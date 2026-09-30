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
                    return float(match.group(1).replace(".", "").replace(",", "."))
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

        # Lançamentos a ignorar completamente
        IGNORE_HIST = [
            "RESGATE CONTAMAX",
            "APLICACAO CONTAMAX",
            "APLICAÇÃO CONTAMAX",
            "RESGATE CONTAMAX AUTOMATICO",
        ]

        # Linhas de saldo/resumo a ignorar
        SKIP_PARTIAL = [
            "SALDO ANTERIOR", "SALDO DIA", "SALDO BLOQUEADO",
            "SALDO DISPONIVEL", "SALDO EM INVESTIMENTOS",
            "SALDO DE CONTA", "A - SALDO", "B - SALDO",
            "C - SALDO", "D - SALDO", "E - SALDO", "F - SALDO",
            "A = SALDO", "B = SALDO", "BLOQUEIO DIA",
            "LANCAMENTO PROVISIONADO",
        ]

        RE_DATE  = re.compile(r"^\d{2}/\d{2}/\d{4}$")
        RE_VALUE = re.compile(r"^-?[\d]{1,3}(?:\.[\d]{3})*,\d{2}$")
        RE_DOC   = re.compile(r"^\d{4,6}$")
        RE_FLAG  = re.compile(r"^[abpABP]$")

        norm = BankParsers._normalize

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

                # ══════════════════════════════════════════════════
                # PASSO 1 — Detectar coordenadas X das colunas
                # lendo a linha de cabeçalho "Data Histórico ..."
                # ══════════════════════════════════════════════════
                col_x = {}

                for page in pdf.pages:
                    words = page.extract_words(
                        x_tolerance=4, y_tolerance=3,
                        keep_blank_chars=False,
                        use_text_flow=False,
                    )
                    by_y = defaultdict(list)
                    for w in words:
                        by_y[round(w["top"])].append(w)

                    for y_key in sorted(by_y):
                        row = by_y[y_key]
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

                # Fallback com coordenadas medidas do PDF real
                if len(col_x) < 4:
                    col_x = {
                        "DATA":      55.0,
                        "HISTORICO": 200.0,
                        "DOCUMENTO": 390.0,
                        "VALOR":     468.0,
                        "SALDO":     560.0,
                    }

                # Monta intervalos [x_start, x_end) para cada coluna
                cols_sorted = sorted(col_x.items(), key=lambda c: c[1])

                def col_range(name):
                    for i, (n, x0) in enumerate(cols_sorted):
                        if n == name:
                            start = x0 - 8
                            end   = (cols_sorted[i + 1][1] - 2
                                     if i + 1 < len(cols_sorted) else 9999)
                            return (start, end)
                    return None

                R_DATE = col_range("DATA")      or (47,   192)
                R_HIST = col_range("HISTORICO") or (192,  388)
                R_DOC  = col_range("DOCUMENTO") or (388,  466)
                R_VAL  = col_range("VALOR")     or (466,  558)
                # Saldo: tudo acima de R_VAL[1]

                # ══════════════════════════════════════════════════
                # PASSO 2 — Processar cada página
                # ══════════════════════════════════════════════════
                for page in pdf.pages:
                    words = page.extract_words(
                        x_tolerance=4, y_tolerance=3,
                        keep_blank_chars=False,
                        use_text_flow=False,
                    )
                    if not words:
                        continue

                    # Agrupa palavras por linha (Y arredondado a 2pt)
                    by_y = defaultdict(list)
                    for w in words:
                        by_y[round(w["top"] / 2) * 2].append(w)

                    sorted_ys = sorted(by_y.keys())

                    # ── Identifica qual coluna cada palavra pertence ──
                    def classify(w):
                        x0 = w["x0"]
                        if R_DATE[0] <= x0 < R_DATE[1]:
                            return "DATE"
                        if R_HIST[0] <= x0 < R_HIST[1]:
                            return "HIST"
                        if R_DOC[0]  <= x0 < R_DOC[1]:
                            return "DOC"
                        if R_VAL[0]  <= x0 < R_VAL[1]:
                            return "VAL"
                        if x0 >= R_VAL[1]:
                            return "SALDO"
                        return "OTHER"

                    # ── Agrupa linhas em blocos de lançamento ──
                    # Um bloco começa quando uma linha tem DATE+VAL
                    # OU quando tem DATE sem VAL (data com hist multilinha).
                    # Linhas sem DATE e sem VAL são continuação do bloco anterior.

                    blocks = []   # cada bloco = lista de y_keys

                    for y in sorted_ys:
                        row = by_y[y]
                        cols_present = {classify(w) for w in row}

                        has_date = (
                            "DATE" in cols_present
                            and any(
                                classify(w) == "DATE"
                                and RE_DATE.match(w["text"])
                                for w in row
                            )
                        )
                        has_val = (
                            "VAL" in cols_present
                            and any(
                                classify(w) == "VAL"
                                and RE_VALUE.match(w["text"])
                                for w in row
                            )
                        )
                        has_hist = "HIST" in cols_present

                        if not blocks:
                            blocks.append([y])
                            continue

                        last_block = blocks[-1]
                        last_y     = last_block[-1]
                        gap        = y - last_y

                        # Linha de continuação: perto, sem data, sem valor
                        is_continuation = (
                            gap <= 35
                            and not has_date
                            and not has_val
                        )

                        if is_continuation:
                            last_block.append(y)
                        else:
                            blocks.append([y])

                    # ── Processa cada bloco ──
                    for block in blocks:
                        all_words = []
                        for y in block:
                            all_words.extend(by_y[y])

                        date_words = []
                        hist_words = []
                        val_words  = []

                        for w in sorted(all_words,
                                        key=lambda x: (x["top"], x["x0"])):
                            col = classify(w)
                            t   = w["text"]

                            if col == "DATE":
                                # Aceita apenas datas reais; ignora flags (a/b/p)
                                if RE_DATE.match(t):
                                    date_words.append(w)

                            elif col == "HIST":
                                # Ignora tokens que são doc ou valor
                                if (not RE_DOC.match(t)
                                        and not RE_VALUE.match(t)
                                        and not RE_FLAG.fullmatch(t)):
                                    hist_words.append(w)

                            elif col == "DOC":
                                pass  # ignora

                            elif col == "VAL":
                                if RE_VALUE.match(t):
                                    val_words.append(w)

                            # SALDO → ignora

                        # Monta strings
                        date_str = " ".join(
                            w["text"] for w in date_words).strip()

                        # Reconstrói histórico linha a linha (preserva ordem Y)
                        hist_by_y = defaultdict(list)
                        for w in hist_words:
                            hist_by_y[round(w["top"] / 2) * 2].append(w)
                        hist_lines = []
                        for hy in sorted(hist_by_y):
                            lw = sorted(hist_by_y[hy], key=lambda x: x["x0"])
                            hist_lines.append(
                                " ".join(w["text"] for w in lw))
                        hist_str = " ".join(hist_lines).strip()

                        # Primeiro valor da coluna VAL = valor do lançamento
                        # (segundo valor, se existir, é o Saldo)
                        val_str = (val_words[0]["text"].strip()
                                   if val_words else "")

                        # ── Validações ──
                        if not RE_DATE.match(date_str):
                            continue
                        if not val_str or not RE_VALUE.match(val_str):
                            continue
                        if not hist_str:
                            continue
                        if is_skip(hist_str):
                            continue
                        if is_ignore(hist_str):
                            continue
                        if is_invalid_desc(hist_str):
                            continue

                        dt_obj = BankParsers._parse_date(date_str)
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


# ── Mapeamento ────────────────────────────────────────────────────

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
                        "🔍 Debug — linhas extraídas do PDF (primeiras 80)"):
                    for i, l in enumerate(text_lines[:80]):
                        st.text(f"{i:03d}: {l}")
                st.error(
                    "Nenhum lançamento identificado. "
                    "Veja o debug acima para diagnóstico.")
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

        except Exception as e:
            st.error(f"Erro ao processar o PDF: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
