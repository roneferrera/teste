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

# --- INICIALIZAÇÃO DO ESTADO ---
if 'de_para_map' not in st.session_state:
    st.session_state.de_para_map = {}

if 'balanco_processado' not in st.session_state:
    st.session_state.balanco_processado = False
    st.session_state.balanco_dados = None
    st.session_state.balanco_totais = {}

if 'i157_processado' not in st.session_state:
    st.session_state.i157_processado = False
    st.session_state.i157_dados = None
    st.session_state.i157_has_data = False

# Novos estados para o modo de saldo aberto com resultado
if 'conta_pl_sugerida' not in st.session_state:
    st.session_state.conta_pl_sugerida = ""
if 'conta_pl_sugerida_nome' not in st.session_state:
    st.session_state.conta_pl_sugerida_nome = ""

# --- FUNÇÕES AUXILIARES ---
def limpar_nome_arquivo(nome):
    nome_limpo = re.sub(r'[\\/*?:"<>|]', "", nome)
    return nome_limpo.strip()

def atualizar_manual(cod_conta):
    chave_input = f"in_{cod_conta}"
    if chave_input in st.session_state:
        valor = st.session_state[chave_input]
        if valor:
            st.session_state.de_para_map[str(cod_conta)] = str(valor)

def atualizar_dropdown(cod_conta, chave_select):
    valor = st.session_state[chave_select]
    if valor and valor != "-- SELECIONE --" and "📝" not in valor:
        cod_reduzido = valor.split(" | ")[0]
        st.session_state.de_para_map[str(cod_conta)] = str(cod_reduzido)
    elif valor == "-- SELECIONE --":
        if str(cod_conta) in st.session_state.de_para_map:
            del st.session_state.de_para_map[str(cod_conta)]

def format_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def ler_arquivo_texto_seguro(file):
    raw_data = file.getvalue()
    try:
        content = raw_data.decode("latin-1")
    except UnicodeError:
        content = raw_data.decode("cp1252", errors="ignore")
    return [linha.strip('\r\n') for linha in content.splitlines() if linha.strip()]

# ── HELPERS portados do Conversor Unificado ──────────────────────────────────

def _str2float(v) -> float:
    """Converte string de valor (com vírgula ou ponto) para float."""
    if isinstance(v, (int, float)):
        return float(v)
    v = str(v).strip()
    if "." in v and "," in v:
        if v.index(".") < v.index(","):
            v = v.replace(".", "").replace(",", ".")
        else:
            v = v.replace(",", "")
    elif "," in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except:
        return 0.0

def _fmt_valor_balanco(valor: float) -> str:
    """Formata float para string com vírgula (ex: 1234,56)."""
    return f"{valor:.2f}".replace(".", ",")

def _sugerir_conta_pl_local(contas_pl_candidatas: list,
                             saldos_i155_raw: dict,
                             resultado_liquido: float) -> str:
    """
    Sugere a conta de PL/Resultado com base nas candidatas do I050.
    Prioriza COD_NAT 09/9, depois menor diferença com o resultado líquido.
    Retorna o código da conta sugerida ou string vazia.
    """
    if not contas_pl_candidatas:
        return ""

    candidatas_com_saldo = []
    for c in contas_pl_candidatas:
        cod = c["cod_cta"]
        if cod in saldos_i155_raw:
            v, dc = saldos_i155_raw[cod]
            diff = abs(abs(v) - resultado_liquido)
            candidatas_com_saldo.append({**c, "saldo": v, "dc": dc, "diff": diff})

    if not candidatas_com_saldo:
        return contas_pl_candidatas[0]["cod_cta"]

    def _score(c):
        prioridade_nat = 0 if c["cod_nat"] in ("09", "9") else 1
        return (prioridade_nat, c["diff"])

    candidatas_com_saldo.sort(key=_score)
    return candidatas_com_saldo[0]["cod_cta"]


def _calcular_resultado_liquido_i355(saldos_i355: dict) -> tuple:
    """
    Resultado líquido = Σ Receitas (C) − Σ Despesas (D).
    Retorna (valor_absoluto, ind_dc) onde ind_dc = 'C' (superávit) ou 'D' (déficit).
    """
    total_rec = sum(v for _, (v, dc) in saldos_i355.items() if dc == "C")
    total_des = sum(v for _, (v, dc) in saldos_i355.items() if dc == "D")
    resultado = round(total_rec - total_des, 2)
    if resultado >= 0:
        return resultado, "C"
    else:
        return abs(resultado), "D"


# --- SIDEBAR ---
st.sidebar.header("Configurações")
file_sped = st.sidebar.file_uploader("1. Arquivo SPED (TXT)", type=["txt"])
usar_padrao = st.sidebar.checkbox("Usar Plano de Contas Padrão UNSÃO?", value=True)

# --- CARREGAMENTO DO PLANO ---
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
            pd.DataFrame(columns=['A', 'B', 'C']).to_excel(writer, sheet_name='Plan1', header=False, index=False)
        st.download_button("⬇️ Baixar Planilha Modelo", buffer, "Modelo_Plano_Contas.xlsx", "application/vnd.ms-excel")

    if file_excel:
        df_novo = pd.read_excel(file_excel, header=None).iloc[:, [0, 1, 2]]
        df_novo.columns = ['Código', 'Classificação', 'Nome']

# --- SEÇÃO BACKUP ---
st.sidebar.divider()
st.sidebar.header("💾 Backup do Trabalho")

arquivo_backup = st.sidebar.file_uploader("Carregar Progresso Salvo (.json)", type=["json"], key="backup_upload")
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

# --- FILTROS DE TELA ---
st.sidebar.divider()
st.sidebar.header("Filtros de Tela")
ocultar_mapeadas = st.sidebar.checkbox("Ocultar contas já mapeadas?", value=False)

# --- Lógica Principal ---
if file_sped and df_novo is not None:
    df_novo = df_novo.astype(str)
    df_novo['Display'] = df_novo['Código'] + " | " + df_novo['Classificação'] + " - " + df_novo['Nome']
    df_novo['Grupo'] = df_novo['Classificação'].str[0]

    content_sped = ler_arquivo_texto_seguro(file_sped)

    # --- EXTRAÇÃO DE DADOS DO CABEÇALHO (REGISTRO 0000) ---
    nome_empresa = "EMPRESA"
    dt_inicial_sped = None
    dt_final_sped = None

    for line in content_sped:
        if line.startswith("|0000|"):
            parts = line.split("|")
            if len(parts) > 5:
                nome_empresa = limpar_nome_arquivo(parts[5])
            if len(parts) > 3:
                try:
                    dt_str = parts[3]
                    dt_inicial_sped = datetime.strptime(dt_str, "%d%m%Y").date()
                except:
                    pass
            if len(parts) > 4:
                try:
                    dt_str_fin = parts[4]
                    dt_final_sped = datetime.strptime(dt_str_fin, "%d%m%Y").date()
                except:
                    pass
            break

    # --- EXTRAÇÃO INTELIGENTE DOS SALDOS (INICIAIS E FINAIS) ---
    initial_balances = {}
    final_balances = {}
    rtl_count_i150 = 0

    for line in content_sped:
        if line.startswith("|I150|"):
            rtl_count_i150 += 1
        elif line.startswith("|I155|"):
            reg = line.split("|")
            if len(reg) >= 10:
                cod = reg[2].strip()
                val_ini_str = reg[4].strip()
                dc_ini = reg[5].strip()
                val_fin_str = reg[8].strip()
                dc_fin = reg[9].strip()

                if cod not in initial_balances:
                    if rtl_count_i150 <= 1:
                        initial_balances[cod] = (val_ini_str, dc_ini)
                    else:
                        initial_balances[cod] = ("0,00", dc_ini)

                final_balances[cod] = (val_fin_str, dc_fin)

    # ── EXTRAÇÃO I355 (Receitas/Despesas abertas — saldo antes do encerramento) ──
    # I355: |I355|COD_CTA|...|VL_CTA|IND_DC|...
    saldos_i355: dict = {}          # cod_cta → (valor_float, ind_dc)
    contas_i355: set  = set()       # conjunto de códigos presentes no I355

    for line in content_sped:
        if line.startswith("|I355|"):
            reg = line.split("|")
            # Layout SPED ECD: |I355|COD_CTA|NUM_ORD|VL_CTA|IND_DC|...
            if len(reg) >= 6:
                cod_cta = reg[2].strip()
                vl_str  = reg[4].strip()
                ind_dc  = reg[5].strip().upper()
                if not cod_cta:
                    continue
                if ind_dc not in ("D", "C"):
                    ind_dc = "D"
                try:
                    valor_f = _str2float(vl_str)
                except:
                    valor_f = 0.0
                saldos_i355[cod_cta] = (valor_f, ind_dc)
                contas_i355.add(cod_cta)

    # ── EXTRAÇÃO I050 — candidatas à conta PL/Resultado ──────────────────────
    # Percorre o arquivo para coletar dados do I050 para sugestão automática
    contas_pl_candidatas: list = []
    mapa_nome_i050: dict       = {}   # cod_cta → nome
    mapa_nat_i050: dict        = {}   # cod_cta → cod_nat

    _PALAVRAS_RESULTADO = (
        "SUPERAVIT", "DÉFICIT", "DEFICIT", "RESULTADO",
        "LUCRO", "PREJUIZO", "PREJUÍZO", "SOBRA", "PERDA",
        "SURPLUS", "RESULTADO DO EXERC", "LUCROS OU PREJUIZ",
    )

    for line in content_sped:
        if not line.startswith("|I050|"):
            continue
        reg = line.split("|")
        # Layout: |I050|DT_ALT|COD_NAT|IND_CTA|COD_CTA_SUP|COD_CTA|...|NOME|
        if len(reg) < 6:
            continue
        # Posições variam — tenta posição padrão SPED ECD (I050 v2)
        # |I050|DT_ALT|COD_NAT|IND_CTA|NIVEL|COD_CTA|COD_CTA_SUP|NOME|...
        try:
            cod_nat  = reg[3].strip()   # COD_NAT
            ind_cta  = reg[4].strip().upper()  # IND_CTA (A=analítica, S=sintética)
            cod_cta  = reg[6].strip()   # COD_CTA
            nome_cta = reg[8].strip() if len(reg) > 8 else ""
        except IndexError:
            continue

        if not cod_cta:
            continue

        mapa_nome_i050[cod_cta] = nome_cta
        mapa_nat_i050[cod_cta]  = cod_nat

        eh_resultado_nat  = cod_nat in ("05", "09", "5", "9")
        nome_up           = nome_cta.upper()
        eh_resultado_nome = any(p in nome_up for p in _PALAVRAS_RESULTADO)

        if ind_cta == "A" and (eh_resultado_nat or eh_resultado_nome):
            contas_pl_candidatas.append({
                "cod_cta":  cod_cta,
                "nome":     nome_cta,
                "cod_nat":  cod_nat,
                "criterio": "COD_NAT" if eh_resultado_nat else "NOME",
            })

    # Calcula resultado líquido do I355 para usar na sugestão
    _total_rec_355 = sum(v for v, dc in saldos_i355.values() if dc == "C")
    _total_des_355 = sum(v for v, dc in saldos_i355.values() if dc == "D")
    _resultado_liq_ref = round(abs(_total_rec_355 - _total_des_355), 2)

    # Sugestão automática de conta PL (usa saldos finais como referência)
    _saldos_i155_raw_float = {
        cod: (_str2float(v), dc)
        for cod, (v, dc) in final_balances.items()
    }
    _conta_pl_sugerida = _sugerir_conta_pl_local(
        contas_pl_candidatas, _saldos_i155_raw_float, _resultado_liq_ref
    )
    if _conta_pl_sugerida and not st.session_state.conta_pl_sugerida:
        st.session_state.conta_pl_sugerida      = _conta_pl_sugerida
        st.session_state.conta_pl_sugerida_nome = mapa_nome_i050.get(_conta_pl_sugerida, "")

    # --- PEGA CONTAS COM MOVIMENTO *OU* COM SALDO PARADO (I155) ---
    contas_com_movimento = set()
    for line in content_sped:
        if line.startswith("|I250|"):
            reg = line.split("|")
            if len(reg) > 2:
                contas_com_movimento.add(reg[2].strip())
        elif line.startswith("|I155|"):
            reg = line.split("|")
            if len(reg) > 2:
                contas_com_movimento.add(reg[2].strip())

    contas_origem_data = []
    for line in content_sped:
        if line.startswith("|I050|"):
            reg = line.split("|")
            if len(reg) > 6:
                cod_encontrado = None
                pos_classif = -1
                cod_cta_fixo = reg[6].strip()
                if cod_cta_fixo in contas_com_movimento:
                    cod_encontrado = cod_cta_fixo
                    pos_classif = 6
                if cod_encontrado:
                    nome_conta = "Sem Nome"
                    for j in range(pos_classif + 1, len(reg)):
                        if len(reg[j].strip()) > 2 and not reg[j].replace(".", "").isnumeric():
                            nome_conta = reg[j].strip()
                            break
                    contas_origem_data.append({
                        "cod": cod_encontrado,
                        "classif": reg[pos_classif].strip(),
                        "nome": nome_conta,
                        "grupo": reg[pos_classif][0] if len(reg[pos_classif]) > 0 else ""
                    })

    # --- CORREÇÃO DO ERRO DUPLICATE KEY ---
    df_origem = pd.DataFrame(contas_origem_data).drop_duplicates(subset=['cod'])

    if not df_origem.empty:

        # --- CÁLCULOS PRINCIPAIS ---
        total_mapeadas_count = 0
        map_final_para_geracao = st.session_state.de_para_map.copy()
        process_data = []

        for idx, row in df_origem.iterrows():
            cod_atual = str(row['cod'])
            grupo_atual = row['grupo']

            df_filtrado = df_novo[df_novo['Grupo'] == grupo_atual]
            df_busca = df_filtrado if not df_filtrado.empty else df_novo

            if grupo_atual in ['1', '2']:
                df_opcoes = df_filtrado if not df_filtrado.empty else df_novo
            else:
                df_opcoes = df_novo[~df_novo['Grupo'].isin(['1', '2'])]
                if df_opcoes.empty:
                    df_opcoes = df_novo

            lista_nomes = df_busca['Nome'].tolist()

            candidatos = process.extract(row['nome'], lista_nomes, scorer=fuzz.token_set_ratio, limit=5)
            melhor_match = None
            melhor_score_final = -1
            for nome_cand, score_flexivel in candidatos:
                score_rigido = fuzz.token_sort_ratio(row['nome'], nome_cand)
                media = (score_flexivel + score_rigido) / 2
                if media > melhor_score_final:
                    melhor_score_final = media
                    melhor_match = nome_cand

            score = int(melhor_score_final)

            cod_sugerido_ia = None
            display_sugerido_ia = None
            if score >= 65:
                match_row = df_busca[df_busca['Nome'] == melhor_match]
                if not match_row.empty:
                    cod_sugerido_ia = match_row.iloc[0]['Código']
                    display_sugerido_ia = match_row.iloc[0]['Display']

            esta_no_mapa = cod_atual in st.session_state.de_para_map
            valor_no_mapa = str(st.session_state.de_para_map.get(cod_atual, ""))

            resolvida = False
            is_manual = False

            if esta_no_mapa:
                resolvida = True
                if valor_no_mapa != cod_sugerido_ia:
                    is_manual = True
            elif score >= 65:
                resolvida = True
                map_final_para_geracao[cod_atual] = cod_sugerido_ia

            if resolvida:
                total_mapeadas_count += 1

            process_data.append({
                "row": row,
                "df_busca": df_busca,
                "df_opcoes": df_opcoes,
                "score": score,
                "cod_sugerido_ia": cod_sugerido_ia,
                "display_sugerido_ia": display_sugerido_ia,
                "resolvida": resolvida,
                "is_manual": is_manual,
                "esta_no_mapa": esta_no_mapa,
                "valor_no_mapa": valor_no_mapa
            })

        # --- EXIBIÇÃO ---
        st.subheader("🔗 Mapeamento de Contas")

        for item in process_data:
            row = item['row']
            cod_atual = str(row['cod'])
            resolvida = item['resolvida']
            esta_no_mapa = item['esta_no_mapa']

            if ocultar_mapeadas and resolvida:
                continue

            with st.container():
                col_origem, col_destino = st.columns([1, 1])
                with col_origem:
                    st.markdown(f"**{row['nome']}**")
                    st.caption(f"Cod no SPED: {cod_atual} | Grupo: {row['grupo']}")

                with col_destino:
                    df_opcoes = item['df_opcoes']
                    opcoes = ["-- SELECIONE --", "📝 -- DIGITAR MANUALMENTE --"] + df_opcoes['Display'].tolist()
                    chave_select = f"sel_{cod_atual}"
                    valor_inicial = opcoes[0]

                    if esta_no_mapa:
                        match_row = df_novo[df_novo['Código'] == item['valor_no_mapa']]
                        if not match_row.empty:
                            display_str = match_row.iloc[0]['Display']
                            if display_str in opcoes:
                                valor_inicial = display_str
                            else:
                                opcoes.insert(2, display_str)
                                valor_inicial = display_str
                        else:
                            valor_inicial = "📝 -- DIGITAR MANUALMENTE --"
                            if f"in_{cod_atual}" not in st.session_state:
                                st.session_state[f"in_{cod_atual}"] = item['valor_no_mapa']
                    elif item['display_sugerido_ia']:
                        if item['display_sugerido_ia'] not in opcoes:
                            opcoes.insert(2, item['display_sugerido_ia'])
                        if chave_select not in st.session_state:
                            valor_inicial = item['display_sugerido_ia']
                        else:
                            valor_inicial = st.session_state[chave_select]

                    if chave_select not in st.session_state:
                        st.session_state[chave_select] = valor_inicial

                    if item['is_manual']:
                        st.info("📌 Mapeado Manualmente")
                    elif item['score'] >= 65:
                        st.success(f"✅ Sugestão: {item['score']}%")
                    else:
                        st.warning(f"⚠️ Similaridade baixa ({item['score']}%)")

                    escolha = st.selectbox(
                        label=f"sel_{cod_atual}", options=opcoes, key=chave_select, label_visibility="collapsed"
                    )

                    novo_valor = None
                    if escolha == "📝 -- DIGITAR MANUALMENTE --":
                        pass
                    elif escolha != "-- SELECIONE --":
                        try:
                            cod_reduzido = escolha.split(" | ")[0]
                            if str(cod_reduzido) != item['valor_no_mapa']:
                                novo_valor = str(cod_reduzido)
                        except:
                            pass
                    elif escolha == "-- SELECIONE --" and esta_no_mapa:
                        del st.session_state.de_para_map[cod_atual]
                        st.rerun()

                    if novo_valor:
                        st.session_state.de_para_map[cod_atual] = novo_valor
                        st.rerun()

                    if escolha == "📝 -- DIGITAR MANUALMENTE --":
                        valor_ant = st.session_state.de_para_map.get(cod_atual, "")
                        st.text_input(f"Cód. manual para {cod_atual}:", value=valor_ant, key=f"in_{cod_atual}", on_change=atualizar_manual, args=(cod_atual,))
                st.markdown("---")

        st.divider()
        col_m1, col_m2, col_m3 = st.columns(3)
        perc_concluido = (total_mapeadas_count / len(df_origem)) * 100 if len(df_origem) > 0 else 0
        col_m1.metric("Total", len(df_origem))
        col_m2.metric("Mapeadas", total_mapeadas_count, f"{perc_concluido:.1f}%")
        col_m3.metric("Pendentes", len(df_origem) - total_mapeadas_count, f"-{len(df_origem) - total_mapeadas_count}", delta_color="inverse")

        # --- FINALIZAÇÃO ---
        st.divider()
        st.subheader("📂 Finalização, Relatórios e Downloads")
        col1, col2, col3, col4 = st.columns(4)

        # 1. SPED AJUSTADO
        sped_buffer = None
        pendentes = len(df_origem) - total_mapeadas_count
        if pendentes == 0:
            saida = []
            for line in content_sped:
                if line.startswith("|9999|"):
                    saida.append(line)
                    break
                if line.startswith("|I250|"):
                    reg = line.split("|")
                    if len(reg) > 2 and reg[2] in map_final_para_geracao:
                        novo_cod = str(map_final_para_geracao[reg[2]]).strip().replace("|", "")
                        reg[2] = novo_cod
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
                    file_name=f"SPED_AJUSTADO_{nome_empresa}.txt", mime="text/plain", use_container_width=True
                )

                if os.path.exists("Conjunto SPED.xml"):
                    st.markdown("---")
                    with open("Conjunto SPED.xml", "rb") as f:
                        st.download_button("⬇️ Baixar Conjunto SPED (XML)", f.read(), "Conjunto SPED.xml", "application/xml", use_container_width=True)

        # ══════════════════════════════════════════════════════════════════════
        # 2. BALANÇO (I155) — com suporte ao modo Aberto com Resultado (I355)
        # ══════════════════════════════════════════════════════════════════════
        with col2:
            st.markdown("**2. Balanço (I155)**")

            tipo_saldo = st.radio(
                "Referência do Saldo:",
                ["Inicial (Abertura)", "Final (Fechamento)"],
                key="radio_tipo_saldo"
            )

            # ── Opções extras apenas para o saldo FINAL ──────────────────────
            modo_resultado_balanco = "apenas_patrimonial"   # default seguro
            conta_pl_informada     = ""

            if tipo_saldo == "Final (Fechamento)":
                tem_i355 = bool(saldos_i355)

                st.markdown("---")
                st.markdown("**Escopo do Balanço:**")

                opcoes_escopo = ["✅ Apenas Ativo / Passivo / PL (balanço fechado)"]
                if tem_i355:
                    opcoes_escopo.append("📂 Ativo / Passivo / PL + Resultado (aberto para encerrar no destino)")
                else:
                    st.caption("ℹ️ Nenhum registro I355 encontrado — somente o modo patrimonial está disponível.")

                escopo_sel = st.radio(
                    "Escopo:",
                    opcoes_escopo,
                    key="radio_escopo_balanco",
                    label_visibility="collapsed"
                )

                if "Resultado" in escopo_sel:
                    modo_resultado_balanco = "aberto_com_resultado"

                    # Exibe métricas do I355 para orientação
                    res_liq, dc_res = _calcular_resultado_liquido_i355(saldos_i355)
                    total_rec_355 = sum(v for v, dc in saldos_i355.values() if dc == "C")
                    total_des_355 = sum(v for v, dc in saldos_i355.values() if dc == "D")

                    st.markdown("---")
                    _c1, _c2, _c3 = st.columns(3)
                    _c1.metric("Receitas (I355)",  format_moeda(total_rec_355))
                    _c2.metric("Despesas (I355)",  format_moeda(total_des_355))
                    _c3.metric(
                        f"Resultado {'Superávit' if dc_res == 'C' else 'Déficit'}",
                        format_moeda(res_liq)
                    )

                    # ── Sugestão automática da conta PL ──────────────────────
                    sugerida      = st.session_state.conta_pl_sugerida
                    sugerida_nome = st.session_state.conta_pl_sugerida_nome

                    st.markdown("---")
                    st.markdown("**Conta de PL / Resultado (Superávit / Déficit):**")

                    if sugerida:
                        st.info(
                            f"💡 Sugestão automática: **{sugerida}** — {sugerida_nome}\n\n"
                            "Detectada pelo COD_NAT / nome no I050. Confirme antes de processar."
                        )

                    conta_pl_informada = st.text_input(
                        "Código da conta de Superávit/Déficit no PL:",
                        value=sugerida if sugerida else "",
                        placeholder="Ex: 311010101",
                        key="input_conta_pl_balanco",
                        help=(
                            "O valor do Resultado Líquido do I355 será deduzido desta conta "
                            "para que Débitos = Créditos no lançamento gerado."
                        )
                    )

                    if not conta_pl_informada:
                        st.warning(
                            "⚠️ Informe a conta de PL/Resultado para que o balanço feche (D = C)."
                        )
                    elif sugerida and conta_pl_informada != sugerida:
                        st.caption(f"ℹ️ Usando conta informada: **{conta_pl_informada}** (sugestão era: {sugerida})")

            # ── Data do balanço ───────────────────────────────────────────────
            st.markdown("---")
            data_padrao = datetime.today()
            if tipo_saldo == "Inicial (Abertura)" and dt_inicial_sped:
                data_padrao = dt_inicial_sped - timedelta(days=1)
            elif tipo_saldo == "Final (Fechamento)" and dt_final_sped:
                data_padrao = dt_final_sped

            data_balanco = st.date_input("Data p/ Balanço:", data_padrao, format="DD/MM/YYYY", key="date_balanco")
            dt_fmt = data_balanco.strftime("%d/%m/%Y")

            # ── Botão Processar ───────────────────────────────────────────────
            btn_disabled_pl = (
                modo_resultado_balanco == "aberto_com_resultado"
                and not conta_pl_informada.strip()
            )
            if btn_disabled_pl:
                st.button("🔍 Processar Balanço", disabled=True,
                          help="Informe a conta de PL/Resultado para habilitar.")
                processar_balanco = False
            else:
                processar_balanco = st.button("🔍 Processar Balanço", key="btn_processar_balanco")

            if processar_balanco:
                balanco_lines = ["|6000|V||||"]
                total_debito = 0.0
                total_credito = 0.0
                has_balanco = False

                # Escolhe o dicionário de saldos base conforme tipo_saldo
                if tipo_saldo == "Inicial (Abertura)":
                    saldos_base = initial_balances   # dict: cod → (val_str, dc)
                else:
                    saldos_base = final_balances     # dict: cod → (val_str, dc)

                # ── Modo 1: apenas patrimonial ────────────────────────────────
                if modo_resultado_balanco == "apenas_patrimonial":
                    for cod_antigo, novo in map_final_para_geracao.items():
                        novo = novo.replace("|", "")
                        val_str, dc = saldos_base.get(cod_antigo, ("0,00", "D"))
                        try:
                            val_float = _str2float(val_str)
                        except:
                            val_float = 0.0
                        if val_float <= 0:
                            continue
                        if dc == "D":
                            total_debito += val_float
                            linha = (f"|6100|{dt_fmt}|{novo}||{val_str}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        else:
                            total_credito += val_float
                            linha = (f"|6100|{dt_fmt}||{novo}|{val_str}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        balanco_lines.append(linha)
                        has_balanco = True

                # ── Modo 2: aberto com resultado (I355) ───────────────────────
                else:
                    conta_pl = conta_pl_informada.strip()
                    res_liq, dc_res = _calcular_resultado_liquido_i355(saldos_i355)

                    # Monta dicionário de saldos patrimoniais como float
                    # Exclui as contas que aparecem no I355 (serão adicionadas separadamente)
                    saldos_pat_float: dict = {}   # cod_antigo → (float, dc)
                    for cod, (val_str, dc) in saldos_base.items():
                        if cod in contas_i355:
                            continue   # tratado via I355
                        try:
                            val_f = _str2float(val_str)
                        except:
                            val_f = 0.0
                        saldos_pat_float[cod] = (val_f, dc)

                    # Ajusta a conta PL: retira o resultado líquido para "reabrir"
                    if conta_pl in saldos_pat_float:
                        saldo_pl, dc_pl = saldos_pat_float[conta_pl]
                        # Lógica de dedução idêntica ao Conversor Unificado
                        if dc_pl == "C" and dc_res == "C":
                            novo_saldo = round(saldo_pl - res_liq, 2)
                        elif dc_pl == "D" and dc_res == "D":
                            novo_saldo = round(saldo_pl - res_liq, 2)
                        elif dc_pl == "C" and dc_res == "D":
                            novo_saldo = round(saldo_pl + res_liq, 2)
                        else:   # dc_pl == "D" e dc_res == "C"
                            novo_saldo = round(saldo_pl + res_liq, 2)

                        if novo_saldo >= 0:
                            saldos_pat_float[conta_pl] = (novo_saldo, dc_pl)
                        else:
                            dc_inv = "D" if dc_pl == "C" else "C"
                            saldos_pat_float[conta_pl] = (abs(novo_saldo), dc_inv)
                    else:
                        st.warning(
                            f"⚠️ Conta PL **{conta_pl}** não encontrada nos saldos finais (I155). "
                            "O balanço pode não fechar."
                        )

                    # Gera linhas patrimoniais (com DE/PARA aplicado)
                    for cod_antigo, (val_f, dc) in saldos_pat_float.items():
                        if val_f <= 0:
                            continue
                        novo = map_final_para_geracao.get(cod_antigo, "").replace("|", "")
                        if not novo:
                            continue   # conta sem mapeamento — ignora
                        val_str_fmt = _fmt_valor_balanco(val_f)
                        if dc == "D":
                            total_debito += val_f
                            linha = (f"|6100|{dt_fmt}|{novo}||{val_str_fmt}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        else:
                            total_credito += val_f
                            linha = (f"|6100|{dt_fmt}||{novo}|{val_str_fmt}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        balanco_lines.append(linha)
                        has_balanco = True

                    # Gera linhas de resultado (I355) — com DE/PARA aplicado
                    for cod_antigo, (val_f, dc) in saldos_i355.items():
                        if val_f <= 0:
                            continue
                        novo = map_final_para_geracao.get(cod_antigo, "").replace("|", "")
                        if not novo:
                            continue   # conta de resultado sem mapeamento — ignora
                        val_str_fmt = _fmt_valor_balanco(val_f)
                        if dc == "D":
                            total_debito += val_f
                            linha = (f"|6100|{dt_fmt}|{novo}||{val_str_fmt}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        else:
                            total_credito += val_f
                            linha = (f"|6100|{dt_fmt}||{novo}|{val_str_fmt}"
                                     f"||SALDO DE ABERTURA EM {dt_fmt}|||||")
                        balanco_lines.append(linha)
                        has_balanco = True

                # ── Persiste no session_state ─────────────────────────────────
                st.session_state.balanco_dados   = "\r\n".join(balanco_lines).encode("latin-1", errors="replace")
                st.session_state.balanco_totais  = {"D": round(total_debito, 2), "C": round(total_credito, 2)}
                st.session_state.balanco_processado = True
                st.session_state.balanco_has_data   = has_balanco
                st.rerun()

            # ── Exibição dos totais e download ────────────────────────────────
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
                        mime="text/plain",
                        use_container_width=True
                    )
                elif pendentes > 0:
                    st.warning("Resolva pendências.")
                else:
                    st.warning("Sem dados.")

        # 3. I157 (Saldos Antigos)
        with col3:
            st.markdown("**3. Troca de Plano (I157)**")

            if st.button("🔄 Processar I157"):
                i157_lines = ["ID;;;;;;"]
                has_i157 = False
                i157_data_list = []

                for cod_antigo in map_final_para_geracao:
                    novo = map_final_para_geracao[cod_antigo].replace("|", "")
                    val_str, dc = initial_balances.get(cod_antigo, ("0,00", "D"))

                    try:
                        val_float = float(val_str.replace(",", "."))
                    except:
                        val_float = 0.0

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

                st.session_state.i157_dados = "\r\n".join(i157_lines).encode("latin-1", errors="replace")
                st.session_state.i157_processado = True
                st.session_state.i157_has_data = has_i157
                st.rerun()

            if st.session_state.get('i157_processado'):
                st.markdown("---")
                if st.session_state.i157_has_data and pendentes == 0:
                    st.success("✅ Arquivo I157 gerado!")
                    st.download_button(
                        "💾 Baixar I157",
                        data=st.session_state.i157_dados,
                        file_name=f"I157_Saldos_{nome_empresa}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )

                    if os.path.exists("Conjunto I157.xml"):
                        st.markdown("---")
                        with open("Conjunto I157.xml", "rb") as f:
                            st.download_button("⬇️ Baixar Conjunto I157 (XML)", f.read(), "Conjunto I157.xml", "application/xml", use_container_width=True)

                elif pendentes > 0:
                    st.warning("Resolva pendências.")
                else:
                    st.warning("Sem dados.")

        # 4. CONFERÊNCIA E CONFIGURAÇÃO
        with col4:
            st.markdown("**4. Conferência**")
            df_pend = df_origem[~df_origem['cod'].isin(map_final_para_geracao.keys())]
            if not df_pend.empty:
                st.warning(f"{len(df_pend)} pendentes.")
                st.download_button("📑 Relatório CSV", df_pend.to_csv(index=False, sep=';', encoding='utf-8-sig'), "contas_pendentes.csv", "text/csv", use_container_width=True)
            else:
                st.success("✅ Tudo Mapeado OK!")

    else:
        st.error("Nenhuma conta com movimento detectada.")

if 'de_para_map' in st.session_state and len(st.session_state.de_para_map) > 0:
    with placeholder_botao_salvar:
        st.download_button("⬇️ Salvar Progresso Atual", json.dumps(st.session_state.de_para_map, indent=4), "backup_mapeamento_ecd.json", "application/json", help="Baixe para continuar depois.")
else:
    st.info("Aguardando arquivos...")
