import streamlit as st
import pandas as pd
from thefuzz import process, fuzz
import os
import io
import json
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="DE/PARA SPED ECD", layout="wide")
st.markdown("<style>.cont-row {border-bottom: 1px solid #f0f2f6; padding: 15px 0px;}</style>", unsafe_allow_html=True)
st.title("🛠️ Conversor de Lançamentos ECD")
st.info("Foco: Substituição pelo **Código Reduzido** com indicadores de progresso.")

# ── INICIALIZAÇÃO DO ESTADO ──────────────────────────────────────────────────
if 'de_para_map' not in st.session_state:
    st.session_state.de_para_map = {}
if 'balanco_processado' not in st.session_state:
    st.session_state.balanco_processado = False
    st.session_state.balanco_dados      = None
    st.session_state.balanco_totais     = {}
if 'i157_processado' not in st.session_state:
    st.session_state.i157_processado = False
    st.session_state.i157_dados      = None
    st.session_state.i157_has_data   = False
# Sugestão de conta PL — inicializa vazio; preenchido após DE/PARA estar pronto
if 'conta_pl_sugerida'      not in st.session_state:
    st.session_state.conta_pl_sugerida      = ""
if 'conta_pl_sugerida_nome' not in st.session_state:
    st.session_state.conta_pl_sugerida_nome = ""
# Guarda a última versão do mapa usada para calcular a sugestão
# (evita recalcular a cada rerun se o mapa não mudou)
if '_pl_mapa_hash' not in st.session_state:
    st.session_state._pl_mapa_hash = ""

# ── FUNÇÕES AUXILIARES GERAIS ────────────────────────────────────────────────
def limpar_nome_arquivo(nome):
    return re.sub(r'[\\/*?:"<>|]', "", nome).strip()

def atualizar_manual(cod_conta):
    chave = f"in_{cod_conta}"
    if chave in st.session_state and st.session_state[chave]:
        st.session_state.de_para_map[str(cod_conta)] = str(st.session_state[chave])

def format_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def ler_arquivo_texto_seguro(file):
    raw = file.getvalue()
    try:    content = raw.decode("latin-1")
    except: content = raw.decode("cp1252", errors="ignore")
    return [l.strip('\r\n') for l in content.splitlines() if l.strip()]

# ── HELPERS PORTADOS DO CONVERSOR UNIFICADO ──────────────────────────────────
def _str2float(v) -> float:
    if isinstance(v, (int, float)): return float(v)
    v = str(v).strip()
    if "." in v and "," in v:
        if v.index(".") < v.index(","): v = v.replace(".", "").replace(",", ".")
        else:                            v = v.replace(",", "")
    elif "," in v: v = v.replace(",", ".")
    try:    return float(v)
    except: return 0.0

def _fmt_valor_balanco(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")

def _calcular_resultado_liquido_i355(saldos_i355: dict) -> tuple:
    """Retorna (valor_absoluto_float, ind_dc) onde C=superávit, D=déficit."""
    total_rec = sum(v for v, dc in saldos_i355.values() if dc == "C")
    total_des = sum(v for v, dc in saldos_i355.values() if dc == "D")
    resultado  = round(total_rec - total_des, 2)
    return (resultado, "C") if resultado >= 0 else (abs(resultado), "D")

# ── SUGESTÃO DE CONTA PL COM DE/PARA ────────────────────────────────────────
_PALAVRAS_PL_ALTA  = ("LUCRO", "PREJUIZO", "PREJUÍZO", "SUPERAVIT",
                       "SUPERÁVIT", "DEFICIT", "DÉFICIT")
_PALAVRAS_PL_MEDIA = ("RESULTADO", "SOBRA", "PERDA", "SURPLUS")

def _sugerir_conta_pl_com_depara(
        map_final: dict,          # cod_antigo → cod_novo  (DE/PARA já realizado)
        final_balances: dict,     # cod_antigo → (val_str, dc)  do I155
        saldos_i355: dict,        # cod_antigo → (float, dc)
        df_novo: pd.DataFrame,    # plano de contas destino com cols Código, Nome, Classificação
) -> tuple:
    """
    Sugere a conta de PL/Resultado usando o código DESTINO (após DE/PARA).

    Critérios (em ordem de prioridade):
      1. Conta cujo nome no plano destino contém palavra de alta prioridade
         (LUCRO, PREJUIZO, SUPERAVIT, DEFICIT …)
      2. Dentro das candidatas, prefere a que tem saldo >= resultado_líquido
      3. Entre empatadas, a de maior saldo absoluto

    Retorna (cod_novo_sugerido, nome_no_plano_novo) ou ("", "").
    """
    if not map_final or not final_balances:
        return "", ""

    res_liq, dc_res = _calcular_resultado_liquido_i355(saldos_i355)

    # Monta dicionário: cod_novo → (saldo_float, dc, nome_no_plano_novo)
    df_idx = df_novo.set_index("Código")   # índice = código reduzido (destino)

    candidatas = []
    for cod_ant, cod_nov in map_final.items():
        cod_nov = str(cod_nov).strip().replace("|", "")
        if not cod_nov:
            continue

        # Saldo no I155 para este código antigo
        val_str, dc = final_balances.get(cod_ant, ("0,00", "D"))
        saldo = _str2float(val_str)
        if saldo <= 0:
            continue

        # Nome no plano destino
        if cod_nov not in df_idx.index:
            continue
        nome_nov = str(df_idx.loc[cod_nov, "Nome"]).upper()

        # Classifica prioridade pelo nome
        if any(p in nome_nov for p in _PALAVRAS_PL_ALTA):
            prioridade = 0
        elif any(p in nome_nov for p in _PALAVRAS_PL_MEDIA):
            prioridade = 1
        else:
            continue   # não é conta de PL/resultado — ignora

        # Tem saldo suficiente para absorver o resultado?
        saldo_suficiente = saldo >= res_liq - 0.005

        candidatas.append({
            "cod_nov":         cod_nov,
            "nome":            df_idx.loc[cod_nov, "Nome"],
            "saldo":           saldo,
            "dc":              dc,
            "prioridade":      prioridade,
            "saldo_suficiente":saldo_suficiente,
        })

    if not candidatas:
        return "", ""

    # Ordena: prioridade (0=alta), depois saldo_suficiente desc, depois saldo desc
    candidatas.sort(key=lambda c: (
        c["prioridade"],
        0 if c["saldo_suficiente"] else 1,
        -c["saldo"],
    ))

    melhor = candidatas[0]
    return melhor["cod_nov"], melhor["nome"]

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
st.sidebar.header("Configurações")
file_sped    = st.sidebar.file_uploader("1. Arquivo SPED (TXT)", type=["txt"])
usar_padrao  = st.sidebar.checkbox("Usar Plano de Contas Padrão UNSÃO?", value=True)

# ── CARREGAMENTO DO PLANO ────────────────────────────────────────────────────
df_novo = None
if usar_padrao:
    caminho_padrao = "plano_padrao.xlsx"
    if os.path.exists(caminho_padrao):
        try:
            df_novo = pd.read_excel(caminho_padrao, header=None).iloc[:, [0, 1, 2]]
            df_novo.columns = ['Código', 'Classificação', 'Nome']
        except:
            st.sidebar.error("Erro ao ler plano_padrao.xlsx")
    else:
        st.sidebar.warning("Arquivo 'plano_padrao.xlsx' não encontrado.")
else:
    file_excel = st.sidebar.file_uploader("2. Subir Novo Plano (Excel)", type=["xlsx"])
    with st.sidebar.expander("ℹ️ Ver Modelo / Baixar Exemplo"):
        st.write("Seu Excel deve seguir estritamente esta ordem (sem cabeçalho):")
        df_exemplo_visual = pd.DataFrame({
            "Coluna A": ["50", "51", "..."],
            "Coluna B": ["1.01.01", "1.01.02", "..."],
            "Coluna C": ["CAIXA GERAL", "BANCO CONTA MOV.", "..."]
        })
        st.table(df_exemplo_visual)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=['A', 'B', 'C']).to_excel(
                writer, sheet_name='Plan1', header=False, index=False)
        st.download_button("⬇️ Baixar Planilha Modelo", buffer,
                           "Modelo_Plano_Contas.xlsx", "application/vnd.ms-excel")
    if file_excel:
        df_novo = pd.read_excel(file_excel, header=None).iloc[:, [0, 1, 2]]
        df_novo.columns = ['Código', 'Classificação', 'Nome']

# ── BACKUP ───────────────────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.header("💾 Backup do Trabalho")
arquivo_backup = st.sidebar.file_uploader(
    "Carregar Progresso Salvo (.json)", type=["json"], key="backup_upload")
if arquivo_backup is not None:
    try:
        file_id = f"{arquivo_backup.name}_{arquivo_backup.size}"
        if st.session_state.get("backup_id") != file_id:
            dados = json.load(arquivo_backup)
            dados_limpos = {str(k): str(v) for k, v in dados.items()}
            st.session_state.de_para_map.update(dados_limpos)
            for cod, val in dados_limpos.items():
                st.session_state[f"in_{cod}"] = val
            st.session_state["backup_id"] = file_id
            st.sidebar.success(f"Backup carregado! {len(dados_limpos)} contas.")
            st.rerun()
    except Exception as e:
        st.sidebar.error(f"Erro no backup: {e}")

placeholder_botao_salvar = st.sidebar.empty()

# ── FILTROS ──────────────────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.header("Filtros de Tela")
ocultar_mapeadas = st.sidebar.checkbox("Ocultar contas já mapeadas?", value=False)

# ═════════════════════════════════════════════════════════════════════════════
# LÓGICA PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════
if file_sped and df_novo is not None:
    df_novo = df_novo.astype(str)
    df_novo['Display'] = (df_novo['Código'] + " | " +
                          df_novo['Classificação'] + " - " + df_novo['Nome'])
    df_novo['Grupo'] = df_novo['Classificação'].str[0]

    content_sped = ler_arquivo_texto_seguro(file_sped)

    # ── CABEÇALHO 0000 ───────────────────────────────────────────────────────
    nome_empresa   = "EMPRESA"
    dt_inicial_sped = None
    dt_final_sped   = None
    for line in content_sped:
        if line.startswith("|0000|"):
            parts = line.split("|")
            if len(parts) > 5: nome_empresa = limpar_nome_arquivo(parts[5])
            try:    dt_inicial_sped = datetime.strptime(parts[3], "%d%m%Y").date()
            except: pass
            try:    dt_final_sped   = datetime.strptime(parts[4], "%d%m%Y").date()
            except: pass
            break

    # ── SALDOS I155 (inicial e final) ────────────────────────────────────────
    initial_balances = {}
    final_balances   = {}
    rtl_count_i150   = 0
    for line in content_sped:
        if line.startswith("|I150|"):
            rtl_count_i150 += 1
        elif line.startswith("|I155|"):
            reg = line.split("|")
            if len(reg) >= 10:
                cod       = reg[2].strip()
                val_ini   = reg[4].strip()
                dc_ini    = reg[5].strip()
                val_fin   = reg[8].strip()
                dc_fin    = reg[9].strip()
                if cod not in initial_balances:
                    initial_balances[cod] = (val_ini, dc_ini) if rtl_count_i150 <= 1 \
                                            else ("0,00", dc_ini)
                final_balances[cod] = (val_fin, dc_fin)

    # ── SALDOS I355 (receitas/despesas abertas) ───────────────────────────────
    saldos_i355: dict = {}   # cod_cta → (valor_float, ind_dc)
    contas_i355: set  = set()
    for line in content_sped:
        if line.startswith("|I355|"):
            reg = line.split("|")
            if len(reg) >= 6:
                cod_cta = reg[2].strip()
                vl_str  = reg[4].strip()
                ind_dc  = reg[5].strip().upper()
                if not cod_cta: continue
                if ind_dc not in ("D", "C"): ind_dc = "D"
                saldos_i355[cod_cta] = (_str2float(vl_str), ind_dc)
                contas_i355.add(cod_cta)

    # ── CONTAS COM MOVIMENTO ─────────────────────────────────────────────────
    contas_com_movimento = set()
    for line in content_sped:
        if line.startswith("|I250|"):
            reg = line.split("|")
            if len(reg) > 2: contas_com_movimento.add(reg[2].strip())
        elif line.startswith("|I155|"):
            reg = line.split("|")
            if len(reg) > 2: contas_com_movimento.add(reg[2].strip())

    # ── I050 → contas de origem ───────────────────────────────────────────────
    contas_origem_data = []
    for line in content_sped:
        if line.startswith("|I050|"):
            reg = line.split("|")
            if len(reg) > 6:
                cod_cta_fixo = reg[6].strip()
                if cod_cta_fixo in contas_com_movimento:
                    nome_conta = "Sem Nome"
                    for j in range(7, len(reg)):
                        if len(reg[j].strip()) > 2 and not reg[j].replace(".", "").isnumeric():
                            nome_conta = reg[j].strip()
                            break
                    contas_origem_data.append({
                        "cod":    cod_cta_fixo,
                        "classif":reg[6].strip(),
                        "nome":   nome_conta,
                        "grupo":  reg[6][0] if reg[6] else ""
                    })

    df_origem = pd.DataFrame(contas_origem_data).drop_duplicates(subset=['cod'])

    if not df_origem.empty:

        # ── MAPEAMENTO / SCORES ───────────────────────────────────────────────
        total_mapeadas_count    = 0
        map_final_para_geracao  = st.session_state.de_para_map.copy()
        process_data            = []

        for idx, row in df_origem.iterrows():
            cod_atual   = str(row['cod'])
            grupo_atual = row['grupo']

            df_filtrado = df_novo[df_novo['Grupo'] == grupo_atual]
            df_busca    = df_filtrado if not df_filtrado.empty else df_novo

            if grupo_atual in ['1', '2']:
                df_opcoes = df_filtrado if not df_filtrado.empty else df_novo
            else:
                df_opcoes = df_novo[~df_novo['Grupo'].isin(['1', '2'])]
                if df_opcoes.empty: df_opcoes = df_novo

            lista_nomes = df_busca['Nome'].tolist()
            candidatos  = process.extract(row['nome'], lista_nomes,
                                          scorer=fuzz.token_set_ratio, limit=5)
            melhor_match = None; melhor_score = -1
            for nome_cand, score_flex in candidatos:
                score_rig = fuzz.token_sort_ratio(row['nome'], nome_cand)
                media = (score_flex + score_rig) / 2
                if media > melhor_score:
                    melhor_score = media; melhor_match = nome_cand
            score = int(melhor_score)

            cod_sugerido_ia = None; display_sugerido_ia = None
            if score >= 65:
                match_row = df_busca[df_busca['Nome'] == melhor_match]
                if not match_row.empty:
                    cod_sugerido_ia     = match_row.iloc[0]['Código']
                    display_sugerido_ia = match_row.iloc[0]['Display']

            esta_no_mapa  = cod_atual in st.session_state.de_para_map
            valor_no_mapa = str(st.session_state.de_para_map.get(cod_atual, ""))
            resolvida = False; is_manual = False

            if esta_no_mapa:
                resolvida = True
                if valor_no_mapa != cod_sugerido_ia: is_manual = True
            elif score >= 65:
                resolvida = True
                map_final_para_geracao[cod_atual] = cod_sugerido_ia

            if resolvida: total_mapeadas_count += 1

            process_data.append({
                "row": row, "df_busca": df_busca, "df_opcoes": df_opcoes,
                "score": score, "cod_sugerido_ia": cod_sugerido_ia,
                "display_sugerido_ia": display_sugerido_ia,
                "resolvida": resolvida, "is_manual": is_manual,
                "esta_no_mapa": esta_no_mapa, "valor_no_mapa": valor_no_mapa,
            })

        # ── SUGESTÃO DE CONTA PL (recalcula quando o mapa muda) ──────────────
        # Usa hash do mapa para evitar recalcular a cada rerun sem mudança
        mapa_hash_atual = str(sorted(map_final_para_geracao.items()))
        if (saldos_i355 and
                mapa_hash_atual != st.session_state._pl_mapa_hash):
            sugerida, sugerida_nome = _sugerir_conta_pl_com_depara(
                map_final_para_geracao,
                final_balances,
                saldos_i355,
                df_novo,
            )
            st.session_state.conta_pl_sugerida      = sugerida
            st.session_state.conta_pl_sugerida_nome = sugerida_nome
            st.session_state._pl_mapa_hash          = mapa_hash_atual

        # ── EXIBIÇÃO DO MAPEAMENTO ────────────────────────────────────────────
        st.subheader("🔗 Mapeamento de Contas")

        for item in process_data:
            row       = item['row']
            cod_atual = str(row['cod'])
            resolvida = item['resolvida']
            esta_no_mapa = item['esta_no_mapa']

            if ocultar_mapeadas and resolvida: continue

            with st.container():
                col_origem, col_destino = st.columns([1, 1])
                with col_origem:
                    st.markdown(f"**{row['nome']}**")
                    st.caption(f"Cod no SPED: {cod_atual} | Grupo: {row['grupo']}")

                with col_destino:
                    df_opcoes    = item['df_opcoes']
                    opcoes       = ["-- SELECIONE --",
                                    "📝 -- DIGITAR MANUALMENTE --"] + df_opcoes['Display'].tolist()
                    chave_select = f"sel_{cod_atual}"
                    valor_inicial = opcoes[0]

                    if esta_no_mapa:
                        match_row = df_novo[df_novo['Código'] == item['valor_no_mapa']]
                        if not match_row.empty:
                            display_str = match_row.iloc[0]['Display']
                            if display_str not in opcoes: opcoes.insert(2, display_str)
                            valor_inicial = display_str
                        else:
                            valor_inicial = "📝 -- DIGITAR MANUALMENTE --"
                            if f"in_{cod_atual}" not in st.session_state:
                                st.session_state[f"in_{cod_atual}"] = item['valor_no_mapa']
                    elif item['display_sugerido_ia']:
                        if item['display_sugerido_ia'] not in opcoes:
                            opcoes.insert(2, item['display_sugerido_ia'])
                        valor_inicial = (item['display_sugerido_ia']
                                        if chave_select not in st.session_state
                                        else st.session_state[chave_select])

                    if chave_select not in st.session_state:
                        st.session_state[chave_select] = valor_inicial

                    if item['is_manual']:         st.info("📌 Mapeado Manualmente")
                    elif item['score'] >= 65:     st.success(f"✅ Sugestão: {item['score']}%")
                    else:                         st.warning(f"⚠️ Similaridade baixa ({item['score']}%)")

                    escolha = st.selectbox(
                        label=f"sel_{cod_atual}", options=opcoes,
                        key=chave_select, label_visibility="collapsed"
                    )

                    novo_valor = None
                    if escolha == "📝 -- DIGITAR MANUALMENTE --":
                        pass
                    elif escolha != "-- SELECIONE --":
                        try:
                            cod_red = escolha.split(" | ")[0]
                            if str(cod_red) != item['valor_no_mapa']:
                                novo_valor = str(cod_red)
                        except: pass
                    elif escolha == "-- SELECIONE --" and esta_no_mapa:
                        del st.session_state.de_para_map[cod_atual]
                        st.rerun()

                    if novo_valor:
                        st.session_state.de_para_map[cod_atual] = novo_valor
                        st.rerun()

                    if escolha == "📝 -- DIGITAR MANUALMENTE --":
                        valor_ant = st.session_state.de_para_map.get(cod_atual, "")
                        st.text_input(f"Cód. manual para {cod_atual}:", value=valor_ant,
                                      key=f"in_{cod_atual}",
                                      on_change=atualizar_manual, args=(cod_atual,))
                st.markdown("---")

        # ── MÉTRICAS ──────────────────────────────────────────────────────────
        st.divider()
        col_m1, col_m2, col_m3 = st.columns(3)
        perc = (total_mapeadas_count / len(df_origem)) * 100 if len(df_origem) > 0 else 0
        col_m1.metric("Total",    len(df_origem))
        col_m2.metric("Mapeadas", total_mapeadas_count, f"{perc:.1f}%")
        col_m3.metric("Pendentes",len(df_origem) - total_mapeadas_count,
                      f"-{len(df_origem) - total_mapeadas_count}", delta_color="inverse")

        # ── FINALIZAÇÃO ───────────────────────────────────────────────────────
        st.divider()
        st.subheader("📂 Finalização, Relatórios e Downloads")
        col1, col2, col3, col4 = st.columns(4)

        pendentes = len(df_origem) - total_mapeadas_count

        # ── COL 1 — SPED AJUSTADO ─────────────────────────────────────────────
        sped_buffer = None
        if pendentes == 0:
            saida = []
            for line in content_sped:
                if line.startswith("|9999|"):
                    saida.append(line); break
                if line.startswith("|I250|"):
                    reg = line.split("|")
                    if len(reg) > 2 and reg[2] in map_final_para_geracao:
                        reg[2] = str(map_final_para_geracao[reg[2]]).strip().replace("|", "")
                    saida.append("|".join(reg))
                else:
                    saida.append(line)
            sped_buffer = "\r\n".join(saida).encode("latin-1", errors="replace")

        with col1:
            st.markdown("**1. Arquivo Final**")
            if pendentes > 0:
                st.warning(f"⚠️ Faltam {pendentes}.")
                st.button("🚀 Gerar SPED", disabled=True)
            else:
                st.download_button(
                    "💾 Baixar SPED Ajustado", data=sped_buffer,
                    file_name=f"SPED_AJUSTADO_{nome_empresa}.txt",
                    mime="text/plain", use_container_width=True)
                if os.path.exists("Conjunto SPED.xml"):
                    st.markdown("---")
                    with open("Conjunto SPED.xml", "rb") as f:
                        st.download_button("⬇️ Baixar Conjunto SPED (XML)",
                                           f.read(), "Conjunto SPED.xml",
                                           "application/xml", use_container_width=True)

        # ── COL 2 — BALANÇO ───────────────────────────────────────────────────
        with col2:
            st.markdown("**2. Balanço (I155)**")

            tipo_saldo = st.radio(
                "Referência do Saldo:",
                ["Inicial (Abertura)", "Final (Fechamento)"],
                key="radio_tipo_saldo"
            )

            # ── Opções extras só para saldo FINAL ────────────────────────────
            modo_resultado_balanco = "apenas_patrimonial"
            conta_pl_informada     = ""

            if tipo_saldo == "Final (Fechamento)":
                tem_i355 = bool(saldos_i355)
                st.markdown("---")
                st.markdown("**Escopo do Balanço:**")

                if tem_i355:
                    escopo_sel = st.radio(
                        "Escopo:",
                        ["✅ Apenas Ativo / Passivo / PL (balanço fechado)",
                         "📂 Ativo / Passivo / PL + Resultado (aberto — encerrar no destino)"],
                        key="radio_escopo_balanco",
                        label_visibility="collapsed"
                    )
                else:
                    escopo_sel = "✅ Apenas Ativo / Passivo / PL (balanço fechado)"
                    st.caption("ℹ️ Nenhum registro I355 encontrado — "
                               "somente o modo patrimonial está disponível.")

                if "Resultado" in escopo_sel:
                    modo_resultado_balanco = "aberto_com_resultado"

                    # Métricas do I355
                    res_liq, dc_res = _calcular_resultado_liquido_i355(saldos_i355)
                    total_rec_355   = sum(v for v, dc in saldos_i355.values() if dc == "C")
                    total_des_355   = sum(v for v, dc in saldos_i355.values() if dc == "D")

                    st.markdown("---")
                    _c1, _c2, _c3 = st.columns(3)
                    _c1.metric("Receitas (I355)",  format_moeda(total_rec_355))
                    _c2.metric("Despesas (I355)",  format_moeda(total_des_355))
                    _c3.metric(
                        f"Resultado ({'Superávit' if dc_res == 'C' else 'Déficit'})",
                        format_moeda(res_liq)
                    )

                    # ── Sugestão automática da conta PL ──────────────────────
                    sugerida      = st.session_state.conta_pl_sugerida
                    sugerida_nome = st.session_state.conta_pl_sugerida_nome

                    st.markdown("---")
                    st.markdown("**Conta de PL / Resultado (Superávit / Déficit):**")

                    if sugerida:
                        saldo_sug_str, dc_sug = final_balances.get(
                            # tenta achar o cod_antigo que mapeia para sugerida
                            next((k for k, v in map_final_para_geracao.items()
                                  if str(v) == sugerida), ""),
                            ("0,00", "?")
                        )
                        saldo_sug_f = _str2float(saldo_sug_str)

                        suficiente = saldo_sug_f >= res_liq - 0.005
                        badge = "✅" if suficiente else "⚠️"
                        st.info(
                            f"{badge} Sugestão automática: **{sugerida}** — {sugerida_nome}\n\n"
                            f"Saldo atual: **{format_moeda(saldo_sug_f)} ({dc_sug})**  |  "
                            f"Resultado a absorver: **{format_moeda(res_liq)}**\n\n"
                            "Detectada pelo nome no plano destino (após DE/PARA). "
                            "Confirme antes de processar."
                        )
                    else:
                        st.warning(
                            "⚠️ Nenhuma conta de PL/Resultado detectada automaticamente "
                            "no plano destino. Informe o código manualmente."
                        )

                    conta_pl_informada = st.text_input(
                        "Código da conta de Superávit/Déficit no PL (código DESTINO):",
                        value=sugerida if sugerida else "",
                        placeholder="Ex: 311010101",
                        key="input_conta_pl_balanco",
                        help=(
                            "Use o código já convertido pelo DE/PARA. "
                            "O valor do Resultado Líquido do I355 será deduzido desta conta "
                            "para que Débitos = Créditos no lançamento gerado."
                        )
                    )

                    if not conta_pl_informada:
                        st.warning("⚠️ Informe a conta de PL/Resultado para que o balanço feche.")
                    elif sugerida and conta_pl_informada != sugerida:
                        st.caption(
                            f"ℹ️ Usando conta informada: **{conta_pl_informada}** "
                            f"(sugestão era: {sugerida})"
                        )

            # ── Data do balanço ───────────────────────────────────────────────
            st.markdown("---")
            data_padrao = datetime.today()
            if tipo_saldo == "Inicial (Abertura)" and dt_inicial_sped:
                data_padrao = dt_inicial_sped - timedelta(days=1)
            elif tipo_saldo == "Final (Fechamento)" and dt_final_sped:
                data_padrao = dt_final_sped

            data_balanco = st.date_input(
                "Data p/ Balanço:", data_padrao,
                format="DD/MM/YYYY", key="date_balanco"
            )
            dt_fmt = data_balanco.strftime("%d/%m/%Y")

            # ── Botão Processar ───────────────────────────────────────────────
            btn_disabled = (
                modo_resultado_balanco == "aberto_com_resultado"
                and not conta_pl_informada.strip()
            )
            processar_balanco = st.button(
                "🔍 Processar Balanço",
                key="btn_processar_balanco",
                disabled=btn_disabled,
                help=("Informe a conta de PL/Resultado para habilitar."
                      if btn_disabled else "")
            )

            if processar_balanco:
                balanco_lines = ["|6000|V||||"]
                total_debito  = 0.0
                total_credito = 0.0
                has_balanco   = False

                saldos_base = (initial_balances
                               if tipo_saldo == "Inicial (Abertura)"
                               else final_balances)

                # ── Modo 1: apenas patrimonial ────────────────────────────────
                if modo_resultado_balanco == "apenas_patrimonial":
                    for cod_antigo, cod_novo in map_final_para_geracao.items():
                        cod_novo = str(cod_novo).replace("|", "")
                        val_str, dc = saldos_base.get(cod_antigo, ("0,00", "D"))
                        val_f = _str2float(val_str)
                        if val_f <= 0: continue

                        if dc == "D":
                            total_debito += val_f
                            linha = (f"|6100|{dt_fmt}|{cod_novo}||"
                                     f"{_fmt_valor_balanco(val_f)}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        else:
                            total_credito += val_f
                            linha = (f"|6100|{dt_fmt}||{cod_novo}|"
                                     f"{_fmt_valor_balanco(val_f)}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        balanco_lines.append(linha)
                        has_balanco = True

                # ── Modo 2: aberto com resultado ──────────────────────────────
                else:
                    conta_pl  = conta_pl_informada.strip()
                    res_liq, dc_res = _calcular_resultado_liquido_i355(saldos_i355)

                    # Monta saldos patrimoniais como float,
                    # excluindo contas que aparecem no I355
                    # A chave aqui é o cod_NOVO (destino), não o original
                    saldos_destino: dict = {}  # cod_novo → (float, dc)

                    for cod_ant, cod_nov in map_final_para_geracao.items():
                        cod_nov = str(cod_nov).replace("|", "")
                        if not cod_nov: continue
                        if cod_ant in contas_i355: continue   # virá pelo I355

                        val_str, dc = saldos_base.get(cod_ant, ("0,00", "D"))
                        val_f = _str2float(val_str)
                        saldos_destino[cod_nov] = (val_f, dc)

                    # Ajusta a conta PL: retira o resultado para "reabrir" via I355
                    if conta_pl in saldos_destino:
                        saldo_pl, dc_pl = saldos_destino[conta_pl]
                        if   dc_pl == "C" and dc_res == "C": novo_saldo = round(saldo_pl - res_liq, 2)
                        elif dc_pl == "D" and dc_res == "D": novo_saldo = round(saldo_pl - res_liq, 2)
                        elif dc_pl == "C" and dc_res == "D": novo_saldo = round(saldo_pl + res_liq, 2)
                        else:                                 novo_saldo = round(saldo_pl + res_liq, 2)

                        if novo_saldo >= 0:
                            saldos_destino[conta_pl] = (novo_saldo, dc_pl)
                        else:
                            dc_inv = "D" if dc_pl == "C" else "C"
                            saldos_destino[conta_pl] = (abs(novo_saldo), dc_inv)
                    else:
                        st.warning(
                            f"⚠️ Conta PL **{conta_pl}** não encontrada nos saldos "
                            "destino. O balanço pode não fechar."
                        )

                    # Gera linhas patrimoniais (já com código destino)
                    for cod_nov, (val_f, dc) in saldos_destino.items():
                        if val_f <= 0: continue
                        val_fmt = _fmt_valor_balanco(val_f)
                        if dc == "D":
                            total_debito += val_f
                            linha = (f"|6100|{dt_fmt}|{cod_nov}||{val_fmt}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        else:
                            total_credito += val_f
                            linha = (f"|6100|{dt_fmt}||{cod_nov}|{val_fmt}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        balanco_lines.append(linha)
                        has_balanco = True

                    # Gera linhas de resultado (I355) — aplica DE/PARA
                    for cod_ant, (val_f, dc) in saldos_i355.items():
                        if val_f <= 0: continue
                        cod_nov = str(map_final_para_geracao.get(cod_ant, "")).replace("|", "")
                        if not cod_nov: continue   # sem mapeamento — ignora
                        val_fmt = _fmt_valor_balanco(val_f)
                        if dc == "D":
                            total_debito += val_f
                            linha = (f"|6100|{dt_fmt}|{cod_nov}||{val_fmt}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        else:
                            total_credito += val_f
                            linha = (f"|6100|{dt_fmt}||{cod_nov}|{val_fmt}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        balanco_lines.append(linha)
                        has_balanco = True

                # ── Persiste resultado ────────────────────────────────────────
                st.session_state.balanco_dados  = "\r\n".join(balanco_lines).encode(
                    "latin-1", errors="replace")
                st.session_state.balanco_totais = {
                    "D": round(total_debito, 2),
                    "C": round(total_credito, 2),
                }
                st.session_state.balanco_processado = True
                st.session_state.balanco_has_data   = has_balanco
                st.rerun()

            # ── Exibe totais e download ───────────────────────────────────────
            if st.session_state.balanco_processado:
                tot  = st.session_state.balanco_totais
                diff = round(tot["D"] - tot["C"], 2)
                st.markdown("---")
                st.caption(f"Débitos:  {format_moeda(tot['D'])}")
                st.caption(f"Créditos: {format_moeda(tot['C'])}")
                if abs(diff) > 0.01:
                    st.error(f"Diferença: {format_moeda(diff)}")
                else:
                    st.success("Diferença: R$ 0,00 ✅")

                if st.session_state.get('balanco_has_data') and pendentes == 0:
                    st.download_button(
                        "💾 Baixar Balanço",
                        data=st.session_state.balanco_dados,
                        file_name=f"BALANCO_{nome_empresa}_{dt_fmt.replace('/', '')}.txt",
                        mime="text/plain", use_container_width=True
                    )
                elif pendentes > 0: st.warning("Resolva pendências.")
                else:               st.warning("Sem dados.")

        # ── COL 3 — I157 ──────────────────────────────────────────────────────
        with col3:
            st.markdown("**3. Troca de Plano (I157)**")
            if st.button("🔄 Processar I157"):
                i157_lines    = ["ID;;;;;;"]
                has_i157      = False
                i157_data_list = []

                for cod_antigo in map_final_para_geracao:
                    novo    = map_final_para_geracao[cod_antigo].replace("|", "")
                    val_str, dc = initial_balances.get(cod_antigo, ("0,00", "D"))
                    try:    val_float = float(val_str.replace(",", "."))
                    except: val_float = 0.0
                    if val_float > 0:
                        i157_data_list.append((novo, cod_antigo, val_str, dc))

                if i157_data_list:
                    i157_data_list.sort(key=lambda x: str(x[0]))
                    for item in i157_data_list:
                        novo, cod_antigo, val_str, dc = item
                        if "." in cod_antigo or not cod_antigo.isnumeric():
                            linha = f"C;{novo};;{cod_antigo};{val_str};{dc};"
                        else:
                            linha = f"C;{novo};{cod_antigo};;{val_str};{dc};"
                        i157_lines.append(linha)
                    has_i157 = True

                st.session_state.i157_dados      = "\r\n".join(i157_lines).encode(
                    "latin-1", errors="replace")
                st.session_state.i157_processado = True
                st.session_state.i157_has_data   = has_i157
                st.rerun()

            if st.session_state.get('i157_processado'):
                st.markdown("---")
                if st.session_state.i157_has_data and pendentes == 0:
                    st.success("✅ Arquivo I157 gerado!")
                    st.download_button(
                        "💾 Baixar I157",
                        data=st.session_state.i157_dados,
                        file_name=f"I157_Saldos_{nome_empresa}.txt",
                        mime="text/plain", use_container_width=True
                    )
                    if os.path.exists("Conjunto I157.xml"):
                        st.markdown("---")
                        with open("Conjunto I157.xml", "rb") as f:
                            st.download_button("⬇️ Baixar Conjunto I157 (XML)",
                                               f.read(), "Conjunto I157.xml",
                                               "application/xml", use_container_width=True)
                elif pendentes > 0: st.warning("Resolva pendências.")
                else:               st.warning("Sem dados.")

        # ── COL 4 — CONFERÊNCIA ───────────────────────────────────────────────
        with col4:
            st.markdown("**4. Conferência**")
            df_pend = df_origem[~df_origem['cod'].isin(map_final_para_geracao.keys())]
            if not df_pend.empty:
                st.warning(f"{len(df_pend)} pendentes.")
                st.download_button(
                    "📑 Relatório CSV",
                    df_pend.to_csv(index=False, sep=';', encoding='utf-8-sig'),
                    "contas_pendentes.csv", "text/csv", use_container_width=True
                )
            else:
                st.success("✅ Tudo Mapeado OK!")

    else:
        st.error("Nenhuma conta com movimento detectada.")

# ── BOTÃO SALVAR BACKUP ───────────────────────────────────────────────────────
if 'de_para_map' in st.session_state and len(st.session_state.de_para_map) > 0:
    with placeholder_botao_salvar:
        st.download_button(
            "⬇️ Salvar Progresso Atual",
            json.dumps(st.session_state.de_para_map, indent=4),
            "backup_mapeamento_ecd.json", "application/json",
            help="Baixe para continuar depois."
        )
else:
    st.info("Aguardando arquivos...")
