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
    def _detect_columns_santander(pdf_bytes):
        """
        Faz uma passagem prévia em todas as páginas do PDF para detectar
        automaticamente as coordenadas X de cada coluna, localizando os
        cabeçalhos: Data, Histórico, Documento, Valor, Saldo.
        Retorna um dict com as bordas de cada coluna.
        """
        HEADER_TERMS = {
            "data":       ["DATA"],
            "historico":  ["HISTÓRICO", "HISTORICO"],
            "documento":  ["DOCUMENTO"],
            "valor":      ["VALOR"],
            "saldo":      ["SALDO"],
        }

        found = {}  # col_name -> x0 do cabeçalho

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

                # Agrupa palavras por linha Y
                lines_by_y = defaultdict(list)
                for w in words:
                    y_key = round(w["top"] / 3) * 3
                    lines_by_y[y_key].append(w)

                # Procura a linha de cabeçalho que contenha pelo menos
                # "DATA" e "VALOR" juntos
                for y in sorted(lines_by_y.keys()):
                    row = lines_by_y[y]
                    texts_upper = [w["text"].upper() for w in row]

                    # Verifica se esta linha é o cabeçalho da tabela
                    has_data  = any(t in ["DATA"] for t in texts_upper)
                    has_valor = any(t in ["VALOR"] for t in texts_upper)

                    if has_data and has_valor:
                        # Encontrou o cabeçalho — mapeia cada coluna
                        for w in row:
                            tu = w["text"].upper()
                            for col, terms in HEADER_TERMS.items():
                                if tu in terms and col not in found:
                                    found[col] = w["x0"]
                        break  # Só precisa da primeira ocorrência

                if len(found) >= 4:
                    break  # Encontrou colunas suficientes

        # Se não encontrou tudo, usa fallback com valores padrão
        defaults = {
            "data":      50,
            "historico": 130,
            "documento": 390,
            "valor":     470,
            "saldo":     570,
        }
        for col, val in defaults.items():
            if col not in found:
                found[col] = val

        # Ordena por x0 para garantir a sequência correta
        cols_sorted = sorted(found.items(), key=lambda x: x[1])

        # Monta bordas: cada coluna vai do seu x0 até o x0 da próxima
        # com uma margem de segurança de 5pt
        col_order = [c[0] for c in cols_sorted]
        col_x0    = {c[0]: c[1] for c in cols_sorted}

        borders = {}
        for i, col in enumerate(col_order):
            x_min = col_x0[col] - 5  # margem esquerda
            if i + 1 < len(col_order):
                x_max = col_x0[col_order[i + 1]] - 5
            else:
                x_max = 9999  # última coluna vai até o fim
            borders[col] = (x_min, x_max)

        return borders

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

        IGNORE_HIST = [
            "RESGATE CONTAMAX",
            "APLICACAO CONTAMAX",
            "APLICAÇÃO CONTAMAX",
        ]

        RE_FLAG      = re.compile(r"^[abp]\.?$", re.IGNORECASE)
        RE_DATE_FULL = re.compile(r"^\d{2}/\d{2}/\d{4}$")
        RE_VALUE     = re.compile(r"^-?[\d\.]+,\d{2}$")
        RE_DOC       = re.compile(r"^\d{5,7}$")

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

        if pdf_bytes:
            try:
                # ── PASSO 1: detecta colunas automaticamente ──
                borders = BankParsers._detect_columns_santander(pdf_bytes)

                X_DATE_MIN, X_DATE_MAX = borders.get("data",      (50,  130))
                X_HIST_MIN, X_HIST_MAX = borders.get("historico", (130, 390))
                X_DOC_MIN,  X_DOC_MAX  = borders.get("documento", (390, 470))
                X_VAL_MIN,  X_VAL_MAX  = borders.get("valor",     (470, 570))
                # Coluna saldo: x >= X_VAL_MAX → ignorada automaticamente

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

                        # ── PASSO 2: agrupa por Y (tolerância fina 3pt) ──
                        raw_lines = defaultdict(list)
                        for w in words:
                            y_key = round(w["top"] / 3) * 3
                            raw_lines[y_key].append(w)

                        # ── PASSO 3: mescla sub-linhas de histórico ──
                        # Sub-linhas do mesmo lançamento ficam a ~10-18pt
                        # de distância e NÃO têm data nem valor próprios.
                        sorted_ys = sorted(raw_lines.keys())
                        groups = []  # lista de (y_ref, [words])

                        for y in sorted_ys:
                            row_words = sorted(raw_lines[y], key=lambda w: w["x0"])

                            has_date = any(
                                X_DATE_MIN <= w["x0"] < X_DATE_MAX
                                and RE_DATE_FULL.match(w["text"])
                                for w in row_words
                            )
                            has_val = any(
                                X_VAL_MIN <= w["x0"] < X_VAL_MAX
                                and RE_VALUE.match(w["text"])
                                for w in row_words
                            )

                            if not groups:
                                groups.append((y, list(row_words)))
                                continue

                            last_y, last_words = groups[-1]
                            gap = y - last_y

                            # Linha de continuação: próxima (≤20pt),
                            # sem data e sem valor → funde ao grupo anterior
                            if gap <= 20 and not has_date and not has_val:
                                hist_words = [
                                    w for w in row_words
                                    if X_HIST_MIN <= w["x0"] < X_HIST_MAX
                                ]
                                last_words.extend(hist_words)
                                groups[-1] = (last_y, last_words)
                            else:
                                groups.append((y, list(row_words)))

                        # ── PASSO 4: processa cada grupo como linha lógica ──
                        p_date = None
                        p_desc = []

                        def save_pending(val_str):
                            nonlocal p_date, p_desc
                            if not p_date or not p_desc or not val_str:
                                p_date = None; p_desc = []
                                return
                            dt_obj = BankParsers._parse_date(p_date)
                            if not dt_obj:
                                p_date = None; p_desc = []
                                return
                            clean = [
                                pt for pt in p_desc
                                if not RE_FLAG.match(pt.strip())
                                and not RE_DOC.match(pt.strip())
                            ]
                            desc = " ".join(clean).strip()
                            if is_invalid_desc(desc):
                                p_date = None; p_desc = []
                                return
                            try:
                                val = float(
                                    val_str.replace(".", "").replace(",", ".")
                                )
                                transactions.append({
                                    "date_obj":    dt_obj,
                                    "amount":      val,
                                    "description": desc,
                                })
                            except ValueError:
                                pass
                            p_date = None; p_desc = []

                        def discard_pending():
                            nonlocal p_date, p_desc
                            p_date = None; p_desc = []

                        for _y, row_words in groups:
                            row = sorted(row_words, key=lambda w: w["x0"])

                            date_tokens = []
                            hist_tokens = []
                            val_tokens  = []

                            for w in row:
                                x0, text = w["x0"], w["text"]
                                if X_DATE_MIN <= x0 < X_DATE_MAX:
                                    date_tokens.append(text)
                                elif X_HIST_MIN <= x0 < X_HIST_MAX:
                                    if (not RE_FLAG.match(text)
                                            and not RE_DOC.match(text)):
                                        hist_tokens.append(text)
                                elif X_DOC_MIN <= x0 < X_DOC_MAX:
                                    pass  # documento ignorado
                                elif X_VAL_MIN <= x0 < X_VAL_MAX:
                                    val_tokens.append(text)
                                # x0 >= X_VAL_MAX → saldo → ignora

                            date_str = " ".join(date_tokens).strip()
                            hist_str = " ".join(hist_tokens).strip()
                            val_str  = " ".join(val_tokens).strip()

                            is_date  = bool(RE_DATE_FULL.match(date_str))
                            is_value = bool(val_str and RE_VALUE.match(val_str))

                            combined = (date_str + " " + hist_str).upper()
                            if is_skip(combined):
                                discard_pending()
                                continue

                            if hist_str and is_ignore(hist_str):
                                discard_pending()
                                continue

                            if hist_str and RE_FLAG.match(hist_str.strip()):
                                hist_str = ""

                            # ── Máquina de estados ──

                            if is_date and hist_str and is_value:
                                discard_pending()
                                dt_obj = BankParsers._parse_date(date_str)
                                if dt_obj and not is_invalid_desc(hist_str):
                                    try:
                                        val = float(
                                            val_str.replace(".", "")
                                                   .replace(",", ".")
                                        )
                                        transactions.append({
                                            "date_obj":    dt_obj,
                                            "amount":      val,
                                            "description": hist_str,
                                        })
                                    except ValueError:
                                        pass

                            elif is_date and hist_str and not is_value:
                                discard_pending()
                                p_date = date_str
                                p_desc = [hist_str]

                            elif is_date and not hist_str and is_value:
                                if p_date:
                                    save_pending(val_str)
                                else:
                                    discard_pending()

                            elif is_date and not hist_str and not is_value:
                                pass

                            elif not is_date and hist_str and is_value:
                                if p_date:
                                    p_desc.append(hist_str)
                                    save_pending(val_str)

                            elif not is_date and hist_str and not is_value:
                                if p_date:
                                    p_desc.append(hist_str)

                            elif not is_date and not hist_str and is_value:
                                if p_date:
                                    save_pending(val_str)

                        discard_pending()

                if transactions:
                    return transactions

            except Exception:
                transactions = []

        # ── Fallback texto puro ──
        RE_DATE_START = re.compile(r"^\d{2}/\d{2}/\d{4}")

        merged = []
        for raw in text_lines:
            s = raw.strip()
            if not s:
                continue
            if is_skip(s):
                continue
            if is_ignore(s):
                continue
            if RE_DATE_START.match(s):
                merged.append(s)
            else:
                if merged:
                    merged[-1] += " " + s

        PAT = re.compile(
            r"(\d{2}/\d{2}/\d{4})"
            r"(?:\s+[abp]\.?)?"
            r"\s+(.+?)"
            r"\s+(\d{5,7})"
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
        ("Santander (033)", [
            ("SANTANDER", 3), ("CONTAMAX", 5),
            ("INTERNET BANKING EMPRESARIAL", 4), ("BLOQUEIO DIA", 3),
            ("4004 2125", 4), ("0800 702 2125", 4),
        ]),
        ("Itaú Unibanco (341)", [
            ("ITAU UNIBANCO", 5), ("BANCO ITAU", 4),
            ("ITAÚ UNIBANCO", 5), ("ITOKEN", 4), ("0300 789 8484", 4),
        ]),
        ("Bradesco (237)", [
            ("BANCO BRADESCO", 5), ("BRADESCO S.A", 5),
            ("BRADESCO PRIME", 4), ("BRADESCO", 3), ("0800 704 8383", 4),
        ]),
        ("Banco do Brasil (001)", [
            ("BANCO DO BRASIL", 5), ("BB.COM.BR", 5),
            ("0800 729 0722", 4), ("AGENCIA BB", 3), ("AGÊNCIA BB", 3),
        ]),
        ("Caixa Econômica Federal (104)", [
            ("CAIXA ECONOMICA FEDERAL", 5), ("CAIXA ECONÔMICA FEDERAL", 5),
            ("CEF", 2), ("0800 726 0101", 4), ("CAIXA.GOV", 4),
        ]),
        ("Sicoob (756)",   [("SICOOB", 5), ("0800 642 2200", 4)]),
        ("Sicredi (748)",  [("SICREDI", 5), ("0800 724 7220", 4)]),
        ("Banco Inter (077)", [
            ("BANCO INTER", 5), ("INTER S.A", 4), ("CONTA DIGITAL INTER", 5),
        ]),
        ("Nubank (260)",   [("NUBANK", 5), ("NU PAGAMENTOS", 5), ("NUCONTA", 4)]),
        ("C6 Bank (336)",  [("C6 BANK", 5), ("C6 S.A", 4)]),
        ("Banrisul (041)", [("BANRISUL", 5), ("BANCO DO ESTADO DO RIO GRANDE", 4)]),
        ("Stone Pagamentos (197)", [("STONE PAGAMENTOS", 5), ("STONECO", 4)]),
        ("Unicred (136)",  [("UNICRED", 5)]),
        ("Mercado Pago (323)", [("MERCADO PAGO", 5), ("MERCADOPAGO", 5)]),
    ]

    scores = {}
    for bank_key, signatures in BANK_SIGNATURES:
        total = sum(w for t, w in signatures if t in header_text)
        if total > 0:
            scores[bank_key] = total

    return max(scores, key=lambda k: scores[k]) if scores else None


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
