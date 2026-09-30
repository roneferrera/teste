import os
import re
import unicodedata
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
                    return float(
                        match.group(1).replace(".", "").replace(",", "."))
                except ValueError:
                    continue
        return 0.0

    @staticmethod
    def _normalize(text):
        return (
            unicodedata.normalize("NFD", text)
            .encode("ascii", "ignore")
            .decode()
            .upper()
        )

    @staticmethod
    def santander(text_lines, pdf_bytes=None):

        IGNORE_HIST = [
            "RESGATE CONTAMAX",
            "APLICACAO CONTAMAX",
            "APLICAÇÃO CONTAMAX",
            "RESGATE CONTAMAX AUTOMATICO",
            "APLICACAO CONTAMAX AUTOMATICO",
        ]

        SKIP_PARTIAL = [
            "SALDO ANTERIOR", "SALDO DIA", "SALDO BLOQUEADO",
            "SALDO DISPONIVEL", "SALDO EM INVESTIMENTOS",
            "SALDO DE CONTA", "A - SALDO", "B - SALDO",
            "C - SALDO", "D - SALDO", "E - SALDO", "F - SALDO",
            "A = SALDO", "B = SALDO", "BLOQUEIO DIA",
            "LANCAMENTO PROVISIONADO",
            "CENTRAL DE ATENDIMENTO", "SAC", "OUVIDORIA",
            "4004 2125", "0800 702", "0800 726", "0800 762",
            "DAS 8H", "SEGUNDA A SEXTA", "ATENDIMENTO",
            "CANAL EXCLUSIVO", "LIBRAS", "EXTERIOR",
            "A - SALDO DE CONTA", "B - SALDO BLOQUEADO",
            "C - SALDO DISPONIVEL", "D - SALDO EM INVEST",
            "E - SALDO DISPONIVEL", "F - SALDO DISPONIVEL",
        ]

        RE_DATE  = re.compile(r"^\d{2}/\d{2}/\d{4}$")
        RE_VALUE = re.compile(r"^-?[\d]{1,3}(?:\.[\d]{3})*,\d{2}$")
        RE_FLAG  = re.compile(r"^[abpABP]$")
        RE_DOC   = re.compile(r"^\d{4,6}$")

        norm = BankParsers._normalize

        def clean_hist(raw):
            """Colapsa quebras de linha e espaços múltiplos."""
            text = re.sub(r"[\r\n]+", " ", raw)
            text = re.sub(r"\s{2,}", " ", text)
            text = re.sub(r"^[abpABP]\s+", "", text).strip()
            return text

        def is_ignore(hist):
            h = norm(hist)
            return any(norm(s) in h for s in IGNORE_HIST)

        def is_skip(hist):
            h = norm(hist)
            return any(norm(s) in h for s in SKIP_PARTIAL)

        def is_invalid_desc(s):
            if not s:
                return True
            if re.fullmatch(r"[\d\s/\.,-]+", s):
                return True
            if RE_FLAG.fullmatch(s.strip()):
                return True
            return False

        transactions = []

        if not pdf_bytes:
            return transactions

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:

                page_w = pdf.pages[0].width

                # ══════════════════════════════════════════════════
                # PASSO 1 — Detectar coordenadas X das colunas
                # ══════════════════════════════════════════════════
                col_x = {}
                for page in pdf.pages:
                    words = page.extract_words(
                        x_tolerance=3, y_tolerance=3,
                        keep_blank_chars=False, use_text_flow=False,
                    )
                    by_y = defaultdict(list)
                    for w in words:
                        by_y[round(w["top"])].append(w)
                    for y_key in sorted(by_y):
                        row   = by_y[y_key]
                        norms = [norm(w["text"]) for w in row]
                        if "DATA" in norms and "VALOR" in norms:
                            for w in row:
                                n = norm(w["text"])
                                if n in ("DATA", "HISTORICO",
                                         "DOCUMENTO", "VALOR", "SALDO"):
                                    col_x[n] = w["x0"]
                            if len(col_x) >= 4:
                                break
                    if len(col_x) >= 4:
                        break

                if len(col_x) < 4:
                    ratio = page_w / 595.276
                    col_x = {
                        "DATA":      56.7  * ratio,
                        "HISTORICO": 155.9 * ratio,
                        "DOCUMENTO": 388.3 * ratio,
                        "VALOR":     459.2 * ratio,
                        "SALDO":     530.2 * ratio,
                    }

                cols_sorted = sorted(col_x.items(), key=lambda c: c[1])

                def x_range(name):
                    for i, (n, x0) in enumerate(cols_sorted):
                        if n == name:
                            end = (cols_sorted[i + 1][1]
                                   if i + 1 < len(cols_sorted)
                                   else page_w)
                            return (x0 - 2, end - 1)
                    return None

                XD = x_range("DATA")
                XH = x_range("HISTORICO")
                XV = x_range("VALOR")

                if not XD or not XH or not XV:
                    return transactions

                # ══════════════════════════════════════════════════
                # PASSO 2 — Processar cada página usando linhas
                # horizontais reais como delimitadores de célula
                # ══════════════════════════════════════════════════
                for page in pdf.pages:

                    # Coleta linhas horizontais longas (> 30% da página)
                    h_lines = sorted(set(
                        round(l["top"])
                        for l in page.horizontal_edges
                        if l.get("width", 0) > page_w * 0.3
                    ))

                    if len(h_lines) < 2:
                        continue

                    # Detecta y_header e y_footer via palavras da página
                    words_page = page.extract_words(
                        x_tolerance=3, y_tolerance=3,
                        keep_blank_chars=False, use_text_flow=False,
                    )
                    by_y_pg = defaultdict(list)
                    for w in words_page:
                        by_y_pg[round(w["top"])].append(w)

                    y_header_line = None
                    y_footer_line = page.height

                    for y_key in sorted(by_y_pg):
                        row_norms = [norm(w["text"])
                                     for w in by_y_pg[y_key]]
                        joined    = " ".join(row_norms)

                        # Linha de cabeçalho da tabela
                        if "DATA" in row_norms and "VALOR" in row_norms:
                            for hl in h_lines:
                                if hl > y_key:
                                    y_header_line = hl
                                    break

                        # Início do rodapé
                        if y_header_line and any(
                            norm(s) in joined for s in [
                                "SALDO DE CONTA",
                                "SALDO BLOQUEADO",
                                "SALDO DISPONIVEL",
                                "A - SALDO",
                                "B - SALDO",
                                "C - SALDO",
                                "BLOQUEIO DIA",
                                "LANCAMENTO PROVISIONADO",
                                "CENTRAL DE ATENDIMENTO",
                            ]
                        ):
                            for hl in reversed(h_lines):
                                if hl < y_key:
                                    y_footer_line = hl
                                    break
                            break

                    if y_header_line is None:
                        continue

                    # Filtra linhas horizontais na área útil
                    area_lines = [
                        hl for hl in h_lines
                        if y_header_line <= hl <= y_footer_line
                    ]

                    if len(area_lines) < 2:
                        continue

                    # Helper: extrai texto de uma bbox e colapsa \n
                    def cell_text(x_rng, y_top, y_bot):
                        try:
                            crop = page.within_bbox(
                                (x_rng[0], y_top,
                                 x_rng[1], y_bot))
                            t = crop.extract_text(
                                x_tolerance=3,
                                y_tolerance=3) or ""
                            # ── CORREÇÃO PRINCIPAL ──
                            return " ".join(t.split())
                        except Exception:
                            return ""

                    # Processa cada faixa entre duas linhas horizontais
                    for i in range(len(area_lines) - 1):
                        y0 = area_lines[i]
                        y1 = area_lines[i + 1]

                        # Ignora faixas muito finas ou muito largas
                        if y1 - y0 < 4:
                            continue
                        if y1 - y0 > 300:
                            continue

                        date_raw = cell_text(XD, y0, y1)
                        hist_raw = cell_text(XH, y0, y1)
                        val_raw  = cell_text(XV, y0, y1)

                        # Limpa data: remove flag (a/b/p)
                        date_clean = re.sub(
                            r"\s*[abpABP]\s*$", "", date_raw).strip()
                        date_clean = re.sub(
                            r"^[abpABP]\s+", "", date_clean).strip()

                        # Limpa histórico em linha única
                        hist_str    = clean_hist(hist_raw)
                        hist_tokens = hist_str.split()
                        hist_clean  = [
                            t for t in hist_tokens
                            if not RE_DOC.match(t)
                            and not RE_VALUE.match(t)
                            and not RE_FLAG.fullmatch(t)
                        ]
                        hist_str = " ".join(hist_clean).strip()

                        # Primeiro valor numérico válido = lançamento
                        val_str = ""
                        for tok in val_raw.split():
                            if RE_VALUE.match(tok):
                                val_str = tok
                                break

                        # Validações
                        if not RE_DATE.match(date_clean):
                            continue
                        if not val_str:
                            continue
                        if not hist_str:
                            continue
                        if is_skip(hist_str):
                            continue
                        if is_ignore(hist_str):
                            continue
                        if is_invalid_desc(hist_str):
                            continue

                        dt_obj = BankParsers._parse_date(date_clean)
                        if not dt_obj:
                            continue

                        try:
                            val = float(
                                val_str.replace(".", "").replace(",", "."))
                        except ValueError:
                            continue

                        transactions.append({
                            "date_obj":    dt_obj,
                            "amount":      val,
                            "description": hist_str,
                        })

        except Exception:
            import traceback
            traceback.print_exc()
            return []

        return transactions

    # ── Outros bancos ──────────────────────────────────────────────

    @staticmethod
    def itau(text_lines):
        transactions = []
        pattern = re.compile(
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)"
            r"\s+(-?[\d\.]+\,\d{2})\s*([CD])?",
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
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)"
            r"\s+([\d\.]+\,\d{2})\s*([CD])",
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
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)"
            r"\s+(-?[\d\.]+\,\d{2})([\+-])?",
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
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s*(?:\d+)?\s+(.+?)"
            r"\s+([\d\.]+\,\d{2})\s*([CD])",
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
            r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)"
            r"\s+(-?[\d\.]+\,\d{2})\s*([CD])?",
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
    header_norm = (
        unicodedata.normalize("NFD", header_text)
        .encode("ascii", "ignore")
        .decode()
    )
    BANK_SIGNATURES = [
        ("Santander (033)",             [("SANTANDER", 3),
                                         ("CONTAMAX", 5),
                                         ("INTERNET BANKING EMPRESARIAL", 4),
                                         ("BLOQUEIO DIA", 3),
                                         ("4004 2125", 4),
                                         ("0800 702 2125", 4)]),
        ("Itaú Unibanco (341)",         [("ITAU UNIBANCO", 5),
                                         ("BANCO ITAU", 4),
                                         ("ITOKEN", 4),
                                         ("0300 789 8484", 4)]),
        ("Bradesco (237)",              [("BANCO BRADESCO", 5),
                                         ("BRADESCO S.A", 5),
                                         ("BRADESCO PRIME", 4),
                                         ("BRADESCO", 3),
                                         ("0800 704 8383", 4)]),
        ("Banco do Brasil (001)",       [("BANCO DO BRASIL", 5),
                                         ("BB.COM.BR", 5),
                                         ("0800 729 0722", 4),
                                         ("AGENCIA BB", 3)]),
        ("Caixa Econômica Federal (104)",[("CAIXA ECONOMICA FEDERAL", 5),
                                          ("CEF", 2),
                                          ("0800 726 0101", 4),
                                          ("CAIXA.GOV", 4)]),
        ("Sicoob (756)",                [("SICOOB", 5),
                                         ("0800 642 2200", 4)]),
        ("Sicredi (748)",               [("SICREDI", 5),
                                         ("0800 724 7220", 4)]),
        ("Banco Inter (077)",           [("BANCO INTER", 5),
                                         ("INTER S.A", 4),
                                         ("CONTA DIGITAL INTER", 5)]),
        ("Nubank (260)",                [("NUBANK", 5),
                                         ("NU PAGAMENTOS", 5),
                                         ("NUCONTA", 4)]),
        ("C6 Bank (336)",               [("C6 BANK", 5),
                                         ("C6 S.A", 4)]),
        ("Banrisul (041)",              [("BANRISUL", 5),
                                         ("BANCO DO ESTADO DO RIO GRANDE", 4)]),
        ("Stone Pagamentos (197)",      [("STONE PAGAMENTOS", 5),
                                         ("STONECO", 4)]),
        ("Unicred (136)",               [("UNICRED", 5)]),
        ("Mercado Pago (323)",          [("MERCADO PAGO", 5),
                                         ("MERCADOPAGO", 5)]),
    ]
    scores = {}
    for bank_key, signatures in BANK_SIGNATURES:
        total = sum(w for t, w in signatures if t in header_norm)
        if total > 0:
            scores[bank_key] = total
    return max(scores, key=lambda k: scores[k]) if scores else None


def generate_ofx(transactions, bank_code="000"):
    now      = datetime.now().strftime("%Y%m%d%H%M%S")
    dt_start = (transactions[0]["date_obj"].strftime("%Y%m%d")
                if transactions else now)
    dt_end   = (transactions[-1]["date_obj"].strftime("%Y%m%d")
                if transactions else now)
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


# ── UI Streamlit ─────────────────────────────────────────────────

st.title("🏦 Conversor de Extrato PDF para OFX")
st.write("Faça o upload do PDF — o banco será detectado automaticamente.")

uploaded_file = st.file_uploader(
    "Selecione o arquivo PDF do extrato", type=["pdf"])

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
            st.success(
                f"✅ Banco detectado automaticamente: **{detected_bank}**")
        else:
            st.warning(
                "⚠️ Banco não identificado. Selecione manualmente abaixo.")
    bank_selected = st.selectbox(
        "Leiaute do Banco:", options=bank_options, index=default_index)

with col2:
    manual_initial_balance = st.number_input(
        "Saldo Inicial da Conta (R$):",
        value=0.0, step=100.0, format="%.2f")

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

            transactions = (
                parser_func(text_lines, pdf_bytes=pdf_bytes)
                if bank_code in BYTES_AWARE_PARSERS
                else parser_func(text_lines)
            )

            if not transactions:
                with st.expander(
                        "🔍 Debug — linhas extraídas (primeiras 80)"):
                    for i, l in enumerate(text_lines[:80]):
                        st.text(f"{i:03d}: {l}")
                st.error(
                    "Nenhum lançamento identificado. "
                    "Veja o debug acima.")
            else:
                transactions.sort(key=lambda x: x["date_obj"])

                pdf_initial     = BankParsers._extract_initial_balance(
                    text_lines)
                initial_balance = (manual_initial_balance
                                   if manual_initial_balance != 0.0
                                   else pdf_initial)
                total_credits   = sum(t["amount"] for t in transactions
                                      if t["amount"] > 0)
                total_debits    = sum(t["amount"] for t in transactions
                                      if t["amount"] < 0)
                final_balance   = (initial_balance
                                   + total_credits + total_debits)

                st.markdown("---")
                st.subheader("📊 Resumo Financeiro da Conta")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Saldo Inicial",       fmt_brl(initial_balance))
                m2.metric("Entradas (Créditos)", fmt_brl(total_credits))
                m3.metric("Saídas (Débitos)",    fmt_brl(abs(total_debits)))
                m4.metric("Saldo Final",          fmt_brl(final_balance))

                ofx_data = generate_ofx(transactions, bank_code)
                output_filename = (
                    os.path.splitext(uploaded_file.name)[0] + ".ofx")

                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    st.download_button(
                        "📥 Baixar OFX",
                        data=ofx_data,
                        file_name=output_filename,
                        mime="application/x-ofx",
                        type="secondary")
                with col_dl2:
                    csv_data = pd.DataFrame([{
                        "Data":       t["date_obj"].strftime("%d/%m/%Y"),
                        "Descrição":  t["description"],
                        "Tipo":       "Entrada" if t["amount"] > 0
                                      else "Saída",
                        "Valor (R$)": t["amount"],
                    } for t in transactions]).to_csv(
                        index=False).encode("utf-8")
                    st.download_button(
                        "📥 Baixar CSV",
                        data=csv_data,
                        file_name=output_filename.replace(".ofx", ".csv"),
                        mime="text/csv",
                        type="secondary")

                st.markdown("---")
                st.subheader(
                    f"📋 Lançamentos — "
                    f"{len(transactions)} registros encontrados")

                df = pd.DataFrame([{
                    "Data":       t["date_obj"].strftime("%d/%m/%Y"),
                    "Descrição":  t["description"],
                    "Tipo":       "Entrada" if t["amount"] > 0 else "Saída",
                    "Valor (R$)": t["amount"],
                } for t in transactions])

                def color_amount(val):
                    color = "#28a745" if val > 0 else "#dc3545"
                    return f"color: {color}; font-weight: bold;"

                table_height = min(len(df) * 35 + 38, 800)
                st.dataframe(
                    df.style
                      .map(color_amount, subset=["Valor (R$)"])
                      .format({"Valor (R$)": fmt_brl}),
                    use_container_width=True,
                    height=table_height,
                )

                with st.expander("🔍 Debug — lançamentos capturados"):
                    for t in transactions:
                        st.text(
                            f"{t['date_obj'].strftime('%d/%m/%Y')} | "
                            f"{t['amount']:>12.2f} | "
                            f"{t['description']}")

        except Exception as e:
            st.error(f"Erro ao processar o PDF: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
