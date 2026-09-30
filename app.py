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

# ==========================================
# 1. PARSERS ESPECÍFICOS POR BANCO
# ==========================================

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
            "A - SALDO", "B - SALDO", "C - SALDO",
            "D - SALDO", "E - SALDO", "F - SALDO",
            "A = SALDO", "B = SALDO",
            "A - SALDO DE CONTA", "B - SALDO BLOQUEADO",
            "C - SALDO DISPONIVEL", "D - SALDO EM",
            "BLOQUEIO DIA", "LANÇAMENTO PROVISIONADO",
            "INTERNET BANKING", "CONTA CORRENTE",
            "CENTRAL DE ATENDIMENTO", "SAC", "OUVIDORIA",
            "4004", "0800", "DATA", "HISTÓRICO", "HISTORICO",
            "DOCUMENTO", "VALOR", "SALDO", "TOTAL", "RESUMO",
            "PERIODO", "PERÍODO", "AGÊNCIA", "AGENCIA",
            "V&T", "DATA/HORA",
        ]

        # Termos que indicam linha de zeramento (RESGATE CONTAMAX, APLICACAO CONTAMAX)
        # Essas linhas têm o valor na coluna SALDO, não VALOR — devem ser ignoradas
        IGNORE_HIST_TERMS = [
            "RESGATE CONTAMAX",
            "APLICACAO CONTAMAX",
        ]

        RE_FLAG      = re.compile(r"^[abp]\.?$", re.IGNORECASE)
        RE_DATE_FULL = re.compile(r"^\d{2}/\d{2}/\d{4}$")
        RE_VALUE     = re.compile(r"^-?[\d\.]+,\d{2}$")
        RE_DOC       = re.compile(r"^\d{5,7}$")

        def is_invalid_desc(s):
            return (
                not s
                or re.fullmatch(r"[\d\s/\.]+", s)
                or RE_FLAG.match(s.strip())
            )

        def is_ignore_line(hist):
            hu = hist.upper()
            return any(t in hu for t in IGNORE_HIST_TERMS)

        transactions = []

        if pdf_bytes:
            try:
                # ── Limites de coluna calibrados pelo PDF real ──
                # Inspecionando o PDF do Santander:
                #   Data      ~  55 – 130
                #   Histórico ~ 130 – 400
                #   Documento ~ 400 – 475
                #   Valor     ~ 475 – 575   (coluna "Valor" — vermelho/preto)
                #   Saldo     ~ 575 +        (coluna "Saldo" — ignorada)
                X_DATE_MIN =  50
                X_DATE_MAX = 130
                X_HIST_MIN = 130
                X_HIST_MAX = 400
                X_DOC_MIN  = 400
                X_DOC_MAX  = 475
                X_VAL_MIN  = 475
                X_VAL_MAX  = 575

                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        words = page.extract_words(
                            x_tolerance=3,
                            y_tolerance=3,
                            keep_blank_chars=False,
                            use_text_flow=False,
                        )
                        if not words:
                            continue

                        # Agrupa palavras por linha (Y com tolerância de 3pt)
                        lines_by_y = defaultdict(list)
                        for w in words:
                            y_key = round(w["top"] / 3) * 3
                            lines_by_y[y_key].append(w)

                        # Estado do lançamento em aberto
                        p_date = None
                        p_desc = []
                        p_val  = None          # valor já encontrado mas pending ainda aberto
                        last_saved = [None]    # referência mutável ao último dict salvo

                        def _commit(dt_obj, desc, val_str):
                            """Converte e salva um lançamento."""
                            try:
                                val = float(
                                    val_str.replace(".", "").replace(",", ".")
                                )
                            except ValueError:
                                return
                            entry = {
                                "date_obj":    dt_obj,
                                "amount":      val,
                                "description": desc,
                            }
                            transactions.append(entry)
                            last_saved[0] = entry

                        def save_pending(val_str=None):
                            nonlocal p_date, p_desc, p_val
                            vs = val_str or p_val
                            if not p_date or not p_desc or not vs:
                                p_date = None; p_desc = []; p_val = None
                                return
                            dt_obj = BankParsers._parse_date(p_date)
                            if not dt_obj:
                                p_date = None; p_desc = []; p_val = None
                                return
                            clean = [
                                pt for pt in p_desc
                                if not RE_FLAG.match(pt.strip())
                                and not RE_DOC.match(pt.strip())
                            ]
                            desc = " ".join(clean).strip()
                            if is_invalid_desc(desc):
                                p_date = None; p_desc = []; p_val = None
                                return
                            _commit(dt_obj, desc, vs)
                            p_date = None; p_desc = []; p_val = None

                        def discard_pending():
                            nonlocal p_date, p_desc, p_val
                            p_date = None; p_desc = []; p_val = None

                        # ── Processa cada linha Y ──
                        for y in sorted(lines_by_y.keys()):
                            row = sorted(lines_by_y[y], key=lambda w: w["x0"])

                            date_tokens = []
                            hist_tokens = []
                            doc_tokens  = []
                            val_tokens  = []

                            for w in row:
                                x0, text = w["x0"], w["text"]
                                if X_DATE_MIN <= x0 < X_DATE_MAX:
                                    date_tokens.append(text)
                                elif X_HIST_MIN <= x0 < X_HIST_MAX:
                                    hist_tokens.append(text)
                                elif X_DOC_MIN <= x0 < X_DOC_MAX:
                                    doc_tokens.append(text)
                                elif X_VAL_MIN <= x0 < X_VAL_MAX:
                                    val_tokens.append(text)
                                # x0 >= X_VAL_MAX → coluna Saldo → ignora

                            date_str = " ".join(date_tokens).strip()
                            hist_str = " ".join(hist_tokens).strip()
                            val_str  = " ".join(val_tokens).strip()

                            is_date  = bool(RE_DATE_FULL.match(date_str))
                            is_value = bool(val_str and RE_VALUE.match(val_str))

                            # Remove flags (a/b/p) do histórico
                            if hist_str and RE_FLAG.match(hist_str.strip()):
                                hist_str = ""

                            # Remove número de documento que vazou para hist
                            hist_str = " ".join(
                                t for t in hist_str.split()
                                if not RE_DOC.match(t)
                            ).strip()

                            # Filtra cabeçalhos e rodapés
                            combined = (date_str + " " + hist_str).upper()
                            if any(skip in combined for skip in SKIP_TERMS):
                                discard_pending()
                                continue

                            # Linhas de zeramento (RESGATE/APLICACAO CONTAMAX):
                            # o valor delas fica na coluna Saldo → ignorar
                            if hist_str and is_ignore_line(hist_str):
                                discard_pending()
                                continue

                            # ── Máquina de estados ──

                            if is_date and hist_str and is_value:
                                # Linha completa em uma única Y
                                discard_pending()
                                dt_obj = BankParsers._parse_date(date_str)
                                if dt_obj and not is_invalid_desc(hist_str):
                                    _commit(dt_obj, hist_str, val_str)

                            elif is_date and hist_str and not is_value:
                                # Início de lançamento multi-linha
                                discard_pending()
                                p_date = date_str
                                p_desc = [hist_str]
                                p_val  = None

                            elif is_date and not hist_str and is_value:
                                # Data + valor sem histórico → fecha pending
                                if p_date:
                                    save_pending(val_str)
                                else:
                                    discard_pending()

                            elif is_date and not hist_str and not is_value:
                                # Só data (linha de flag/doc sem texto útil)
                                pass

                            elif not is_date and hist_str and is_value:
                                # Continuação com valor → acumula hist e fecha
                                if p_date:
                                    p_desc.append(hist_str)
                                    save_pending(val_str)
                                else:
                                    # Sem pending: complementa último salvo
                                    if last_saved[0] is not None:
                                        last_saved[0]["description"] += " " + hist_str

                            elif not is_date and hist_str and not is_value:
                                # Linha de continuação de histórico puro
                                if p_date:
                                    p_desc.append(hist_str)
                                elif last_saved[0] is not None:
                                    # Continuação chegou APÓS o valor já ter
                                    # sido salvo → complementa descrição
                                    last_saved[0]["description"] += " " + hist_str

                            elif not is_date and not hist_str and is_value:
                                # Só valor → fecha pending
                                if p_date:
                                    save_pending(val_str)

                        discard_pending()

                if transactions:
                    return transactions

            except Exception:
                transactions = []

        # ── Fallback: parsing por texto puro ──
        RE_DATE_START = re.compile(r"^\d{2}/\d{2}/\d{4}")

        merged = []
        for raw in text_lines:
            s = raw.strip()
            if not s:
                continue
            if any(skip in s.upper() for skip in SKIP_TERMS):
                continue
            if RE_DATE_START.match(s):
                merged.append(s)
            else:
                if merged:
                    merged[-1] += " " + s
                else:
                    merged.append(s)

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
            if any(skip in s.upper() for skip in SKIP_TERMS):
                continue
            if any(t in s.upper() for t in IGNORE_HIST_TERMS):
                continue
            m = PAT.search(s)
            if m:
                dt_str, desc, _doc, val_str = m.group(1, 2, 3, 4)
                desc = desc.strip()
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
            if any(t in s.upper() for t in
                   ["SALDO DA CONTA", "SD CTA/APL", "SALDO ANTERIOR"]):
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
            if any(t in s.upper() for t in
                   ["SALDO ANTERIOR", "S A L D O", "RESUMO"]):
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
            if any(t in s.upper() for t in
                   ["SALDO ANTERIOR", "ULTIMO SALDO"]):
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
            if any(t in s.upper() for t in
                   ["SALDO ANTERIOR", "RENDIMENTO", "TOTAL"]):
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


# ==========================================
# MAPEAMENTO DE BANCOS
# ==========================================

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

# ==========================================
# DETECÇÃO AUTOMÁTICA DE BANCO
# ==========================================

def detect_bank(text_lines):
    header_text = " ".join(text_lines[:40]).upper()

    BANK_SIGNATURES = [
        (
            "Santander (033)", [
                ("SANTANDER", 3),
                ("CONTAMAX", 5),
                ("INTERNET BANKING EMPRESARIAL", 4),
                ("BLOQUEIO DIA", 3),
                ("4004 2125", 4),
                ("0800 702 2125", 4),
            ]
        ),
        (
            "Itaú Unibanco (341)", [
                ("ITAU UNIBANCO", 5),
                ("BANCO ITAU", 4),
                ("ITAÚ UNIBANCO", 5),
                ("ITOKEN", 4),
                ("0300 789 8484", 4),
            ]
        ),
        (
            "Bradesco (237)", [
                ("BANCO BRADESCO", 5),
                ("BRADESCO S.A", 5),
                ("BRADESCO PRIME", 4),
                ("BRADESCO", 3),
                ("0800 704 8383", 4),
            ]
        ),
        (
            "Banco do Brasil (001)", [
                ("BANCO DO BRASIL", 5),
                ("BB.COM.BR", 5),
                ("0800 729 0722", 4),
                ("AGENCIA BB", 3),
                ("AGÊNCIA BB", 3),
            ]
        ),
        (
            "Caixa Econômica Federal (104)", [
                ("CAIXA ECONOMICA FEDERAL", 5),
                ("CAIXA ECONÔMICA FEDERAL", 5),
                ("CEF", 2),
                ("0800 726 0101", 4),
                ("CAIXA.GOV", 4),
            ]
        ),
        (
            "Sicoob (756)", [
                ("SICOOB", 5),
                ("0800 642 2200", 4),
            ]
        ),
        (
            "Sicredi (748)", [
                ("SICREDI", 5),
                ("0800 724 7220", 4),
            ]
        ),
        (
            "Banco Inter (077)", [
                ("BANCO INTER", 5),
                ("INTER S.A", 4),
                ("CONTA DIGITAL INTER", 5),
            ]
        ),
        (
            "Nubank (260)", [
                ("NUBANK", 5),
                ("NU PAGAMENTOS", 5),
                ("NUCONTA", 4),
            ]
        ),
        (
            "C6 Bank (336)", [
                ("C6 BANK", 5),
                ("C6 S.A", 4),
            ]
        ),
        (
            "Banrisul (041)", [
                ("BANRISUL", 5),
                ("BANCO DO ESTADO DO RIO GRANDE", 4),
            ]
        ),
        (
            "Stone Pagamentos (197)", [
                ("STONE PAGAMENTOS", 5),
                ("STONECO", 4),
            ]
        ),
        (
            "Unicred (136)", [
                ("UNICRED", 5),
            ]
        ),
        (
            "Mercado Pago (323)", [
                ("MERCADO PAGO", 5),
                ("MERCADOPAGO", 5),
            ]
        ),
    ]

    scores = {}
    for bank_key, signatures in BANK_SIGNATURES:
        total = sum(
            weight for term, weight in signatures
            if term in header_text
        )
        if total > 0:
            scores[bank_key] = total

    if not scores:
        return None

    return max(scores, key=lambda k: scores[k])


# ==========================================
# GERADOR OFX
# ==========================================

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


# ==========================================
# INTERFACE STREAMLIT
# ==========================================

def fmt_brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


st.title("🏦 Conversor de Extrato PDF para OFX")
st.write(
    "Faça o upload do PDF — o banco será detectado automaticamente. "
    "Você pode corrigir manualmente se necessário."
)

uploaded_file = st.file_uploader(
    "Selecione o arquivo PDF do extrato", type=["pdf"]
)

detected_bank  = None
preview_lines  = []

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
            pdf_bytes = uploaded_file.read()

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
                    f"Nenhum lançamento identificado com o leiaute "
                    f"'{bank_selected}'. Verifique se o PDF contém "
                    f"texto selecionável."
                )
            else:
                transactions.sort(key=lambda x: x["date_obj"])

                pdf_initial     = BankParsers._extract_initial_balance(text_lines)
                initial_balance = (
                    manual_initial_balance
                    if manual_initial_balance != 0.0
                    else pdf_initial
                )

                total_credits = sum(t["amount"] for t in transactions if t["amount"] > 0)
                total_debits  = sum(t["amount"] for t in transactions if t["amount"] < 0)
                final_balance = initial_balance + total_credits + total_debits

                st.markdown("---")
                st.subheader("📊 Resumo Financeiro da Conta")

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Saldo Inicial",       fmt_brl(initial_balance))
                m2.metric("Entradas (Créditos)", fmt_brl(total_credits))
                m3.metric("Saídas (Débitos)",    fmt_brl(abs(total_debits)))
                m4.metric("Saldo Final",          fmt_brl(final_balance))

                ofx_data        = generate_ofx(transactions, bank_code)
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
                        "Data":       t["date_obj"].strftime("%d/%m/%Y"),
                        "Descrição":  t["description"],
                        "Tipo":       "Entrada" if t["amount"] > 0 else "Saída",
                        "Valor (R$)": t["amount"],
                    }
                    for t in transactions
                ])

                def color_amount(val):
                    color = "#28a745" if val > 0 else "#dc3545"
                    return f"color: {color}; font-weight: bold;"

                styled_df = (
                    df.style
                    .map(color_amount, subset=["Valor (R$)"])
                    .format({"Valor (R$)": fmt_brl})
                )

                st.dataframe(styled_df, use_container_width=True, height=400)

        except Exception as e:
            st.error(f"Erro ao processar o PDF: {str(e)}")
