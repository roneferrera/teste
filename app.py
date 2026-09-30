import os
    page_title="Conver
import re
from collectionssor Ext import defaultdict
from datetimerato PDF import datetime para
import O ioFX",
    page_
import streamicon="lit as st
import p🏦",
    layout="wide"dfplumber
import pandas as
) pd


class

st B.set_page_config(ankPars
    page_title="Converers:sor

    @ Extstaticmethod
    def _rato PDF paraparse O_date(dtFX",
    page_icon="_str):
        current🏦",
    layout="_year = datetime.now().wide"year
        parts
) = dt_str.strip


class BankParsers:().split("/")
        if len(parts

    @staticmethod
    def) == 2 _parse:
            dt_date_formatted(dt = f"{parts[0]_str):
        current}/{parts[1]}/{_year = datetime.now().current_year}"
        elifyear
        parts len(parts) == 3 = dt_str.strip ().split("/")
        ifand len len(parts) == 2(parts[2:
            dt]) == 2_formatted:
            dt_formatted = = f"{parts[0] f"{parts[0]}/{}/{parts[1]}/{parts[1]}/current_year}"
        elif20{parts[2]}" len(parts) == 3
        else:
            dt _formatted = dt_str.and lenstrip()
        try(parts[2]) == 2:
            return datetime.str:
            dt_formatted =ptime(dt_formatted, f"{parts[0]}/{ "%d/%m/%Y")parts[1]}/
        except ValueError:
            20{parts[2]}"return None

    @staticmethod
        else:
            dt
    def _extract_initial_formatted = dt_str._balance(textstrip()
        try_:
            return datetime.strlinesptime(dt_formatted,):
        pattern_ "%d/%m/%Y")s
        except ValueErroraldo:
            return None

     = re@staticmethod
    def _.compile(extract_initial_balance(text
            r"(?:_lines):
        patternSALDO\_s+sANTERIORaldo = re|SD.compile(\s+C
            r"(?TA:/SALDO\APs+ANTERIORL|SD|SALDO\s+\s+CINICIALTA)"/
            APr"\Ls*|SALDO\s+[INICIAL:\.-)"]
            r"\?\s*(-s*?[[\d\.:\.-]+\],?\s*(-\?d[\{2})",d\.
            re.IGNORECASE
        )
        for]+\,\ line in text_lines:d{2})",
            match = pattern_saldo
            re.IGNORE.search(line.stripCASE
        )
        for line in text_lines:())
            if match:
                try
            match = pattern_saldo.search(line.strip())
            if match:
                try:
                    :
                    return float(return float(match.group(match.group(1).replace1).replace("(".", "").replace(",", "."))
                except ValueError:.", "").replace(",", ".
                    continue
        return 0.0

    @static"))
                except ValueError:
                    continuemethod
    def santander(
        return 0.0text_lines,

    @staticmethod
     pdfdef sant_bytesander(=textNone):_lines,

         pdfSKIP_bytes_TERMS= = [None):
            "S

        ALDO ANTERIOR", "SKIP_TERMSSALDO D = [IA", "SALDO BLO
            "SALDOQUEADO", ANTERIOR", "SALDO D
            "SALDOIA DISPONIVEL", "SALDO BLO", "SALDO DISPONQUEADO",ÍVEL
            "SALDO DISPON",
            "SALDO IVELEM INVEST", "SALDO DISPONIMENTOSÍVEL", "SALDO DE", CONTA
            "SALDO EM INVEST",
            "A -IMENTOS", "SALDO DE SALDO", "B - CONTA SALDO", "C -",
            "A SALDO", "D - - SALDO",
            " SALDO", "B -E - SALDO", " SALDO", "C -F - SALDO", " SALDO", "D -A SALDO",
            " =E - SALDO", " SALDO", "B =F - SALDO", " SALDO",
            "AA = - SALDO", "B = SALDO DE CONTA", "B - SALDO",
            "A SALDO - BLO SALDO DEQUEADO",
            "C CONTA - SALDO DISPONIVEL", "B - SALDO", "D - SALDO EM", BLOQUEADO",
            "C
            " - SALDO DISPONIVELBLOQUEIO", "D - SALDO EM",
            "BLOQUEIO DIA", "LANÇAMENTO PROV DISIONIA", "LADO",
            "INTERNETANÇAMENTO PROV BANKINGISION", "CONTAADO",
            "INTERNET CORR BANKINGENTE",", "CONTA
            "CENTRAL DE CORR ATENDIMENTO", "SAC", "OUVIDORIA",
            "4ENTE",
            "CENTRAL DE AT004ENDIMENTO", "SA", "0C", "OU800", "DATAVIDORIA",
            "4",004 "HISTÓ", "0RICO", "HISTOR800", "DATAICO",
            "DOCUMENTO",", "VALOR "HISTÓ", "SRICO",ALDO", "TOTAL "HISTOR", "RESUMICO",
            "DOCUMENTOO",
            "PERIODO", "VALOR", "PERÍODO", "", "SAGALDO", "TOTALÊNCIA", "AG", "RESUMENCIAO",
            "PERIODO",
            "V&", "PERÍODO", "AGTÊNCIA", "DATA/", "AGENCIAHORA", "D",
            "V&AS 8T", "DATAH", "/ATHORA", "DENDIMENTO",
            "ASCANAL 8 EXCLUSHIVO", "LIB", "RASAT",
        ENDIMENTO",
            "CANAL EXCLUS]

        IGNORE_HISTIVO", "LIBRAS",
        ]

        IGNORE = [
            "RES_HISTGATE CONTAMAX", = [
            "RES
            "APLICACAO CONTAMAX",
            "APLICGATEAÇÃO CONTAMAX CONTAMAX",
        ]

        RE",_FLAG
            "APLIC      ACAO= re.compile(r" CONTAM^AX",
            "APLIC[abAÇÃOp CONTAMAX",
        ]$", re.IGN]

        REORECASE)
        RE__FLAGDATE      _= re.compile(r"FULL^ = re.compile(r"[abp^\]$d{2}/\d{", re.IGNORECASE2}/\d{4}$")
        RE_VALUE)
        RE_DATE_     = re.compile(rFULL"^ = re.compile(r"-^\?d{2}/\d{[\d\.]+,\d2}/\d{4}{2}$")
        $")
        RE_VALUERE_DOC            = re.compile(r= re.compile(r""^^\-d{5?,[\d\.]+,\d6{2}$")
        }$")

        def joinRE_DO_cell(cC       ):
            """= re.compile(r"^\d{5
            Junta sub,6-linhas de}$")

        def is_skip( umatext célula multi):
            ulinhas do = text.upper()
            return Santander.
             any(s
            O in u for s in SKIP Santander queb_TERMS)

        defra o histórico em sub is_ignore(text):-linhas dentro
            u = text.upper() da
            return any(s in célula. u for s in IGNORE_
            AHIST)

        def is quebra pode_invalid acont_descecer:(s
            1. No):
            return (
                not meio s de uma palavra
                or re:.full "VImatch(r\"[\nVOd\s/ CEL\.ULAR,-"]+", s)
                or → " REV_FLAGIVO CELULAR".match(s. (sem espaço)strip())
            
            2. Entre palavras: ")

        transactionsOUTROS = []\

        ifnBA pdf_bytes:
            tryNCOS:
                with pdfplumber.open(io.Byt" → "OUTROS BANCOS" (comesIO(pdf_bytes)) as pdf: espaço)
            

                    #
            Regra :── se P a última charasso 1: detect da linha anteriora é as letra c Eolunas lendo
                 o ca   abeçalho ── primeira char da pró
                    #xima linha é Proc MAIura a linhaÚSCULA e que
                   a linha contém "Data anterior N",ÃO term "Históina com letrarico", isol
                    # "Documentoada (", "Valor", "Saldo"< 3 para chars), calib
                   então érar os queb Xra no
                    col meio de palavra_bounds → = None sem espaço.
            

                    for page in pdf.Casopages:
                        words contrário → = page.extract_words( com espaço.
            
                            x_tolerance="""
            if not c:5
                return ""
            parts,
                            y_tolerance = [=3p.strip() for p in,
                            keep str_blank_chars=False(c).split("\,
                            usen") if p.strip()]_text_flow=False
            if not,
                         parts:
                return "")
            result
                        # = parts Agr[0]
            for pupa por Y in parts[1:]:
                if not
                        by result_y = defaultdict(list)
                        for w or in words:
                            by not p_y[round:
                    result(w[" += " " + p
                top    "]continue
                last /_char   3= result[-1]
                )first *_char = p[0] 3].append(w)
                #

                        for Última palavra y in sorted(by_y da.keys()):
                            row linha anterior = by_y[y]
                last
                            texts = [w["text"].upper_word =() for w in row]
                            # result.split Linha()[-1] if result.split() else ""
                 de cabeçalho tem# Quebra de DATA e palavra: ambos são letras E VALOR
                            if "DATA" a in texts and "VALOR" última in texts:
                                col palavra_x = {}
                #
                                for w tem <= in row:
                                     2t chars = w["text"].upper() (
                                    if t infoi (" cortDATA", "HISTÓada no meio)RICO", "HISTOR ICO",OU a
                                             "DOCUMENTO primeira", "VALOR", " char
                # daSALDO"):
                                         próxima linha é mincol_x[t] =úscula ( w["x0"]
                continu                ifação de palavra)
                if len ((col_x) >=last_char.isalpha 4() and first:
                                    col__char.isbounds = colalpha()_x
                                    break
                        and (len
                        if col_bounds:
                (last_word) <=             break

                    #2 or first_char. Fallback de coordislower())):
                    result += penadas
                else:
                    
                    if not col_boundsresult += " " + p
            return ":
                        col ".join(result.split())._bounds = {
                            strip()

        def clean"DATA": (s55,):
            if not s: "HISTÓRICO": 140
                return ""
            return ", ".join(str
                            "DOCUMENTO": 390(s).split()).strip()

        , "VALOR": 468def is,_skip(text):
            u "SALDO": 560 = text.upper()
            return any(s in u for s in SKIP,_TERMS)

        def
                        }

                    hk is_ignore(text): = "HISTÓRICO"
            u = text.upper() if "HISTÓRICO" in col_
            return any(s in u for s in IGNORE_bounds else "HISTORICO"HIST)

        def is

                    #_invalid Lim_descites(s de cada):
            return ( coluna (
                notx s_
                or remin.full, x_max)match(r"[\
                    #d\s/ Cada\. coluna vai,- do]+", s)
                or seu RE x_FLAG0.match até o x(s.0strip())
             da próxima -)

        transactions 2 = []pt

        if
                    sorted pdf_bytes:
            # _cols = sorted(col_══bounds.items(), key=lambda════════════════════════════ x: x[1])════════════════════════
                    col_ranges
            # ESTRATÉGIA   = {}1 
                    for i—, (name extract_tables, x0) in enumerate(
            #sorted_cols):
                         Usax bord_min = x0 -as re 8ais da
                        x_max = tabela HTML sorted do Santander._cols[i + 1
            #][1] - 2  Cada célif i + 1 ula multi< len(sorted_cols) elselinhas já  v9em com \999
                        col_rangesn interno[name] = (x_.
            # ══════min, x_max)════════════════════════════

                    X════════════════════
            _DATEtry = col:
                table_ranges._settingsget("DATA", = {       
                    "vertical(_strategy":47     ,"lines  138",
                    "horizontal_))
                    X_strategy":   "lines",HIST = col_ranges.get(
                    "snap_tolerancehk,           ":         4(138,
                    "join, 388_tolerance))
                    X_DO":         C  4,
                    "edge= col_ranges.get("_minDOCUMENTO",_length":        5  (388, 466,
                    "min))
                    X_VA_wordsL  = col_ranges._verticalget("VALOR",      ":     1(466, 558,
                    "min_))
                    #words_horizontal":   1,
                    "intersection SALDO:_tolerance": 5 x >= X,
                }_VAL[

                with pdfplumber.1open(io] →.BytesIO(pdf_ ignorbytes)) as pdf:
                ado    for page in pdf.pages:
                        tables

                    # ── P = page.extract_tables(asso 2: extrai ltableançamentos página_settings) a
                        if not página ──
                    for tables:
                            tables page in pdf.pages: = page.extract_tables({
                        words = page.extract
                                "vertical_strategy_words(
                            x":_tolerance=5,
                               y_tolerance=3,"lines",
                                "
                            keep_blank_horizontal_strategy": "textchars=False,
                            ",
                                "snap_use_text_flow=Falsetolerance":,
                        ) 4,
                            
                        if})

                        for table in not words:
                            continue (

                        # Agrupatables or []):
                             palavforras por Y ( row in table:
                                tolerif not row:
                                ância     continue3pt

                                cells)
                        by_y = [ = defaultdict(list)join
                        for w in words:_cell(c) for c
                            by_y[ in row]

                                ifround(w["top"] / not any 3) * 3].(cellsappend(w)

                        ):
                                    continue#

                                date ── Passo 3:_str = "" ident
                                histifica "_str = ""
                                blovalcos_str  " de lançamento= "" ──
                        #

                                for cell in cells: Cada
                                    if not l cell:
                                        continueançamento tem uma linha â
                                    ifnc REora (com_DATE_FULL.match data e/(cell) and not dateou valor)
                        #_str:
                                         e podedate_str = cell
                 ter lin                    elif RE_DOhas de continuC.match(cell):ação de
                                        pass histó
                                    elif RE_rico logoFLAG abaixo..match(cell):
                
                        #                        pass Estrat
                                    elif RE_égia: vVALUE.match(cell)arre as and not val_str: linhas Y
                                        val_str = em cell
                                    elif ( ordemlen e agr(cell) >upa 2
                        # lin
                                          and nothas consecut reivas que.full pertençmatch(r"[\dam ao\., mesmo lançamento.
                \s]+", cell)        #
                                          and not hist
                        # Uma_str): linha pert
                                        hist_strence ao = cell l

                                combinedançamento anterior = ( se:
                        #date_str +   - Não " " + hist_str). temupper data próp()
                                if is_riaskip(combined):
                                
                        #   - Não    continue
                                if hist tem valor próprio
                        #   - Está_str and a is_ignore(hist_str menos):
                                    continue de 20
                                if notpt da linha date anterior
                        #   _str or not val_str or- Tem not hist_str:
                 texto                    continue na
                                if is_invalid_ coldesc(histuna de histó_str):
                                    ricocontinue

                        sorted

                                dt__ys = sorted(by_yobj = B.keys())

                        #ankParsers._parse_ Mdate(date_str)onta blocos:
                                if not dt_obj cada bl:
                                    continueoco é uma lista

                                try de linhas Y:
                                    val =
                        # que float( pertencem ao mesmo lanç
                                        valamento
                        blocks = []_str.replace("  .", "").replace(",", "# lista.")
                                    ) de l
                                    istastransactions de y_.append({
                                        keys"date_obj

                        for y in sorted":_ys:
                                row_dt_obj,
                                words        "amount = by_y[y]":      val,
                                        "description": hist

                            has_str,
                                    _date = any(
                                X})
                                except ValueError:
                                    pass_DATE[0] <= w["x0"] 

                if transactions< X_DATE[1]:
                    return
                                and RE_DATE_FULL.match(w["text"])
                                for w in row_words
                            )
                             transactionshas_val = any(
                                X

            except Exception:
                transactions = []

            _VAL[0] <=# ══════════════════════════════════════════════════════
            # ESTRAT w["x0"] < XÉGIA 2 — extract_text layout_VAL[1]=
                                and RE_VALUE.True
            # ══════════════════════════════════════════════════════match(w["text"])
            if
                                for w in row_words
                            ) not transactions:
                try:
                    RE
                            has_hist = any(
                                X_DATE_HIST[0] <=_START w["x0"] < X = re.compile(r"_HIST[1]^\d{2}/\d
                                for w in row_words
                            )

                            if{2}/\d{4}") not
                    all_lines blocks = []:
                                blocks.append

                    with pdfplumber([y])
                                .open(io.Bytescontinue

                            lastIO(pdf_bytes)) as_block pdf:
                        for page = blocks[-1] in pdf.pages:
                
                            last_y                 text = page.extract_= lasttext(layout=True)_block[-1] or page
                            gap.extract_text()
                        = y - last_y            if text

                            # É:
                                all_lines continu.extendação se(text.split("\n")):

                    merged pró =ximo [] (
                    for raw in all_lines:
                ≤        s22 = rawpt), sem.strip()
                        if data, not
                            # sem valor, s or is e tem texto_skip(s) no histórico
                            if gap or is_ignore(s): <= 22 and not
                            continue
                         has_date and not has_if RE_DATE_START.val and has_hist:match(s):
                            merged
                                last_block.append(y.append(s)
                )
                                    elif mergedelse:
                                blocks.:append([y])

                        
                            merged[-1]# ── Passo  += " " + s4: proc

                    PAessaT cada = bloco  re.compile(──
                        for block in
                        r"(\ blocks:
                            #d{2}/\d{ Col2}/\d{4}eta)" todas as palav
                        r"(?:\s+[abp])?"
                        r"\s+ras do(. bloco
                            all_words = []
                            for y in block:
                                all_words.extend(+?by_y[y])

                )"
                        r"\            # Seps+(\d{5ara por coluna,6})"
                        
                            dater"\_wordss+(- = []?
                            hist[\d\.]+,\d_words = []
                            {2})"
                        valr"_words  (?:\s+-= []

                            for w? in sorted[\d\.]+,\d(all_words, key={2})?$lambda x: (",x["top
                        re.IGN"], x["x0"])):ORECASE,
                                x
                    )0

                    for line    in merged:
                        s= w["x0"] = line.strip()
                
                                text        if is = w["text"]

                                if_skip(s) or is X_ignore(s):
                _DATE[0] <= x            continue
                        m0 < X_DATE[ = PAT.search1]:
                                    if(s)
                        if not m:
                            dt_ RE_FLAGstr,.match(text):
                                        date_words.append desc,(w _doc)
                                elif X_, val_HIST[0] <= x0str = m.group < X_HIST[(1,1]:
                                    if 2, 3,  not RE_FLAG.match(4)
                            desctext) = clean and not(desc)
                            if RE is_DO_invalid_desc(desc):C.match(text):
                                continue
                            
                                        hist_words.dt_obj = BankPappend(w)
                                arsers._parse_date(elif X_DOdt_str)
                            C[0] <= x0if dt_obj:
                 < X_DOC[                try:
                                    1]:
                                    passval = float(  # ign
                                        val_str.ora documentoreplace(".", "").replace(",
                                elif X_VA", ".")
                                    L[0] <= x0)
                                    transactions. < X_VAL[append({
                                        "1]:
                                    valdate_obj":    dt__words.append(w)obj,
                                        "
                                #amount":      val,
                 x                        "description": desc,0 >= X_VAL
                                    })
                [1] → s                except ValueError:
                                aldo →    pass

                    if transactions ign:
                        return transactionsora

                            # Recon

                except Exception:
                    strói opass histó

        rico respeitando# ══════════════════
                            # queb════════════════════════════ras de linha (════════════j
        # ESTRATÉGIAunta 3 — text palav_linesras da
        # ══════════ mesma════════════════════════════
                            # sub════════════════════
        -linha com esRE_DATEpaço, sub_START = re.compile(-linr"^\d{2}/has entre\d{2}/\d si{4}")
        merged
                            # também = com []
        for raw in text espaço —_lines:
            s = o raw.strip()
            if Santander queb not s or is_skip(ras) or is_ignore(
                            # entres):
                continue
             palavif RE_DATE_START.ras,match(s):
                merged não no.append(s)
             meio de palavelif merged:
                merged[-ras)
                            date_str1] += " " + s = " ".join(w

        PAT = re.["text"] for w in datecompile(
            r"(\_words).d{2}/\d{strip()
                            val2}/\d{4})_str  = " ".join(?(w["text"] for w:\s+[abp]) in val_words).strip()?\s+(.+?)"

                            # Para o
            r"\s+(\ histórico, agrd{5,6})\upa palavs+(-?[\d\.ras por Y
                            #]+,\d{2}) e j(?:\s+-?[\dunta cada\.]+,\d{2 grupo})?$",
            re com espaço
                            .IGNORECASE,hist_by
        )_y = defaultdict(list
        for line in merged:)
                            for w in
            s = line.strip() hist_words:
                                
            if is_skip(hist_by_y[rounds) or is_ignore((w["top"] / s):
                continue
            3) * 3].appendm = PAT.search((w)

                            hists)
            if m:_lines
                dt_str, desc = []
                            for , _doc, val_strhy in sorted(hist_by = m.group(1,_y.keys()):
                                line 2, 3, 4)
                desc = clean_words = sorted(desc)
                if is(hist_by_y[hy],_invalid_desc(desc): key=lambda x: x
                    continue
                dt["x_obj = BankPars0"])
                                hist_ers._parse_date(dtlines.append(" ".join(_str)
                if dtw["text"] for w in_obj:
                    try line_words))

                            :
                        val = floathist(val_str.replace(".", "").replace(",", "._str"))
                        transactions.append = " ".join(hist_lines).strip()

                            #({
                            "date_ Validobj":    dt_obj,ações
                            "amount":      
                            if not REval,
                            "description_DATE": desc,
                        })
                    except ValueError:
                        pass

        return transactions

    @staticmethod_FULL.match(date_str):
                                continue
                            if not val
    def it_str orau(text_lines):
        transactions = []
        pattern not RE_VALUE.match(val_str):
                                 = re.compile(
            continue
                            if not hist_str:
                                continue

                            r"(\d{2}/combined = (\d{2}date_str + " " +(? hist:/_str).upper\d{2,()
                            if is4})?)\s+(._skip(combined):
                +?)\s+(-                continue?[\d\.]+\
                            if is_ignore(,\d{2})\hists*_str):
                                continue([CD
                            if is_invalid_])?desc(hist_str):",
            re.IGN
                                continue

                            dtORECASE_
        )
        for line inobj text_lines:
            s = B = line.strip()
            ankParsers._parse_if anydate(date_str)(t
                            if not dt_obj in s.:
                                continue

                upper() for t in ["            tryS:
                                valALDO = DA float(val_str. CONTA", "SDreplace(" C.", "").replace(",", ".TA/APL", ""))
                                SALDO ANTERIORtransactions"]):
                continue
            .append({
                                    m = pattern.search(s"date_obj":)
            if m:    
                dt_str, desc,dt_obj,
                                 val_str,    "amount tp":      val,
                                 = m.groups    "description": hist()
                dt_str,
                                })_obj = BankPars
                            except ValueError:ers._parse_date(dt
                                pass_str)
                if not

                if dt_obj:
                     transactionscontinue
                val:
                    return = float(val_str. transactions

            replace(".", "").replace(",except Exception:", "."))
                if tp
                transactions: =
                    val []

        # = ── Fall -abs(val)back: texto if tp p.uro ──
        REupper_DATE() == "D_START" else abs = re.compile(r"^\d{2}/\d(val)
                transactions.{2}/\d{4}")append({
                    "date
        merged =_obj": []
        for raw dt_obj, in text "amount": val,
                    "description": desc._lines:
            sstrip()
                })
        return transactions = raw.strip()
            if not

    @staticmethod
     s ordef banco is_do_brasil_skip(s)(text_lines):
         or is_ignore(s):transactions = []
        pattern =
                continue
            if RE re.compile(
            r_DATE_START.match("(\d{2}/\s):
                mergedd{2}(?:/\.append(s)
            d{2,4})?elif)\s+(.+?)\ mergeds+(:[\
                merged[-1] +=d\.]+\ " " + s,\d{2})\

        PAs*([CD])",T =
            re.IGNORE re.compile(CASE
        )
        for
            r"(\ line in text_lines:d{2}/\d{
            s = line.strip()2}/\d{4})
            if any(t in(?:\s+[ s.upper() for t inab ["SALDOp]) ANTERIOR", "S?\s+(. A+? L)" D
            r"\ O", "RESUMs+(\d{5O",6})\s+(-]):
                continue
            m? = pattern.search(s)[\d\.]+,\d
            if m:
                {2})dt_str, desc, val(?:\s+-_str, tp = m.?[\d\.]+,\groups()
                dt_objd{2})?$ = BankParsers._",parse_date(dt_str
            re.IGNORE)
                if not dt_CASE,obj:
                    continue
        )
        for line
                val = float(val_ in merged:
            sstr.replace(".", ""). = linereplace(",", "."))
                .strip()
            if isif tp._skip(s) or isupper() == "D":_ignore(s):
                
                    val = -abs(continue
            mval)
                transactions.append = PAT.search({
                    "date_(s)
            if mobj": dt_obj, ":
                dt_stramount": val,
                    ,"description": desc.strip() desc, _doc
                })
        return transactions,

    @staticmethod
     val_def bradstr = m.groupesco(text_lines):(1,
        transactions = []
        pattern 2, 3,  = re.compile(
            4)
                descr"(\d{2}/\d{2}(?:/\d{2,4} = ")?)\s+(.+?)\s+(-?[\d\.]+\ ".join(desc.split()).,\d{2})([\strip()
                if is+-_invalid_desc(desc):
                    continue
                dt_obj = BankPars])?ers._parse_date(dt_str)
                if dt_obj:
                    try",
            re.IGN:
                        val = float(val_str.replace("ORECASE
        )
        for line in text_lines:.", "").replace(",", "."))
                        transactions.append
            s = line.strip({
                            "date_()
            if any(tobj":    dt_obj, in s.upper() for t
                            "amount":       in ["SALDO ANTERIOR", "val,
                            "descriptionULTIMO": desc,
                        }) SALDO"
                    except ValueError:]):
                continue
            m
                        pass

        return = pattern.search(s) transactions

    @staticmethod
    def it
            if m:
                au(dt_str, desc, valtext_lines):_str, signal = m.groups()
                
        transactionsdt_obj = BankP = []
        patternarsers._parse_date( = re.compile(dt_str)
                if
            r"(\d{2 not dt_obj:
                }/\d{2}    continue
                val = float(?(val_str.replace(":/\d{2,.", "").replace(",", ".4})?)\s+(."))
                if signal ==+?)\s+(- "-?[\d\.]+\",\d{2})\ or vals*_([str.startCDswith("-"):
                    val])? = -abs(val)",
            re.IGN
                transactions.append({
                ORECASE    "date_obj": dt
        )
        for line in_obj, "amount": val text_lines:
            s,
                    "description": = line.strip()
             desc.strip()
                })
        return transactions

    @if any(tstaticmethod
    def c in s.aixupper() for t in ["SasALDO DA(text_lines):
        transactions = []
        pattern = CONTA", "SD re.compile(
            r C"(\d{2}/\TA/APL", "SALDO ANTERIORd{2}(?:/\"d{2,4})?]):
                continue
            m)\s*(? = pattern.search(s):\
            if m:
                ddt_str, desc, val+_str,) tp?\s+(.+?)\ = m.groupss+(()
                dt[\d\.]+\,\_objd{2})\s* = BankParsers._([CD])",
            reparse_date(dt_str.IGNORECASE
        )
                if not)
        for line in text dt_obj:
                    _lines:
            s =continue
                val line.strip()
            if = float(val_str. any(t in s.upperreplace(".", "").replace(",() for t in ["S", "."))
                if tpALDO :ANTER
                    val", "SALDO D = -absIA"(val)]):
                continue
            m if tp.upper = pattern.search(s)() == "D
            if m:
                " else absdt_str, desc, val(val)
                transactions._str, tp = m.append({
                    "dategroups()
                dt_obj_obj": = BankParsers._ dt_obj,parse_date(dt_str "amount": val,)
                if not dt_
                    "description": descobj:
                    continue.
                val = float(val_strip()str.replace(".", "").
                })
        return transactions

    @staticreplace(",", "."))
                method
    def bancoif tp.upper() == "_do_brasilD":
                    val = -abs(val)
                (text_lines):
        transactions = []
        pattern =transactions.append({
                     re.compile(
            r"date_obj": dt_obj, "amount": val,"(\d{2}/\
                    "description": desc.strip()
                })d{2}(?:/\d{2,4})?)\s+(.+?)\
        return transactions

    @staticmethod
    def generics+(_[\d\.]+\fall,\d{2})\back(text_lines):s*([CD])",
        transactions = []
        pattern
            re.IGNORE = re.compile(
            CASE
        )
        forr"(\d{2}/ line in text_lines:\d{2}(?:/
            s = line.strip()\d{2,4}
            if any(t in)?)\s+(.+? s.upper() for t in)\s+(-?[\d ["SALDO\.]+\,\d{ ANTERIOR", "S2})\ As*([CD])? L",
            re.IGN D O", "RESUMORECASE
        )
        O"for line in text_lines:]):
                continue
            m
            s = line.strip = pattern.search(s)()
            if any(t
            if m:
                 in s.upper() for tdt_str, desc, val in ["SALDO ANTERIOR_str, tp = m.", "RENDgroups()
                dt_obj = BankParsers._IMENTO", "TOTAL"]):
                continue
            parse_date(dt_strm = pattern.search(s)
                if not dt_)
            if m:obj:
                    continue
                dt_str, desc,
                val = float(val_ val_str, tp = mstr.replace(".", "")..groups()
                dt_replace(",", "."))
                obj = BankParsersif tp.upper() == "D":._parse_date(dt_str)
                if not dt
                    val = -abs(_obj:
                    continueval)
                transactions.append
                val = float(val({
                    "date__str.replace(".", "obj": dt_obj, "").replace(",", "."))amount": val,
                    
                if tp and"description": desc.strip() tp.upper() == "D
                })
        return transactions":
                    val = -

    @staticmethod
    abs(val)
                transactionsdef brad.append({
                    "esco(text_lines):date_obj": dt_obj
        transactions = []
        pattern, "amount": val, = re.compile(
            
                    "description": desc.r"(\d{2}/strip()
                })
        \d{2}(?:/return transactions\d{2,4})?)\s+(.+?


BANK_MAPPING)\s+ = {
    "(-?[\d\.]+\It,\d{2})(aú[\ Unibanco (+-341])?)":",
            re.IGN           ORECASE
        )
        (BankParsers.itfor line in text_lines:au,
            s = line.strip            ()
            if any(t"341 in s.upper() for t"),
    "Brad in ["SALDO ANTERIOResco (237", "ULTIMO)":                 (Bank SALDO"Parsers.bradesco,]):
                continue
            m         = pattern.search(s)"237"),
    "
            if m:
                Santdt_str, desc, valander (033_str, signal)":                 = m.groups()
                (BankParsers.dt_obj = BankPsantander,       "033"),arsers._parse_date(
    "Bancodt_str)
                if do Brasil (001 not dt_obj:
                )":          (BankParsers.banco_do_    continue
                val = float(val_str.replace("brasil, "001"),
    .", "").replace(",", "."))
                if signal =="Caixa Econômica Federal (104 "-")":  (BankParsers or.caixas,          " val104"),
    "Si_coob (756str.start)":                   (Bankswith("-"):
                    valParsers.generic = -abs(val)_fallback,"
                transactions.append({
                756"),
        "date_obj": dt"Si_obj, "amount": valcredi (748,
                    "description": desc.strip()
                }))":                  (Bank
        return transactions

    @Parsers.generic_fallback,"748"),
    "staticmethod
    def caixBancoas Inter(text_lines):
         (077transactions = []
        pattern =)":              (BankP re.compile(
            rarsers.generic_fallback"(\d{2}/\,"077"),
    "Nud{2}(?:/\bank (260d{2,4})?)":                   (Bank)\s*Parsers.generic_fall(?:\back,"260"),
    "dC+6) Bank?\s+(.+?)\ (336s+()":                  (Bank[\d\.]+\,\Parsers.generic_falld{2})\s*([CD])",
            re.IGNORECASE
        )
        for line in text_lines:
            s =back,"336"),
    " line.strip()
            if any(t in s.upperBanrisul (041)":                 (Bank() for t in ["SParsers.generic_fallback,"041"),
    "ALDO Stone Pagamentos (197ANTER)":         (BankP", "SALDO Darsers.generic_fallbackIA","197"),
    "]):
                continue
            mUnic = pattern.search(s)red
            if m:
                 (136dt_str, desc, val)":                  _str, tp = m.(BankParsers.groups()
                dt_objgeneric_fallback,"136"), = BankParsers._
    "Mercparse_date(dt_strado Pago (323)
                if not dt_)":             obj:
                    continue(BankParsers.
                val = float(val_generic_fallback,"323"),
}str.replace(".", "").replace(",", "."))
                

BYTESif tp.upper() == "_AWARED":
                    val =_PARS -abs(val)
                ERS = {"transactions.append({
                    033"date_obj": dt_"}obj, "amount": val,


def detect
                    "description": desc_bank(text_lines.strip()
                })):
    header
        return transactions

    @static_method
    def generictext_ = " ".join(text_falllines[:40back(text_lines):]).
        transactions = []
        patternupper = re.compile(
            ()
    r"(\d{2}/BANK\d{2}(?:/_SIGNATURES = [\d{2,4}
        (")?)\s+(.+?Sant)\s+(-?[\dander (\.]+\,\d{033)",2})\             s*([CD])?[",
            re.IGN("ORECASE
        )
        SANTANDER",for line in text_lines:3),
            s = line.strip("CONTAM()
            if any(tAX",5 in s.upper() for t),("INTERNET in ["SALDO ANTERIOR", "REND BANKINGIMENTO", "TOTAL EMPRES"]):
                continue
            ARIAL",4),("BLOQUEIO DIA",3),("4m = pattern.search(s)
            if m:004 
                dt_str, desc, val_str, tp = m.groups()
                dt_2obj = BankParsers._parse_date(dt_125str)
                if not dt",4_obj:
                    continue),("0
                val = float(val800 702_str.replace(".", " 2").replace(",", "."))125",4)]),
        
                if tp and("Itaú Un tp.upper() == "Dibanco (341)",         [":
                    val = -("ITAUabs(val)
                transactions UNIBANCO",5.append({
                    "),("BANCOdate_obj": dt_obj ITAU, "amount": val,",4),("ITA
                    "description": desc.Ú UNIBANCO",5strip()
                })
        ),("Ireturn transactionsTOKEN",4),("0


BANK300_MAPPING 789 = {
    " 8It484aú",4)]),
        (" Unibanco (Bradesco (237)",              341[("BANCO)":            BRADESCO",5),("BRADESCO S(B.A",5ankParsers.itau),("BRAD,            ESCO PRIME",4"341),("BRADESCO","),
    "Brad3esco (237),("0)":                 (Bank800 704Parsers.bradesco, 8        383"237"),
    "",4)]),
        ("Banco do Brasil (001)",       [("BANCO DO BRASIL",5),("BBSant.COMander (033.)":                (BankParsers.santander,       "033"),BR",5),("0
    "Banco do Brasil (001)":          (BankParsers.800 729banco_do_brasil, "001"),
    "C 0aixa Econ722ômica Federal (104",4),)":("AGENCIA  (BankParsers BB.caixas,          ",3"104"),
    "),("SiAGcoob (756ÊNCIA)":                    BB",3)(BankParsers.]),
        ("Caigenericxa Econômica Federal (_fallback,"104)"756"),
    ,[("CAIXA"Si ECONOMcrICA FEDERAL",5),("edi (748CAIXA)":                  (Bank ECONParsers.generic_fallÔMICA FEDERAL",5),back,"748"),
    "("CEBancoF",2 Inter),("0800 726 (077 0101)":              ",4),(BankParsers.("Cgeneric_fallback,"077"),AIXA.
    "NuGObank (260V",)":                   (Bank4Parsers.generic_fall)]),
        ("Siback,"260"),
    "coob (756)",                C[("SICOOB",65),("0 Bank800 642 (336 2)":                  (Bank200Parsers.generic_fall",4)back,"336"),
    "]),
        ("SicrBanedi (748)",               [("risul (041SICREDI",5),)":                 (Bank("0800 724Parsers.generic_fall 7back,"041"),
    "220Stone",4)]),
        ("Banco Inter (077)",            Pag[("BANCO INTER",amentos (1975),("INTER)":          S(BankParsers..A",4generic_fallback,"197"),),("CONTA
    "Unic DIGITALred (136 INTER",5)":                  (Bank)Parsers.generic_fall]),
        ("Nubankback,"136"),
    " (260)",                [("MercNUBANK",5),("ado Pago (323NU PAG)":             (BankPAMENTOS",5arsers.generic_fallback),("NUCONTA,"323"),
}",4)

BYTES]),
        ("C6 _AWAREBank (336)",               [("_PARSC6 BANK",5ERS = {"),("C6 S033.A",4"})


def detect]),
        ("Banris_bank(text_lines):ul (041)",              
    header[("BANRISUL",_5),("BANCOtext DO = " ESTADO ".join(text_lines[:40 DO R]).IO GRANDE",4upper)]),
        ("Stone()
     Pagamentos (197)",      [("STONE PAGAMENTOSBANK",5),("STON_SIGNATURES = [
        ("ECO",4)]),
        ("SantUnicred (136)",               ander ([("UNICRED",5033)",)             ]),
        ("Mercado[ Pago (323)",          ("SANTANDER",[("MERCADO P3AGO",5),("MERC),AD("CONTAMOPAGO",5)]),AX",5
    ]
    scores),("INTERNET = {}
    for bank_key BANKING, signatures in BANK_ EMPRESSIGNATURES:
        totalARIAL",4 =),("BLO sumQUEIO DIA",3(w), for t("4004 , w in signatures if t in2 header_text)
        if125 total > 0:
            ",4scores[bank_key] =),("0800  total
    return702 max 2(scores, key=lambda k125",4)]),
        : scores[k]) if scores("Itaú Unibanco (341)",         [ else None


def generate_of("ITAUx(transactions UNIBANCO",5, bank_code),("BANCO=" ITAU",4),("000ITA"):
    nowÚ UNIBANCO",5      ),("I= datetime.now().TOKENstrftime("%Y%",4),("0m%d%300H%M%S") 789
    dt 8_start484 = transactions",4)]),
        ("[0]["date_obj"].Bradesco (237)",              strftime("%Y%m%[("BANCOd") BRADESCO",5),(" if transactions else nowBRADESCO S
    dt_end   =.A", transactions[-1]["date_obj"].strftime("%Y%m%d") if transactions else now
    ofx =5),("BRADESCO f""" PRIME",4),("BRADOFXHEADER:100ESCO",
DATA3:OFXSGML),("0
VERSION:102
SECURITY:800 704NONE
ENCODING: 8USASCII
CHARSET:3831",4)]),
        ("252
COMPRESSION:NONEBanco
OLDFI do Brasil (001)",       [LED("BANCO DO BRASIL",AREA5),("BB:NONE.
NEWFILEDAREA:COMNONE.BR",5

<OFX>),("0
<SIG800 729NONMSGSRSV1> 0722
<SONRS>",4),
<STATUS>
<CODE>("0AG
<SEVERITY>INFOENCIA
</STATUS>
<DTSERVER BB>{now",3}),("
<LANGUAGE>PAGORÊNCIA BB",3)
</SON]),
        ("CaiRS>xa Econômica Federal (104)"
</SIGNONMSGSRSV1,[("CAIXA>
<BANKMS ECONOMGSRSV1>ICA FEDERAL",5),("
<STMTTRNRS>C
<TRNUID>{AIXAnow} ECONÔMICA FEDERAL",5
<STATUS>
<CODE),("CE>0
<SEVERITY>F",2INFO
</STATUS>),("0800 726
<ST 0101MTRS>
<CURDEF>B",4),("CAIXA.RLGO</CURDEF>V",
<BANKACCTFROM>4
<BANKID>{bank_)]),
        ("Sicoob (756)",                code}[("SICOOB",</BANKID>5),("0
<ACCTID>800 64200000000 2200</ACCTID>",4)
<ACCTTYPE>CHECKING]),
        ("Sicr</ACCTTYPE>edi (748)",               [("
</BANKSICREDI",5),ACCTFROM>("0800 724
<BAN 7KTRANLIST>220
<DT",4)]),
        ("Banco Inter (077)",           [("BANCO INTER",5),("INTER S.A",4START>{dt_start}),("CONTA DIGITAL</DTSTART>
<DTEND>{dt_end}</DTEND>
"""
    for idx INTER",5, tr in enumerate(transactions):
        tr_)type = "]),
        ("NubankCREDIT" if tr["amount (260)",                [(""] > 0 else "NUBANK",5),("DEBIT"
        dt_str  NU PAGAMENTOS",5= tr["date_obj"].),("NUCstrftime("%Y%m%ONTAd")",4)
        ofx += f"""]),
        ("C6 <STMTTRNBank (336)",               [(">
<TRNTYPEC6 BANK",5>{tr_type}</T),("C6 SRNTYPE>
<DT.A",4POSTED>{dt_str})</DTPOSTED>]),
        ("Banris
<TRNAMT>{tr['ul (041)",              amount']:.[("BANRISUL",2f}</TRNAMT5),("BANCO>
<FITID>{ DOdt ESTADO DO_str}{idx+ R1:IO GRANDE",044)]),
        ("Stoned}</FITID> Pagamentos (197)",      [("STONE PAGAMENTOS
<MEMO",5),("STON>{tr['description']}ECO</MEMO>
</STM",4)]),
        ("TTRN>
"""Unicred (136)",               
    of[("UNICRED",5x += """)</BAN]),
        ("MercadoKTRANLIST> Pago (323)",          
</STMTRS>[("MERCADO P
</STAGO",5),("MERCMTTRNRS>ADOPAGO",5)]),
</BANK
    ]
    scoresMSGSRSV1> = {}
    for bank_key
</OFX>"""
    , signaturesreturn ofx


def fmt in BANK_SIGNATURES:_b
        totalrl(v =):
    return sum f"R$ {v:(w,.2f} for".replace(",", "X t")., w in signatures if t inreplace(".", ","). header_text)
        ifreplace("X", ".") total >


st 0:
            scores[.titlebank_key] = total("
    return🏦 Conversor de max Ext(scores, key=lambdarato PDF k: scores[k]) if para scores else None


def generate O_ofFX")
st.write("Faça o upload do PDF —x( o banco será detectado automaticamente.transactions, bank_code Você pode cor="000rigir man"):
    now      ualmente se necessário.")= datetime.now().strftime("%Y%m%d%H%M%S")

uploaded
    dt_file = st.file__start = transactions[0]["date_obj"].uploader("Selecionestrftime("%Y%m% o arquivo PDF dod") ext if transactions else now
    dtrato", type=["pdf"])

detected_end   = transactions[-1_bank = None
preview]["date_obj"].strftime_lines("%Y%m%d") = []

if uploaded_file if transactions else now
    of isx = not None:
    try: f"""OFX
        pdfHEADER:100
DATA_bytes_preview:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING: = uploaded_file.read()
        uploadedUSASCII
CHARSET:_file.seek(0)1
        with252
COMPRESSION:NONE pdfplumber.open(
OLDFIio.BytesIO(pdfLED_bytes_preview)) as pdfAREA:NONE:
            for page in pdf.pages[:
NEWFILEDAREA:2NONE]:
                text = page.extract_text()

<O
                if text:
                FX>    preview_lines.extend
<SIGNONMSGSRSV1>(text.split("\n"))
<SONRS>
        detected_bank = detect
<STATUS>
<CODE>_bank(preview_lines)0
    
<SEVERITY>INFOexcept Exception:
        detected
</STATUS>
<DTSERVER_bank = None

col>{now}1, col2 = st
<LANGUAGE>P.columns([2OR, 1])

with col1:
    bank
</SON_optionsRS>  
</SIGNONMSGSRSV= list(BANK_1>
<BANKMSMAPPING.keys())
    defaultGSRSV1>_index
<STMTT = (RNRS>
<TRNUID>{
        banknow}_options.index(detected_bank)
<STATUS>
<CODE
        if detected_bank and>0
<SEVERITY> detected_bank in bankINFO
</STATUS>_options
        else 0
<ST
    )
    ifMTRS> uploaded
<CURDEF>BRL</CURDEF>_file is not None:
        if detected_bank:
            st
<BANKACCTFROM>.success
<BANKID>{bank_(f"code}✅ Banco detectado automat</BANKID>icamente: **
<ACCTID>{detected_bank}**")00
        else:
            st000000</ACCTID>.warning("⚠️ Banco não identific
<ACCTTYPE>CHECKINGado. Sel</ACCTTYPE>ecione manualmente ab
</BANKACCTFROM>aixo.")
    bank
<BAN_selectedKTRANLIST> = st.selectbox(
<DTSTART>{dt_start}
        "Le</DTSTART>iaute do Banco (
<DTEND>{dt_end}confir</DTEND>
"""me ou
    for idx corr, trija se in enumerate(transactions):
         necessário)tr:",
        options=bank__options,
        index=defaulttype_index,
     = "CREDIT" if tr)["amount"] > 0 

with col2:
    manualelse "DEBIT"_initial
        dt__str  balance= tr["date_obj"]. = st.number_input(strftime("%Y%m%
        "Saldod") Inicial da
        ofx += f""" Conta (R$)<STMTTRN:",
        value=0.>
<TRNTYPE0,>{tr_type}</T step=100RNTYPE>
<DT.0, formatPOSTED>{dt_str}="%.2f",
        </DTPOSTED>help="Inf
<TRNAMT>{tr['orme o samount']:.aldo anterior2f}</TRNAMT caso>
<FITID>{ o PDFdt não o_str}{ contenidx+ha."1:
    )

if uploaded04_file is not None:d}</FITID>
    if st.button("
<MEMOConverter para OFX e>{tr['description']} Ex</MEMO>
</STMibirTTRN>
""" Ext
    ofrato", type="primary"):x += """
        parser</BAN_KTRANLIST>func
</STMTRS>, bank
</STMTTRNRS>_code = BANK_MAPPING[bank_selected]
</BANK
        tryMSGSRSV1>:
            pdf_bytes  = uploaded_file.read()
</OFX>"""
    return ofx


def fmt
            text_lines = []_brl(v
            with):
    return pdfplumber.open( f"R$ {v:io.BytesIO(pdf_bytes)) as pdf:,.2f}".replace(",", "X").
                for page in pdf.pagesreplace(".", ",").:
                    text = page.extract_text()
                replace("X", ".")    if text:
                        


sttext_lines.extend(text.title.split("\n"))("

            if🏦 Conver banksor de Ext_code inrato PDF para BYTES_AWARE_ OPARSERS:
                transactions =FX")
st.write parser_func(text_lines,("Fa pdfça o upload do_bytes= PDF —pdf_bytes)
            else o banco:
                transactions = parser_ seráfunc(text_lines) detectado automaticamente.")

            if not

uploaded transactions:
                st.error_file = st.file_(uploader("Selecione o arquivo PDF do
                    f"Nenh extrato", type=["pdfum"])

detected lanç_bank = None
previewamento identific_linesado com = [] o le

if uploaded_file isiaute '{ not None:
    try:bank_selected}'. "
        pdf
                    f_bytes"Verifique se o_preview PDF contém texto = uploaded selecionável_file.read()."
                )
            
        uploaded_file.seek(0)else:
                transactions.
        with psort(key=lambda x: x["date_obj"])dfplumber.open(io.BytesIO(pdf_

                pdfbytes_preview)) as pdf:_initial
            for page      in pdf.pages[:= B2ankParsers._extract_initial]:
                text_balance(text = page.extract_text()
                if text:
                _lines)
                initial    preview_lines.extend_balance = manual(text.split("\n"))_initial_balance if manual_
        detected_bank = detectinitial_balance !=_bank(preview_lines) 0.
    0 else pdf_initialexcept Exception:
                total
        detected_credits_bank = None

col   = sum(t["amount1, col2 = st"] for t in transactions if.columns([2, 1])
with col1:
    bank t["amount"] > 0)
                total_debits    _options= sum(t["amount"]   for t in transactions if t["= list(BANK_amount"] < 0)
                finalMAPPING.keys())
    default_index_balance   = initial_balance = + total_credits + ( total_debits

                stbank_options.index(detected.markdown_bank) if detected_bank(" and---")
                st.sub detected_bank in bankheader("📊 _options else 0)Resumo
    if uploaded_file is not None:
        if Financeiro da detected_bank:
            st. Conta")
                m1, m2,success m3, m4 = st.columns(4)
                m(f"✅ Banco detectado automat1.metric("Saldo Inicial",icamente: **       {detected_bank}**")fmt_brl(initial_
        else:
            stbalance))
                m2..warning("⚠️metric("Ent Banco não identificradas (ado. SelCréditosecione man)", fmt_brl(totalualmente ab_credits))
                m3aixo.")
    bank.metric("Saídas_selected (Débitos)",    fmt = st.selectbox("_brl(absLe(total_debits)))ia
                m4.metric("ute doSaldo Final",           Banco:",fmt_brl(final_ optionsbalance))

                of=bank_options, index=x_default_index)data

with col2:
    manual        _initial= generate_ofx(transactions_, bank_code)
                balanceoutput = st.number_input("_filenameSaldo Inicial da = os Conta (R$).path.split:", valueext(uploaded_file.name=0.0, step=)[0] + ".ofx100".0,

                col format_="%.2f")dl

if uploaded_file is not None1:
    if, col_dl2 = st st.columns(2).button("
                with col_dl1:Converter para OFX e
                    st.download_ Exbutton(
                        label="ibir📥 Baixar Ext Arquivorato", type="primary"): OFX",
                        
        parser_func,data=ofx_data,
                        file_name=output_filename,
                        mime="application/x bank_code = BANK_-ofx",
                        MAPPING[bank_selected]type
        try="secondary:
            pdf"
                    )
                with_bytes  = uploaded_file.read() col_dl2:
                
            text    csv_lines = []_data = pd
            with.DataFrame([{
                         pdfplumber.open("Data":io.BytesIO(pdf_bytes)) as pdf:       
                for page in pdf.pagest["date_obj"].strftime:
                    text = page("%d.extract_text()
                /%m/%Y"),
                    if text:
                                "Descrição":  t["description"],
                        "Tipo":       "Entradatext_lines.extend(text" if t["amount"] > 0 else "Sa.split("\n"))

            transactions = parserída",
                        "_func(text_lines, pdfValor (_bytes=pdf_bytes) if bankR$)":_code in t BYTES_AWARE_PARSERS else parser_func(text_lines)["amount"],
                    }

            if not for t in transactions]). transactions:
                st.errorto_csv(index=False("Nenhum). lencodeançamento identific("utf-8")
                ado.    st.download_button( Verifique se o PDF
                        label="📥 contém texto Baixar CSV", s
                        data=csv_dataelecionável,
                        file_name.")
            else:
                transactions=output_filename..replace(".ofx", ".csvsort(key=lambda x:"),
                        mime="text x["date_obj"])/csv",
                        type
                pdf="secondary"
                    )_initial

                st.markdown("---     ")
                st.subhe= Bader(ankParsers._extractf"📋 L_initialançamentos Ext_balance(textrato_lines)
                initial —_balance = manual {len_initial_balance if manual_(transactions)} registinitial_balance !=ros encont 0.rados")

                df0 else pdf_initial = pd.DataFrame([{
                total
                    "Data":       t_credits["date_obj"].strftime   ("%d/%m/%Y"),= sum(t["amount"]
                    "Descrição for t in transactions if t["":  t["description"],amount"] > 0)
                    "Tipo":       
                total_debits    "Entrada" if t["= sum(t["amount"]amount"] > 0 else for t in transactions if t[" "Saída",
                amount"] < 0)    "Valor (R$
                final_balance   = initial_balance)": t["amount"],
                } for t in transactions]) + total_credits + total_debits

                def

                st.markdown(" color_amount---")
                st.sub(val):
                    returnheader("📊  fResumo"color Financeiro da: {' Conta")
                m#1,28 m2,a745' if val >  m3,0 else '#dc3545 m4 = st.columns'}(4)
                m;1.metric("Saldo font-weight: bold;" Inicial",

                #        Alturafmt_brl(initial que_balance))
                m2 mostra.metric("Ent TODOS os registradas (Créditosros sem cor)", fmt_brl(totaltar
                #_credits))
                m3 .metric("Saídas35 (Débitos)",px    fmt_brl(abs por(total_debits))) linha + 38
                m4.metric("px deSaldo Final",           headerfmt_brl(final_,balance)) sem

                of limitex_ mádataximo
                table        _height = len= generate_ofx(transactions(df) * 35 , bank_code)
                + 38

                st.outputdataframe(
                    df_filename. = osstyle.path.split
                      ext(uploaded_file.name.map)[0] + ".ofx(color_amount, subset"=["

                colValor (R$)"])_
                      .formatdl({"Valor (R$1, col_dl2 =)": fmt_brl} st.columns(2)),
                    use_container_width=True,
                
                with col_dl1:
                    st.download_    height=table_heightbutton("
                )

        except Exception as e:
            st.error(f"📥 Baixar OFX", data=ofx_data, file_name=Erro ao processar o PDF: {stroutput_filename, mime="application/x(e)}")
```-ofx",

---

** typeAs duas="secondary corre")
                with col_dlções desta2:
                    csv vers_data = pdão:**

**.DataFrame1. `([{join
                        "Data_cell`": t mais["date_obj"].strftime int("%deligente**/%m/%Y"),
                 —        "Descrição": t ag["description"],
                        "ora usa aTipo": " regra corEntrada" if t["amount"]reta para > 0 else " decidSaída",
                        "ir quandoValor ( junR$)": ttar sem["amount"],
                    } es for t in transactions]).paço:
-to_csv(index=False). Jencodeunta sem("utf-8")
                 espaço **so    st.download_button("mente** se a última📥 Baixar CSV palavra", data=csv_data, da file_name=output_filename linha anterior. temreplace(".ofx", ".csv "), mime="text/csv",≤ 2 caract type="secondary")

                eres (st.markdown("---")foi clar
                st.subheader(amente cortf"📋 Lada noançamentos — {len meio:(transactions)} regist `ros encontVIrados")`,

                df `G = pd.DataFrame([E{
                    "Data":`, `C       `,t["date_obj"].str `Eftime("%d/%m/%YL"),
                    "Descri`) ção":  t["description"],OU se a primeira
                    "Tipo": letra       " da próEntrada" if t["amountxima linha é"] > 0 else " minSaída",
                    úscula"Valor (R$)
- Junta com espa":ço nos t["amount"],
                } dem for t in transactions])ais casos (`

                def colorOUTROS_amount\n(val):
                    returnBA f"colorNC: {'#OS28`, `CANAIS\nINa745' if val > TERNET0 else '#dc3545`'}; etc.)

**2. `table font-weight: bold;"_height =

                table len(df) * 35_height = min + 38`(len(df) sem * limite máximo** — com 35 25 + 38 l, 800ançamentos a)
                st.dataframe( tabela terá 913
                    df.pxstyle.map e(color_amount, mo subset=["strará todos semValor (R$)" precis]).ar deformat scroll interno({"Valor (R$.)": fmt_brl} O),
                    use_container scroll da_width=True,
                 página    height=table_height do
                )

        except Exception as e:
             Streamlit cust.error(f"ida doErro ao proces resto.sar o
