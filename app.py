import os
import re
from datetime import datetime
import io
import streamlit as st
import pdfplumber
import pandas as pd

st.set_page_config(
    page_title="Conversor Extrato PDF para OFX",
    page_icon="🏦",
    layout="wide"
)

# ==========================================
# 1. PARSERS ESPECÍFICOS POR BANCO
# ==========================================

class BankParsers:
    @staticmethod
    def _parse_date(dt_str):
        current_year = datetime.now().year
        parts = dt_str.split("/")
        if len(parts) == 2:
            dt_formatted = f"{parts[0]}/{parts[1]}/{current_year}"
        elif len(parts) == 3 and len(parts[2]) == 2:
            dt_formatted = f"{parts[0]}/{parts[1]}/20{parts[2]}"
        else:
            dt_formatted = dt_str
        try:
            return datetime.strptime(dt_formatted, "%d/%m/%Y")
        except ValueError:
            return None

    @staticmethod
    def _extract_initial_balance(text_lines):
        pattern_saldo = re.compile(
            r"(?:SALDO\s+ANTERIOR|SD\s+CTA/APL|SALDO\s+INICIAL)\s*[:\.-]?\s*(-?[\d\.]+\,\d{2})",
            re.IGNORECASE
        )
        for line in text_lines:
            match = pattern_saldo.search(line.strip())
            if match:
                try:
                    return float(match.group(1).replace(".", "").replace(",", "."))
                except ValueError:
                    continue
        return 0.0

    # ----------------------------------------------------------
    # SANTANDER — parser baseado em coordenadas de palavras
    # ----------------------------------------------------------
    @staticmethod
    def santander(text_lines, pdf_bytes=None):
        """
        O extrato Santander Empresarial tem 5 colunas:
            Data | Histórico | Documento | Valor | Saldo

        Estratégia:
          1. Se pdf_bytes disponível → usa extract_words() com coordenadas X
             para separar as colunas por faixa horizontal, eliminando o
             número do documento e o saldo da equação.
          2. Fallback texto puro → regex que captura o nº do documento
             explicitamente e o descarta.
        """
        transactions = []

        # ── MODO COORDENADAS (preferencial) ────────────────────
        if pdf_bytes:
            try:
                # Limites horizontais das colunas (em pontos PDF, página A4 ≈ 595pt)
                # Ajustados empiricamente para o layout do Santander Empresarial:
                #   Data      : x0  0  – x1 100
                #   Histórico : x0 100 – x1 370
                #   Documento : x0 370 – x1 450
                #   Valor     : x0 450 – x1 530
                #   Saldo     : x0 530 – x1 999
                COL_DATE_X1      = 100
                COL_HIST_X0      = 100
                COL_HIST_X1      = 370
                COL_DOC_X0       = 370
                COL_DOC_X1       = 450
                COL_VAL_X0       = 450
                COL_VAL_X1       = 530

                # Padrões de reconhecimento
                re_date  = re.compile(r"^\d{2}/\d{2}/\d{4}$")
                re_value = re.compile(r"^-?[\d\.]+\,\d{2}$")
                re_doc   = re.compile(r"^\d{5,7}$")   # documento: 5-7 dígitos

                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        words = page.extract_words(
                            x_tolerance=3,
                            y_tolerance=3,
                            keep_blank_chars=False
                        )
                        if not words:
                            continue

                        # Agrupa palavras por linha (y0 arredondado a 2pt)
                        from collections import defaultdict
                        lines_by_y = defaultdict(list)
                        for w in words:
                            y_key = round(w["top"] / 2) * 2
                            lines_by_y[y_key].append(w)

                        # Ordena linhas de cima para baixo
                        sorted_ys = sorted(lines_by_y.keys())

                        # Cada entrada pendente: acumula fragmentos de histórico
                        # até encontrar a próxima data com valor
                        pending = None   # dict com date_obj, desc_parts

                        def flush(p):
                            """Finaliza entrada pendente sem valor → descarta."""
                            pass  # sem valor = linha de saldo/cabeçalho

                        for y in sorted_ys:
                            row_words = sorted(lines_by_y[y], key=lambda w: w["x0"])

                            # Classifica cada palavra pela coluna
                            date_words = []
                            hist_words = []
                            val_words  = []

                            for w in row_words:
                                x0 = w["x0"]
                                x1 = w["x1"]
                                text = w["text"]

                                if x1 <= COL_DATE_X1:
                                    date_words.append(text)
                                elif COL_HIST_X0 <= x0 < COL_DOC_X0:
                                    hist_words.append(text)
                                elif COL_DOC_X0 <= x0 < COL_VAL_X0:
                                    pass  # coluna Documento → descartada
                                elif COL_VAL_X0 <= x0 < COL_VAL_X1:
                                    val_words.append(text)
                                # Saldo (x0 >= COL_VAL_X1) → descartado

                            date_str = " ".join(date_words).strip()
                            hist_str = " ".join(hist_words).strip()
                            val_str  = " ".join(val_words).strip()

                            has_date  = bool(re_date.match(date_str))
                            has_value = bool(re_value.match(val_str.replace(".", "").replace(",", "X").replace("X", ",")) 
                                            if val_str else False)
                            # Simplificado:
                            has_value = bool(val_str and re.match(r"^-?[\d\.]+\,\d{2}$", val_str))

                            # Ignora linhas de saldo/cabeçalho sem histórico real
                            skip_terms = ["SALDO ANTERIOR", "SALDO DIA", "TOTAL", "RESUMO",
                                          "Data", "Histórico", "Documento", "Valor", "Saldo"]
                            if any(t.upper() in hist_str.upper() for t in skip_terms):
                                pending = None
                                continue

                            if has_date and hist_str:
                                # Nova linha com data
                                if has_value:
                                    # Linha completa: data + histórico + valor na mesma linha
                                    dt_obj = BankParsers._parse_date(date_str)
                                    if dt_obj:
                                        val = float(val_str.replace(".", "").replace(",", "."))
                                        transactions.append({
                                            "date_obj": dt_obj,
                                            "amount": val,
                                            "description": hist_str
                                        })
                                    pending = None
                                else:
                                    # Histórico quebrado: salva pendente, valor virá depois
                                    pending = {
                                        "date_str": date_str,
                                        "desc_parts": [hist_str]
                                    }
                            elif not has_date and hist_str and pending:
                                # Continuação do histórico quebrado
                                pending["desc_parts"].append(hist_str)
                                if has_value:
                                    # Encontrou o valor: finaliza a entrada
                                    dt_obj = BankParsers._parse_date(pending["date_str"])
                                    if dt_obj:
                                        full_desc = " ".join(pending["desc_parts"])
                                        val = float(val_str.replace(".", "").replace(",", "."))
                                        transactions.append({
                                            "date_obj": dt_obj,
                                            "amount": val,
                                            "description": full_desc
                                        })
                                    pending = None
                            elif has_date and not hist_str and has_value and pending:
                                # Valor aparece em linha separada com a data repetida
                                dt_obj = BankParsers._parse_date(pending["date_str"])
                                if dt_obj:
                                    full_desc = " ".join(pending["desc_parts"])
                                    val = float(val_str.replace(".", "").replace(",", "."))
                                    transactions.append({
                                        "date_obj": dt_obj,
                                        "amount": val,
                                        "description": full_desc
                                    })
                                pending = None
                            else:
                                if has_date:
                                    pending = None  # linha sem histórico e sem valor → ignora

                return transactions

            except Exception as e:
                # Falha no modo coordenadas → cai no fallback
                transactions = []

        # ── FALLBACK: texto puro ────────────────────────────────
        # Regex que captura o nº do documento explicitamente e o descarta:
        # DATA  HISTÓRICO  DOCUMENTO(5-7 dígitos)  VALOR
        re_date_start = re.compile(r"^\d{2}/\d{2}(?:/\d{2,4})?")

        # Passo 1: merge de linhas quebradas
        merged = []
        for line in text_lines:
            s = line.strip()
            if not s:
                continue
            if re_date_start.match(s):
                merged.append(s)
            else:
                if merged:
                    merged[-1] += " " + s
                else:
                    merged.append(s)

        # Passo 2: regex com documento explícito
        # Formato: DATA  HISTÓRICO  DOC(5-7 dígitos)  VALOR
        pat_with_doc = re.compile(
            r"(\d{2}/\d{2}/\d{4})\s+"
            r"(.+?)\s+"
            r"(\d{5,7})\s+"
            r"(-?[\d\.]+\,\d{2})",
            re.IGNORECASE
        )
        # Formato sem documento (ex: TARIFA REGISTRO TITULO 190702 -4,86)
        pat_no_doc = re.compile(
            r"(\d{2}/\d{2}/\d{4})\s+"
            r"(.+?)\s+"
            r"(-?[\d\.]+\,\d{2})$",
            re.IGNORECASE
        )

        skip_terms = ["SALDO ANTERIOR", "SALDO DIA", "TOTAL", "RESUMO"]

        for line in merged:
            s = line.strip()
            if any(t in s.upper() for t in skip_terms):
                continue

            m = pat_with_doc.search(s)
            if m:
                dt_str, desc, _doc, val_str = m.groups()
                dt_obj = BankParsers._parse_date(dt_str)
                if dt_obj:
                    val = float(val_str.replace(".", "").replace(",", "."))
                    transactions.append({
                        "date_obj": dt_obj,
                        "amount": val,
                        "description": desc.strip()
                    })
                continue

            m = pat_no_doc.search(s)
            if m:
                dt_str, desc, val_str = m.groups()
                # Rejeita se "descrição" for só dígitos (número de doc sem valor real)
                if re.fullmatch(r"[\d\s]+", desc.strip()):
                    continue
                dt_obj = BankParsers._parse_date(dt_str)
                if dt_obj:
                    val = float(val_str.replace(".", "").replace(",", "."))
                    transactions.append({
                        "date_obj": dt_obj,
                        "amount": val,
                        "description": desc.strip()
                    })

        return transactions

    # ----------------------------------------------------------
    # ITAÚ
    # ----------------------------------------------------------
    @staticmethod
    def itau(text_lines):
        transactions = []
        pattern = re.compile(
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)\s+(-?[\d\.]+\,\d{2})\s*([CD])?",
            re.IGNORECASE
        )
        for line in text_lines:
            s = line.strip()
            if any(t in s.upper() for t in ["SALDO DA CONTA", "SD CTA/APL", "SALDO ANTERIOR"]):
                continue
            m = pattern.search(s)
            if m:
                dt_str, desc, val_str, tp = m.groups()
                dt_obj = BankParsers._parse_date(dt_str)
                if not dt_obj:
                    continue
                val = float(val_str.replace(".", "").replace(",", "."))
                if tp:
                    val = -abs(val) if tp.upper() == "D" else abs(val)
                transactions.append({"date_obj": dt_obj, "amount": val, "description": desc.strip()})
        return transactions

    # ----------------------------------------------------------
    # BANCO DO BRASIL
    # ----------------------------------------------------------
    @staticmethod
    def banco_do_brasil(text_lines):
        transactions = []
        pattern = re.compile(
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)\s+([\d\.]+\,\d{2})\s*([CD])",
            re.IGNORECASE
        )
        for line in text_lines:
            s = line.strip()
            if any(t in s.upper() for t in ["SALDO ANTERIOR", "S A L D O", "RESUMO"]):
                continue
            m = pattern.search(s)
            if m:
                dt_str, desc, val_str, tp = m.groups()
                dt_obj = BankParsers._parse_date(dt_str)
                if not dt_obj:
                    continue
                val = float(val_str.replace(".", "").replace(",", "."))
                if tp.upper() == "D":
                    val = -abs(val)
                transactions.append({"date_obj": dt_obj, "amount": val, "description": desc.strip()})
        return transactions

    # ----------------------------------------------------------
    # BRADESCO
    # ----------------------------------------------------------
    @staticmethod
    def bradesco(text_lines):
        transactions = []
        pattern = re.compile(
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)\s+(-?[\d\.]+\,\d{2})([\+-])?",
            re.IGNORECASE
        )
        for line in text_lines:
            s = line.strip()
            if any(t in s.upper() for t in ["SALDO ANTERIOR", "ULTIMO SALDO"]):
                continue
            m = pattern.search(s)
            if m:
                dt_str, desc, val_str, signal = m.groups()
                dt_obj = BankParsers._parse_date(dt_str)
                if not dt_obj:
                    continue
                val = float(val_str.replace(".", "").replace(",", "."))
                if signal == "-" or val_str.startswith("-"):
                    val = -abs(val)
                transactions.append({"date_obj": dt_obj, "amount": val, "description": desc.strip()})
        return transactions

    # ----------------------------------------------------------
    # CAIXA
    # ----------------------------------------------------------
    @staticmethod
    def caixas(text_lines):
        transactions = []
        pattern = re.compile(
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s*(?:\d+)?\s+(.+?)\s+([\d\.]+\,\d{2})\s*([CD])",
            re.IGNORECASE
        )
        for line in text_lines:
            s = line.strip()
            if any(t in s.upper() for t in ["SALDO ANTER", "SALDO DIA"]):
                continue
            m = pattern.search(s)
            if m:
                dt_str, desc, val_str, tp = m.groups()
                dt_obj = BankParsers._parse_date(dt_str)
                if not dt_obj:
                    continue
                val = float(val_str.replace(".", "").replace(",", "."))
                if tp.upper() == "D":
                    val = -abs(val)
                transactions.append({"date_obj": dt_obj, "amount": val, "description": desc.strip()})
        return transactions

    # ----------------------------------------------------------
    # GENÉRICO
    # ----------------------------------------------------------
    @staticmethod
    def generic_fallback(text_lines):
        transactions = []
        pattern = re.compile(
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)\s+(-?[\d\.]+\,\d{2})\s*([CD])?",
            re.IGNORECASE
        )
        for line in text_lines:
            s = line.strip()
            if any(t in s.upper() for t in ["SALDO ANTERIOR", "RENDIMENTO", "TOTAL"]):
                continue
            m = pattern.search(s)
            if m:
                dt_str, desc, val_str, tp = m.groups()
                dt_obj = BankParsers._parse_date(dt_str)
                if not dt_obj:
                    continue
                val = float(val_str.replace(".", "").replace(",", "."))
                if tp and tp.upper() == "D":
                    val = -abs(val)
                transactions.append({"date_obj": dt_obj, "amount": val, "description": desc.strip()})
        return transactions


BANK_MAPPING = {
    "Itaú Unibanco (341)":           (BankParsers.itau,            "341"),
    "Bradesco (237)":                 (BankParsers.bradesco,        "237"),
    "Santander (033)":                (BankParsers.santander,       "033"),
    "Banco do Brasil (001)":          (BankParsers.banco_do_brasil, "001"),
    "Caixa Econômica Federal (104)":  (BankParsers.caixas,          "104"),
    "Sicoob (756)":                   (BankParsers.generic_fallback,"756"),
    "Sicredi (748)":                  (BankParsers.generic_fallback,"748"),
    "Banco Inter (077)":              (BankParsers.generic_fallback,"077"),
    "Nubank (260)":                   (BankParsers.generic_fallback,"260"),
    "C6 Bank (336)":                  (BankParsers.generic_fallback,"336"),
    "Banrisul (041)":                 (BankParsers.generic_fallback,"041"),
    "Stone Pagamentos (197)":         (BankParsers.generic_fallback,"197"),
    "Unicred (136)":                  (BankParsers.generic_fallback,"136"),
    "Mercado Pago (323)":             (BankParsers.generic_fallback,"323"),
}

# Bancos cujo parser aceita pdf_bytes
BYTES_AWARE_PARSERS = {"033"}

# ==========================================
# 2. GERADOR OFX
# ==========================================

def generate_ofx(transactions, bank_code="000"):
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    dt_start = transactions[0]["date_obj"].strftime("%Y%m%d") if transactions else now
    dt_end   = transactions[-1]["date_obj"].strftime("%Y%m%d") if transactions else now

    ofx = f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEDAREA:NONE
NEWFILEDAREA:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<DTSERVER>{now}
<LANGUAGE>POR
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>{now}
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<STMTRS>
<CURDEF>BRL</CURDEF>
<BANKACCTFROM>
<BANKID>{bank_code}</BANKID>
<ACCTID>00000000</ACCTID>
<ACCTTYPE>CHECKING</ACCTTYPE>
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>{dt_start}</DTSTART>
<DTEND>{dt_end}</DTEND>
"""
    for idx, tr in enumerate(transactions):
        tr_type = "CREDIT" if tr["amount"] > 0 else "DEBIT"
        dt_str  = tr["date_obj"].strftime("%Y%m%d")
        ofx += f"""<STMTTRN>
<TRNTYPE>{tr_type}</TRNTYPE>
<DTPOSTED>{dt_str}</DTPOSTED>
<TRNAMT>{tr['amount']:.2f}</TRNAMT>
<FITID>{dt_str}{idx+1:04d}</FITID>
<MEMO>{tr['description']}</MEMO>
</STMTTRN>
"""
    ofx += """</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""
    return ofx

# ==========================================
# 3. INTERFACE STREAMLIT
# ==========================================

st.title("🏦 Conversor de Extrato PDF para OFX")
st.write("Selecione o banco, faça o upload do PDF e visualize o resumo financeiro.")

col1, col2 = st.columns([2, 1])
with col1:
    bank_selected = st.selectbox("Selecione o Leiaute do Banco:", options=list(BANK_MAPPING.keys()))
with col2:
    manual_initial_balance = st.number_input(
        "Saldo Inicial da Conta (R$):",
        value=0.0, step=100.0, format="%.2f",
        help="Informe o saldo anterior caso o PDF não o contenha."
    )

uploaded_file = st.file_uploader("Selecione o arquivo PDF do extrato", type=["pdf"])

if uploaded_file is not None:
    if st.button("Converter para OFX e Exibir Extrato", type="primary"):
        parser_func, bank_code = BANK_MAPPING[bank_selected]

        try:
            # Lê os bytes uma única vez
            pdf_bytes = uploaded_file.read()

            # Extrai texto (usado por todos os parsers como base)
            text_lines = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_lines.extend(text.split("\n"))

            # Chama o parser — parsers "bytes-aware" recebem pdf_bytes
            if bank_code in BYTES_AWARE_PARSERS:
                transactions = parser_func(text_lines, pdf_bytes=pdf_bytes)
            else:
                transactions = parser_func(text_lines)

            if not transactions:
                st.error(
                    f"Nenhum lançamento identificado com o leiaute '{bank_selected}'. "
                    "Verifique se o PDF contém texto selecionável."
                )
            else:
                transactions.sort(key=lambda x: x["date_obj"])

                pdf_initial = BankParsers._extract_initial_balance(text_lines)
                initial_balance = manual_initial_balance if manual_initial_balance != 0.0 else pdf_initial

                total_credits = sum(t["amount"] for t in transactions if t["amount"] > 0)
                total_debits  = sum(t["amount"] for t in transactions if t["amount"] < 0)
                final_balance = initial_balance + total_credits + total_debits

                def fmt_brl(v):
                    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                st.markdown("---")
                st.subheader("📊 Resumo Financeiro da Conta")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Saldo Inicial",      fmt_brl(initial_balance))
                m2.metric("Entradas (Créditos)", fmt_brl(total_credits))
                m3.metric("Saídas (Débitos)",    fmt_brl(abs(total_debits)))
                m4.metric("Saldo Final",          fmt_brl(final_balance))

                ofx_data = generate_ofx(transactions, bank_code)
                output_filename = os.path.splitext(uploaded_file.name)[0] + ".ofx"

                st.download_button(
                    label="📥 Baixar Arquivo OFX Gerado",
                    data=ofx_data,
                    file_name=output_filename,
                    mime="application/x-ofx",
                    type="secondary"
                )

                st.markdown("---")
                st.subheader("📋 Lançamentos Extrato (Ordem Cronológica)")

                df = pd.DataFrame([
                    {
                        "Data": t["date_obj"].strftime("%d/%m/%Y"),
                        "Descrição": t["description"],
                        "Tipo": "Entrada" if t["amount"] > 0 else "Saída",
                        "Valor (R$)": t["amount"]
                    }
                    for t in transactions
                ])

                def color_amount(val):
                    color = "#28a745" if val > 0 else "#dc3545"
                    return f"color: {color}; font-weight: bold;"

                styled_df = (
                    df.style
                    .map(color_amount, subset=["Valor (R$)"])
                    .format({"Valor (R$)": lambda x: fmt_brl(x)})
                )
                st.dataframe(styled_df, use_container_width=True, height=400)

        except Exception as e:
            st.error(f"Erro ao processar o PDF: {str(e)}")
