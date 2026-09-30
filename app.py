import os
import re
from collections import defaultdict
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


class BankParsers:

    @staticmethod
    def _parse_date(dt_str):
        current_year = datetime.now().year
        parts = dt_str.strip().split("/")
        if len(parts) == 2:
            dt_formatted = f"{parts[0]}/{parts[1]}/{current_year}"
        elif len(parts) == 3 and len(parts[2]) == 2:
            dt_formatted = f"{parts[0]}/{parts[1]}/20{parts[2]}"
        else:
            dt_formatted = dt_str.strip()
        try:
            return datetime.strptime(dt_formatted, "%d/%m/%Y")
        except ValueError:
            return None

    @staticmethod
    def _extract_initial_balance(text_lines):
        pattern_saldo = re.compile(
            r"(?:SALDO\s+ANTERIOR|SD\s+CTA/APL|SALDO\s+INICIAL)"
            r"\s*[:\.-]?\s*(-?[\d\.]+\,\d{2})",
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

    @staticmethod
    def santander(text_lines, pdf_bytes=None):

        SKIP_TERMS = [
            "SALDO ANTERIOR", "SALDO DIA", "SALDO BLOQUEADO",
            "SALDO DISPONIVEL", "SALDO DISPONÍVEL",
            "SALDO EM INVESTIMENTOS", "SALDO DE CONTA",
            "A - SALDO", "B - SALDO", "C - SALDO", "D - SALDO",
            "E - SALDO", "F - SALDO", "A = SALDO", "B = SALDO",
            "A - SALDO DE CONTA", "B - SALDO BLOQUEADO",
            "C - SALDO DISPONIVEL", "D - SALDO EM",
            "BLOQUEIO DIA", "LANÇAMENTO PROVISIONADO",
            "INTERNET BANKING", "CONTA CORRENTE",
            "CENTRAL DE ATENDIMENTO", "SAC", "OUVIDORIA",
            "4004", "0800", "DATA", "HISTÓRICO", "HISTORICO",
            "DOCUMENTO", "VALOR", "SALDO", "TOTAL", "RESUMO",
            "PERIODO", "PERÍODO", "AGÊNCIA", "AGENCIA",
            "V&T", "DATA/HORA", "DAS 8H", "ATENDIMENTO",
            "CANAL EXCLUSIVO", "LIBRAS",
        ]

        IGNORE_HIST = [
            "RESGATE CONTAMAX",
            "APLICACAO CONTAMAX",
            "APLICAÇÃO CONTAMAX",
        ]

        RE_FLAG      = re.compile(r"^[abp]\.?$", re.IGNORECASE)
        RE_DATE_FULL = re.compile(r"^\d{2}/\d{2}/\d{4}$")
        RE_VALUE     = re.compile(r"^-?[\d\.]+,\d{2}$")
        RE_DOC       = re.compile(r"^\d{5,6}$")

        def clean(s):
            if not s:
                return ""
            return " ".join(str(s).split()).strip()

        def is_skip(text):
            u = text.upper()
            return any(s in u for s in SKIP_TERMS)

        def is_ignore(text):
            u = text.upper()
            return any(s in u for s in IGNORE_HIST)

        def is_invalid_desc(s):
            return (
                not s
                or re.fullmatch(r"[\d\s/\.,-]+", s)
                or RE_FLAG.match(s.strip())
            )

        transactions = []

        # ══════════════════════════════════════════════════════════
        # ESTRATÉGIA 1 — extract_tables (usa bordas reais da tabela)
        # O Santander gera PDF a partir de HTML com tabela.
        # extract_tables agrupa sub-linhas de cada célula sozinho,
        # resolvendo o histórico quebrado em múltiplas linhas.
        # ══════════════════════════════════════════════════════════
        if pdf_bytes:
            try:
                table_settings = {
                    "vertical_strategy":      "lines",
                    "horizontal_strategy":    "lines",
                    "snap_tolerance":          4,
                    "join_tolerance":          4,
                    "edge_min_length":         5,
                    "min_words_vertical":      1,
                    "min_words_horizontal":    1,
                    "intersection_tolerance":  5,
                }

                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        tables = page.extract_tables(table_settings)

                        if not tables:
                            tables = page.extract_tables({
                                "vertical_strategy":   "lines",
                                "horizontal_strategy": "text",
                                "snap_tolerance":       4,
                            })

                        for table in (tables or []):
                            for row in table:
                                if not row:
                                    continue

                                cells = [clean(c) for c in row]
                                if not any(cells):
                                    continue

                                date_str = ""
                                hist_str = ""
                                val_str  = ""

                                for cell in cells:
                                    if not cell:
                                        continue
                                    if RE_DATE_FULL.match(cell) and not date_str:
                                        date_str = cell
                                    elif RE_DOC.match(cell):
                                        pass
                                    elif RE_FLAG.match(cell):
                                        pass
                                    elif RE_VALUE.match(cell) and not val_str:
                                        val_str = cell
                                    elif (len(cell) > 2
                                          and not re.fullmatch(r"[\d\.,\s]+", cell)
                                          and not hist_str):
                                        hist_str = cell

                                combined = (date_str + " " + hist_str).upper()
                                if is_skip(combined):
                                    continue
                                if hist_str and is_ignore(hist_str):
                                    continue
                                if not date_str or not val_str or not hist_str:
                                    continue
                                if is_invalid_desc(hist_str):
                                    continue

                                dt_obj = BankParsers._parse_date(date_str)
                                if not dt_obj:
                                    continue

                                try:
                                    val = float(
                                        val_str.replace(".", "").replace(",", ".")
                                    )
                                    transactions.append({
                                        "date_obj":    dt_obj,
                                        "amount":      val,
                                        "description": hist_str,
                                    })
                                except ValueError:
                                    pass

                if transactions:
                    return transactions

            except Exception:
                transactions = []

        # ══════════════════════════════════════════════════════════
        # ESTRATÉGIA 2 — extract_text(layout=True)
        # Preserva estrutura colunar. Reagrupa linhas sem data
        # como continuação do lançamento anterior.
        # ══════════════════════════════════════════════════════════
        if pdf_bytes and not transactions:
            try:
                RE_DATE_START = re.compile(r"^\d{2}/\d{2}/\d{4}")
                all_lines = []

                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text(layout=True) or page.extract_text()
                        if text:
                            all_lines.extend(text.split("\n"))

                merged = []
                for raw in all_lines:
                    s = raw.strip()
                    if not s or is_skip(s) or is_ignore(s):
                        continue
                    if RE_DATE_START.match(s):
                        merged.append(s)
                    elif merged:
                        merged[-1] += " " + s

                PAT = re.compile(
                    r"(\d{2}/\d{2}/\d{4})"
                    r"(?:\s+[abp]\.?)?"
                    r"\s+(.+?)"
                    r"\s+(\d{5,6})"
                    r"\s+(-?[\d\.]+,\d{2})"
                    r"(?:\s+-?[\d\.]+,\d{2})?",
                    re.IGNORECASE,
                )

                for line in merged:
                    s = line.strip()
                    if is_skip(s) or is_ignore(s):
                        continue
                    m = PAT.search(s)
                    if m:
                        dt_str, desc, _doc, val_str = m.group(1, 2, 3, 4)
                        desc = clean(desc)
                        if is_invalid_desc(desc):
                            continue
                        dt_obj = BankParsers._parse_date(dt_str)
                        if dt_obj:
                            try:
                                val = float(val_str.replace(".", "").replace(",", "."))
                                transactions.append({
                                    "date_obj":    dt_obj,
                                    "amount":      val,
                                    "description": desc,
                                })
                            except ValueError:
                                pass

                if transactions:
                    return transactions

            except Exception:
                pass

        # ══════════════════════════════════════════════════════════
        # ESTRATÉGIA 3 — text_lines (último recurso)
        # ══════════════════════════════════════════════════════════
        RE_DATE_START = re.compile(r"^\d{2}/\d{2}/\d{4}")
        merged = []
        for raw in text_lines:
            s = raw.strip()
            if not s or is_skip(s) or is_ignore(s):
                continue
            if RE_DATE_START.match(s):
                merged.append(s)
            elif merged:
                merged[-1] += " " + s

        PAT = re.compile(
            r"(\d{2}/\d{2}/\d{4})(?:\s+[abp]\.?)?\s+(.+?)"
            r"\s+(\d{5,6})\s+(-?[\d\.]+,\d{2})(?:\s+-?[\d\.]+,\d{2})?",
            re.IGNORECASE,
        )
        for line in merged:
            s = line.strip()
            if is_skip(s) or is_ignore(s):
                continue
            m = PAT.search(s)
            if m:
                dt_str, desc, _doc, val_str = m.group(1, 2, 3, 4)
                desc = clean(desc)
                if is_invalid_desc(desc):
                    continue
                dt_obj = BankParsers._parse_date(dt_str)
                if dt_obj:
                    try:
                        val = float(val_str.replace(".", "").replace(",", "."))
                        transactions.append({
                            "date_obj":    dt_obj,
                            "amount":      val,
                            "description": desc,
                        })
                    except ValueError:
                        pass

        return transactions

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
                transactions.append({
                    "date_obj": dt_obj, "amount": val,
                    "description": desc.strip()
                })
        return transactions

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
                transactions.append({
                    "date_obj": dt_obj, "amount": val,
                    "description": desc.strip()
                })
        return transactions

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
                transactions.append({
                    "date_obj": dt_obj, "amount": val,
                    "description": desc.strip()
                })
        return transactions

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
                transactions.append({
                    "date_obj": dt_obj, "amount": val,
                    "description": desc.strip()
                })
        return transactions

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
                transactions.append({
                    "date_obj": dt_obj, "amount": val,
                    "description": desc.strip()
                })
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

BYTES_AWARE_PARSERS = {"033"}


def detect_bank(text_lines):
    header_text = " ".join(text_lines[:40]).upper()
    BANK_SIGNATURES = [
        ("Santander (033)",             [("SANTANDER",3),("CONTAMAX",5),("INTERNET BANKING EMPRESARIAL",4),("BLOQUEIO DIA",3),("4004 2125",4),("0800 702 2125",4)]),
        ("Itaú Unibanco (341)",         [("ITAU UNIBANCO",5),("BANCO ITAU",4),("ITAÚ UNIBANCO",5),("ITOKEN",4),("0300 789 8484",4)]),
        ("Bradesco (237)",              [("BANCO BRADESCO",5),("BRADESCO S.A",5),("BRADESCO PRIME",4),("BRADESCO",3),("0800 704 8383",4)]),
        ("Banco do Brasil (001)",       [("BANCO DO BRASIL",5),("BB.COM.BR",5),("0800 729 0722",4),("AGENCIA BB",3),("AGÊNCIA BB",3)]),
        ("Caixa Econômica Federal (104)",[("CAIXA ECONOMICA FEDERAL",5),("CAIXA ECONÔMICA FEDERAL",5),("CEF",2),("0800 726 0101",4),("CAIXA.GOV",4)]),
        ("Sicoob (756)",                [("SICOOB",5),("0800 642 2200",4)]),
        ("Sicredi (748)",               [("SICREDI",5),("0800 724 7220",4)]),
        ("Banco Inter (077)",           [("BANCO INTER",5),("INTER S.A",4),("CONTA DIGITAL INTER",5)]),
        ("Nubank (260)",                [("NUBANK",5),("NU PAGAMENTOS",5),("NUCONTA",4)]),
        ("C6 Bank (336)",               [("C6 BANK",5),("C6 S.A",4)]),
        ("Banrisul (041)",              [("BANRISUL",5),("BANCO DO ESTADO DO RIO GRANDE",4)]),
        ("Stone Pagamentos (197)",      [("STONE PAGAMENTOS",5),("STONECO",4)]),
        ("Unicred (136)",               [("UNICRED",5)]),
        ("Mercado Pago (323)",          [("MERCADO PAGO",5),("MERCADOPAGO",5)]),
    ]
    scores = {}
    for bank_key, signatures in BANK_SIGNATURES:
        total = sum(w for t, w in signatures if t in header_text)
        if total > 0:
            scores[bank_key] = total
    return max(scores, key=lambda k: scores[k]) if scores else None


def generate_ofx(transactions, bank_code="000"):
    now      = datetime.now().strftime("%Y%m%d%H%M%S")
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


def fmt_brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


st.title("🏦 Conversor de Extrato PDF para OFX")
st.write("Faça o upload do PDF — o banco será detectado automaticamente. Você pode corrigir manualmente se necessário.")

uploaded_file = st.file_uploader("Selecione o arquivo PDF do extrato", type=["pdf"])

detected_bank = None
preview_lines = []

if uploaded_file is not None:
    try:
        pdf_bytes_preview = uploaded_file.read()
        uploaded_file.seek(0)
        with pdfplumber.open(io.BytesIO(pdf_bytes_preview)) as pdf:
            for page in pdf.pages[:2]:
                text = page.extract_text()
                if text:
                    preview_lines.extend(text.split("\n"))
        detected_bank = detect_bank(preview_lines)
    except Exception:
        detected_bank = None

col1, col2 = st.columns([2, 1])

with col1:
    bank_options  = list(BANK_MAPPING.keys())
    default_index = (
        bank_options.index(detected_bank)
        if detected_bank and detected_bank in bank_options
        else 0
    )
    if uploaded_file is not None:
        if detected_bank:
            st.success(f"✅ Banco detectado automaticamente: **{detected_bank}**")
        else:
            st.warning("⚠️ Banco não identificado. Selecione manualmente abaixo.")
    bank_selected = st.selectbox(
        "Leiaute do Banco (confirme ou corrija se necessário):",
        options=bank_options,
        index=default_index,
    )

with col2:
    manual_initial_balance = st.number_input(
        "Saldo Inicial da Conta (R$):",
        value=0.0, step=100.0, format="%.2f",
        help="Informe o saldo anterior caso o PDF não o contenha."
    )

if uploaded_file is not None:
    if st.button("Converter para OFX e Exibir Extrato", type="primary"):
        parser_func, bank_code = BANK_MAPPING[bank_selected]
        try:
            pdf_bytes  = uploaded_file.read()
            text_lines = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_lines.extend(text.split("\n"))

            if bank_code in BYTES_AWARE_PARSERS:
                transactions = parser_func(text_lines, pdf_bytes=pdf_bytes)
            else:
                transactions = parser_func(text_lines)

            if not transactions:
                st.error(
                    f"Nenhum lançamento identificado com o leiaute '{bank_selected}'. "
                    f"Verifique se o PDF contém texto selecionável."
                )
            else:
                transactions.sort(key=lambda x: x["date_obj"])

                pdf_initial     = BankParsers._extract_initial_balance(text_lines)
                initial_balance = manual_initial_balance if manual_initial_balance != 0.0 else pdf_initial
                total_credits   = sum(t["amount"] for t in transactions if t["amount"] > 0)
                total_debits    = sum(t["amount"] for t in transactions if t["amount"] < 0)
                final_balance   = initial_balance + total_credits + total_debits

                st.markdown("---")
                st.subheader("📊 Resumo Financeiro da Conta")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Saldo Inicial",       fmt_brl(initial_balance))
                m2.metric("Entradas (Créditos)", fmt_brl(total_credits))
                m3.metric("Saídas (Débitos)",    fmt_brl(abs(total_debits)))
                m4.metric("Saldo Final",          fmt_brl(final_balance))

                ofx_data        = generate_ofx(transactions, bank_code)
                output_filename = os.path.splitext(uploaded_file.name)[0] + ".ofx"

                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    st.download_button(
                        label="📥 Baixar Arquivo OFX",
                        data=ofx_data,
                        file_name=output_filename,
                        mime="application/x-ofx",
                        type="secondary"
                    )
                with col_dl2:
                    csv_data = pd.DataFrame([{
                        "Data":       t["date_obj"].strftime("%d/%m/%Y"),
                        "Descrição":  t["description"],
                        "Tipo":       "Entrada" if t["amount"] > 0 else "Saída",
                        "Valor (R$)": t["amount"],
                    } for t in transactions]).to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="📥 Baixar CSV",
                        data=csv_data,
                        file_name=output_filename.replace(".ofx", ".csv"),
                        mime="text/csv",
                        type="secondary"
                    )

                st.markdown("---")
                st.subheader(f"📋 Lançamentos Extrato — {len(transactions)} registros encontrados")

                df = pd.DataFrame([{
                    "Data":       t["date_obj"].strftime("%d/%m/%Y"),
                    "Descrição":  t["description"],
                    "Tipo":       "Entrada" if t["amount"] > 0 else "Saída",
                    "Valor (R$)": t["amount"],
                } for t in transactions])

                def color_amount(val):
                    return f"color: {'#28a745' if val > 0 else '#dc3545'}; font-weight: bold;"

                # Altura dinâmica: mostra todos sem precisar de scroll
                row_height   = 35
                header_extra = 38
                table_height = min(len(df) * row_height + header_extra, 800)

                st.dataframe(
                    df.style
                      .map(color_amount, subset=["Valor (R$)"])
                      .format({"Valor (R$)": fmt_brl}),
                    use_container_width=True,
                    height=table_height
                )

        except Exception as e:
            st.error(f"Erro ao processar o PDF: {str(e)}")
