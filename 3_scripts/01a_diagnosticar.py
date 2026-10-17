#!/usr/bin/env python3
"""Diagnóstico de un CSV sucio: encuentra problemas SIN modificar nada.

Uso:
    python diagnosticar.py ARCHIVO.csv [--json salida.json] [--max-ejemplos 5]

Lee todo como texto (para no perder ceros a la izquierda ni formatos) y reporta:
estructura del archivo, encabezados, filas basura, nulos disfrazados, tipos,
formatos de número y fecha mezclados, categorías escritas de varias formas,
codificación rota, identificadores, duplicados y valores atípicos (outliers).

La salida es un informe en Markdown por pantalla (y opcionalmente JSON).
Es un punto de partida: el analista debe revisar el contexto antes de decidir.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

NULOS_DISFRAZADOS = {
    "", "na", "n/a", "n.a.", "nan", "null", "none", "nil", "nulo", "-", "--", "---", "?", "??",
    ".", "sin dato", "sin datos", "s/d", "sd", "no aplica", "no disponible", "desconocido",
    "#n/a", "#n/d", "#na", "#value!", "#valor!", "#ref!", "#div/0!", "#name?", "missing",
    "undefined", "vacío", "vacio", "x", "xx", "xxx", "0000-00-00", "00/00/0000",
}
PALABRAS_TOTAL = re.compile(r"^\s*(sub)?total(es)?\b|^\s*(suma|gran total|grand total|totals?)\s*:?\s*$", re.I)
MOJIBAKE = re.compile(r"Ã[\x80-\xbf¡-¿]|Â[\x80-\xbf ¡-¿]|â€|ï¿½|�")
MONEDA = re.compile(r"(?:R\$|US\$|\$|€|£|\bCOP\b|\bUSD\b|\bEUR\b|\bBRL\b|\bMXN\b)", re.I)
CENTINELAS = {-1, -9, -99, -999, -9999, 999, 9999, 99999, 999999, 9999999, 99999999}
PATRONES_FECHA = [
    (re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?$"), "AAAA-MM-DD"),
    (re.compile(r"^\d{4}/\d{2}/\d{2}( \d{1,2}:\d{2}(:\d{2})?)?$"), "AAAA/MM/DD"),
    (re.compile(r"^\d{1,2}/\d{1,2}/\d{4}( \d{1,2}:\d{2}(:\d{2})?)?$"), "NN/NN/AAAA"),
    (re.compile(r"^\d{1,2}-\d{1,2}-\d{4}( \d{1,2}:\d{2}(:\d{2})?)?$"), "NN-NN-AAAA"),
    (re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$"), "NN.NN.AAAA"),
    (re.compile(r"^\d{1,2}/\d{1,2}/\d{2}$"), "NN/NN/AA"),
    (re.compile(r"^\d{8}$"), "AAAAMMDD?"),
    (re.compile(r"^\d{1,2}[ -](ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic|jan|apr|aug|dec)[a-z]*[ -]\d{2,4}$", re.I), "DD-mes-AAAA"),
]


# ----------------------------------------------------------------------------
# Lectura robusta
# ----------------------------------------------------------------------------
def detectar_codificacion(crudo: bytes) -> tuple[str, str]:
    if crudo.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", "BOM UTF-8 presente"
    if crudo.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16", "BOM UTF-16 presente"
    try:
        crudo.decode("utf-8")
        return "utf-8", "decodifica limpio como UTF-8"
    except UnicodeDecodeError as e:
        pos = e.start
    # Para datos en español/portugués casi siempre es cp1252 (Excel en Windows) o latin-1.
    # Los detectores automáticos a veces proponen cp1250/cp1251 y rompen tildes (São -> Săo).
    for enc in ("cp1252", "latin-1"):
        try:
            crudo.decode(enc)
            return enc, f"no es UTF-8 (byte inválido en posición {pos}); se usa {enc}. Verifica que tildes y ñ se vean bien"
        except UnicodeDecodeError:
            continue
    return "cp1252", f"no es UTF-8 (byte inválido en posición {pos}); se asume cp1252/latin-1"


def detectar_separador(texto: str) -> tuple[str, str]:
    muestra = "\n".join(texto.splitlines()[:50])
    try:
        d = csv.Sniffer().sniff(muestra, delimiters=",;\t|")
        return d.delimiter, "csv.Sniffer"
    except csv.Error:
        conteo = {s: muestra.count(s) for s in [",", ";", "\t", "|"]}
        sep = max(conteo, key=conteo.get)
        return sep, f"conteo de caracteres {conteo}"


def leer_como_texto(ruta: Path):
    crudo = ruta.read_bytes()
    enc, motivo_enc = detectar_codificacion(crudo)
    texto = crudo.decode(enc, errors="replace")
    sep, motivo_sep = detectar_separador(texto)

    # filas con número de campos distinto al encabezado
    lector = csv.reader(io.StringIO(texto), delimiter=sep)
    anchos = Counter()
    malas = []
    n_enc = None
    for i, fila in enumerate(lector):
        if i == 0:
            n_enc = len(fila)
            continue
        anchos[len(fila)] += 1
        if len(fila) != n_enc and len(malas) < 10:
            malas.append((i + 1, len(fila)))

    df = pd.read_csv(
        io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False,
        on_bad_lines="warn", engine="python",
    )
    meta = {
        "archivo": str(ruta), "bytes": len(crudo), "codificacion": enc, "motivo_codificacion": motivo_enc,
        "separador": sep, "motivo_separador": motivo_sep, "columnas_encabezado": n_enc,
        "anchos_de_fila": dict(anchos), "filas_ancho_incorrecto_ejemplos": malas,
        "saltos_de_linea": "CRLF" if b"\r\n" in crudo[:100_000] else "LF",
    }
    return df, meta


# ----------------------------------------------------------------------------
# Utilidades de normalización (solo para comparar, nunca se escriben)
# ----------------------------------------------------------------------------
def clave_suave(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def a_numero(serie: pd.Series) -> tuple[pd.Series, dict]:
    """Intenta convertir texto a número detectando formato (1.234,56 vs 1,234.56, moneda, %)."""
    s = serie.astype(str).str.strip()
    info = {"con_moneda": int(s.str.contains(MONEDA).sum()), "con_porcentaje": int(s.str.endswith("%").sum())}
    s = s.str.replace(MONEDA, "", regex=True).str.replace("%", "", regex=False).str.replace(r"\s", "", regex=True)
    s = s.str.replace(r"^\((.*)\)$", r"-\1", regex=True)  # (123) contable = negativo
    coma_dec = s.str.fullmatch(r"-?\d{1,3}(\.\d{3})*,\d+|-?\d+,\d+").sum()
    punto_dec = s.str.fullmatch(r"-?\d{1,3}(,\d{3})*\.\d+|-?\d+\.\d+").sum()
    info["decimal_coma"] = int(coma_dec)
    info["decimal_punto"] = int(punto_dec)
    if coma_dec > punto_dec:
        s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        info["formato_asumido"] = "1.234,56 (coma decimal)"
    else:
        s = s.str.replace(",", "", regex=False)
        info["formato_asumido"] = "1,234.56 (punto decimal)"
    return pd.to_numeric(s, errors="coerce"), info


def patron_fecha(v: str) -> str | None:
    for rx, nombre in PATRONES_FECHA:
        if rx.match(v):
            return nombre
    return None


def resumen_ambiguedad_dm(valores: list[str]) -> dict:
    """Para NN/NN/AAAA: ¿el primer número pasa de 12 (día primero) o el segundo (mes primero)?"""
    p1 = p2 = ambos_12 = 0
    for v in valores:
        m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.]", v)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12:
            p1 += 1
        elif b > 12:
            p2 += 1
        else:
            ambos_12 += 1
    return {"primero>12 (DD/MM)": p1, "segundo>12 (MM/DD)": p2, "ambiguos (ambos<=12)": ambos_12}


# ----------------------------------------------------------------------------
# Diagnóstico
# ----------------------------------------------------------------------------
def diagnosticar(df: pd.DataFrame, meta: dict, max_ej: int = 5) -> dict:
    r: dict = {"meta": meta, "filas": len(df), "columnas": len(df.columns)}
    cols = list(df.columns)

    # --- Encabezados
    enc = []
    for c in cols:
        probs = []
        if c != c.strip():
            probs.append("espacios al inicio/fin")
        if re.search(r"\s{2,}", c):
            probs.append("espacios dobles")
        if re.match(r"^Unnamed: \d+", c) or c.strip() == "":
            probs.append("sin nombre (columna índice exportada o vacía)")
        if re.search(r"[^\w ]", c, re.ASCII):
            probs.append("caracteres especiales/acentos")
        if re.search(r"\.\d+$", c) and c.rsplit(".", 1)[0] in cols:
            probs.append("nombre duplicado (pandas le agregó .N)")
        if probs:
            enc.append({"columna": c, "problemas": probs})
    r["encabezados"] = enc

    # --- Filas basura
    fila_enc = df.apply(lambda f: sum(str(v).strip() == str(c).strip() for v, c in zip(f, cols)) >= max(2, len(cols) // 2), axis=1)
    r["filas_encabezado_repetido"] = [int(i) for i in df.index[fila_enc]]
    total = df.apply(lambda f: any(PALABRAS_TOTAL.match(str(v)) for v in f.iloc[:3]), axis=1)
    r["filas_total_o_resumen"] = [int(i) for i in df.index[total]]
    vacias = df.apply(lambda f: all(str(v).strip() == "" for v in f), axis=1)
    r["filas_totalmente_vacias"] = int(vacias.sum())
    basura = fila_enc | total | vacias
    datos = df[~basura]

    # --- Duplicados
    r["duplicados_exactos"] = int(datos.duplicated().sum())
    norm = datos.apply(lambda s: s.map(clave_suave))
    r["duplicados_tras_normalizar_texto"] = int(norm.duplicated().sum()) - r["duplicados_exactos"]

    # --- Columnas
    col_rep = {}
    candidatas_id = []
    for c in cols:
        s = datos[c].astype(str)
        st = s.str.strip()
        low = st.str.lower()
        n = len(s)
        info: dict = {}
        vacio = st.eq("")
        disfraz = low.isin(NULOS_DISFRAZADOS) & ~vacio
        info["vacios"] = int(vacio.sum())
        info["nulos_disfrazados"] = dict(Counter(s[disfraz]).most_common(10))
        util = st[~(vacio | disfraz)]
        info["pct_faltante_total"] = round(100 * (vacio.sum() + disfraz.sum()) / max(n, 1), 1)
        info["unicos"] = int(util.nunique())
        info["ejemplos"] = util.drop_duplicates().head(max_ej).tolist()
        if util.empty:
            info["alerta"] = "columna totalmente vacía"
            col_rep[c] = info
            continue
        if util.nunique() == 1 and len(util) == n:
            info["alerta"] = f"columna constante ('{util.iloc[0]}')"

        # espacios
        info["con_espacios_extremos"] = int((s != s.str.strip()).sum())
        info["con_espacios_dobles"] = int(s.str.contains(r"\S\s{2,}\S", regex=True).sum())
        # mojibake
        moj = util[util.str.contains(MOJIBAKE)]
        if len(moj):
            info["codificacion_rota"] = {"n": int(len(moj)), "ejemplos": moj.head(3).str.slice(0, 80).tolist()}
        # multilínea
        ml = int(util.str.contains(r"[\r\n]").sum())
        if ml:
            info["valores_multilinea"] = ml

        # tipo inferido
        num, finfo = a_numero(util)
        pct_num = num.notna().mean()
        pats = util.map(patron_fecha)
        pct_fecha = pats.notna().mean()
        if pct_fecha >= 0.6:
            info["tipo_probable"] = "fecha"
            info["formatos_fecha"] = dict(Counter(pats.dropna()))
            no_fecha = util[pats.isna()]
            if len(no_fecha):
                info["no_parecen_fecha"] = no_fecha.drop_duplicates().head(max_ej).tolist()
            nn = util[pats.isin(["NN/NN/AAAA", "NN-NN-AAAA", "NN.NN.AAAA", "NN/NN/AA"])].tolist()
            if nn:
                info["ambiguedad_dia_mes"] = resumen_ambiguedad_dm(nn)
            iso = pd.to_datetime(util[pats == "AAAA-MM-DD"], errors="coerce", format="mixed")
            if iso.notna().any():
                hoy = pd.Timestamp.now()
                fut = iso[iso > hoy + pd.Timedelta(days=366)]
                viejas = iso[iso < pd.Timestamp("1950-01-01")]
                info["rango_fechas_iso"] = [str(iso.min()), str(iso.max())]
                if len(fut):
                    info["fechas_futuras_sospechosas"] = dict(Counter(fut.astype(str)).most_common(5))
                if len(viejas):
                    info["fechas_muy_antiguas"] = dict(Counter(viejas.astype(str)).most_common(5))
        elif pct_num >= 0.8:
            info["tipo_probable"] = "numérico"
            info["formato_numero"] = finfo
            no_num = util[num.isna()]
            if len(no_num):
                info["no_convertibles"] = dict(Counter(no_num).most_common(max_ej))
            # ceros a la izquierda -> probablemente es un código, no un número
            ceros = util.str.fullmatch(r"0\d+").sum()
            largos = util[util.str.fullmatch(r"\d+")].str.len().value_counts().to_dict()
            if ceros or (len(largos) > 1 and ("id" in c.lower() or "cod" in c.lower() or "cep" in c.lower() or "zip" in c.lower() or "postal" in c.lower())):
                info["posible_codigo"] = {"con_cero_inicial": int(ceros), "largos": {int(k): int(v) for k, v in largos.items()}}
            x = num.dropna()
            info["estadisticas"] = {k: round(float(v), 4) for k, v in x.describe().items()}
            info["negativos"] = int((x < 0).sum())
            info["ceros"] = int((x == 0).sum())
            cent = x[x.isin(CENTINELAS) | (x.abs() >= 1e7)]
            if len(cent):
                info["posibles_centinelas"] = dict(Counter(cent).most_common(5))
            q1, q3 = x.quantile([0.25, 0.75]) if len(x) else (0, 0)
            iqr = q3 - q1
            if len(x) >= 20 and x.nunique() > 10 and iqr > 0:
                bajo, alto = q1 - 3 * iqr, q3 + 3 * iqr
                med = x.median()
                mad = (x - med).abs().median()
                z = 0.6745 * (x - med) / mad if mad else pd.Series(0, index=x.index)
                fuera = x[(x < bajo) | (x > alto)]
                info["outliers"] = {
                    "regla": "fuera de [Q1-3·IQR, Q3+3·IQR]",
                    "limites": [round(float(bajo), 4), round(float(alto), 4)],
                    "n_iqr3": int(len(fuera)),
                    "n_z_robusto>3.5": int((z.abs() > 3.5).sum()),
                    "valores_mas_altos": [float(v) for v in x.nlargest(max_ej)],
                    "valores_mas_bajos": [float(v) for v in x.nsmallest(max_ej)],
                    "tope_repetido": ({"valor": float(x.max()), "veces": int((x == x.max()).sum())}
                                      if x.max() > alto and (x == x.max()).sum() >= 3 else {}),
                    "piso_repetido": ({"valor": float(x.min()), "veces": int((x == x.min()).sum())}
                                      if x.min() < bajo and (x == x.min()).sum() >= 3 else {}),
                    "sesgo": round(float(x.skew()), 2),
                }
        else:
            info["tipo_probable"] = "texto/categoría"
            # variantes que solo difieren en mayúsculas/acentos/espacios
            grupos = util.groupby(util.map(clave_suave)).agg(lambda v: sorted(set(v)))
            variantes = {k: v for k, v in grupos.items() if len(v) > 1}
            if variantes:
                info["variantes_misma_categoria"] = {
                    "n_grupos": len(variantes),
                    "ejemplos": dict(list(sorted(variantes.items(), key=lambda kv: -len(kv[1])))[:max_ej]),
                }
            if util.nunique() <= 50:
                info["frecuencias"] = dict(Counter(util).most_common(15))
            if pct_num > 0.2:
                info["alerta_mezcla"] = f"{round(100 * pct_num)}% de valores parecen números"
        # identificadores
        ratio = util.nunique() / max(len(util), 1)
        es_id_por_nombre = re.search(r"(^|_|\s)(id|codigo|código|cod)($|_|\s)", c, re.I)
        texto_libre = util.str.len().median() > 40 or (util.str.contains(" ").mean() > 0.5 and util.str.len().median() > 25)
        if texto_libre and info.get("tipo_probable") == "texto/categoría":
            info["parece_texto_libre"] = True
        if (info.get("tipo_probable") == "texto/categoría" and not texto_libre and ratio > 0.95 and len(util) > 20) or es_id_por_nombre:
            largos = util.str.len().value_counts()
            candidatas_id.append({"columna": c, "unicos/filas": round(ratio, 3), "largos_texto": {int(k): int(v) for k, v in largos.head(5).items()}})
        col_rep[c] = info
    r["columnas_detalle"] = col_rep
    r["posibles_identificadores"] = candidatas_id

    # --- Claves repetidas con contenido distinto (conflictos)
    conflictos = []
    for cand in candidatas_id:
        c = cand["columna"]
        sub = datos[datos[c].str.strip() != ""]
        dup = sub[sub.duplicated(c, keep=False)]
        if 0 < len(dup) and cand["unicos/filas"] > 0.9:
            distintos = dup.drop_duplicates()
            n_conf = int(distintos.duplicated(c, keep=False).sum())
            if n_conf:
                conflictos.append({"clave": c, "filas_con_clave_repetida": int(len(dup)), "filas_en_conflicto": n_conf,
                                   "nota": "puede ser normal si la clave real es compuesta (p. ej. pedido+ítem)"})
    r["claves_repetidas_con_contenido_distinto"] = conflictos
    return r


# ----------------------------------------------------------------------------
# Salida en Markdown
# ----------------------------------------------------------------------------
def a_markdown(r: dict) -> str:
    m = r["meta"]
    L = [f"# Diagnóstico: {Path(m['archivo']).name}", ""]
    L.append(f"- Codificación: **{m['codificacion']}** ({m['motivo_codificacion']})")
    L.append(f"- Separador: **{repr(m['separador'])}** ({m['motivo_separador']}); saltos de línea {m['saltos_de_linea']}")
    L.append(f"- Filas leídas: **{r['filas']}**, columnas: **{r['columnas']}**")
    if len(m["anchos_de_fila"]) > 1:
        L.append(f"- ⚠ Filas con distinto número de campos: {m['anchos_de_fila']} (ejemplos línea,campos: {m['filas_ancho_incorrecto_ejemplos']})")
    L.append("")
    L.append("## Estructura y filas")
    L.append(f"- Encabezado repetido dentro de los datos (índices): {r['filas_encabezado_repetido'] or 'ninguno'}")
    L.append(f"- Filas de TOTAL/resumen (índices): {r['filas_total_o_resumen'] or 'ninguna'}")
    L.append(f"- Filas totalmente vacías: {r['filas_totalmente_vacias']}")
    L.append(f"- Duplicados exactos: **{r['duplicados_exactos']}**")
    L.append(f"- Duplicados adicionales si se ignoran mayúsculas/acentos/espacios: **{r['duplicados_tras_normalizar_texto']}**")
    if r["claves_repetidas_con_contenido_distinto"]:
        L.append(f"- ⚠ Claves repetidas con contenido distinto (conflictos, no duplicados): {r['claves_repetidas_con_contenido_distinto']}")
    if r["posibles_identificadores"]:
        L.append(f"- Posibles identificadores: {[c['columna'] for c in r['posibles_identificadores']]}")
    if r["encabezados"]:
        L.append("")
        L.append("## Encabezados con problemas")
        for e in r["encabezados"]:
            L.append(f"- `{e['columna']!r}`: {', '.join(e['problemas'])}")
    L.append("")
    L.append("## Columnas")
    for c, i in r["columnas_detalle"].items():
        L.append(f"### `{c}` — {i.get('tipo_probable', '—')}")
        if "alerta" in i:
            L.append(f"- ⚠ {i['alerta']}")
        L.append(f"- Faltantes: {i['pct_faltante_total']}% (vacíos {i['vacios']}; disfrazados {i['nulos_disfrazados'] or 'ninguno'}) · únicos: {i['unicos']}")
        L.append(f"- Ejemplos: {i['ejemplos']}")
        for k in ["con_espacios_extremos", "con_espacios_dobles", "valores_multilinea"]:
            if i.get(k):
                L.append(f"- {k.replace('_', ' ')}: {i[k]}")
        for k in ["codificacion_rota", "formatos_fecha", "no_parecen_fecha", "ambiguedad_dia_mes", "rango_fechas_iso",
                  "fechas_futuras_sospechosas", "fechas_muy_antiguas", "formato_numero", "no_convertibles",
                  "posible_codigo", "posibles_centinelas", "variantes_misma_categoria", "alerta_mezcla", "parece_texto_libre"]:
            if i.get(k):
                L.append(f"- {k.replace('_', ' ')}: {i[k]}")
        if "estadisticas" in i:
            e = i["estadisticas"]
            L.append(f"- min {e['min']} · p25 {e['25%']} · mediana {e['50%']} · p75 {e['75%']} · max {e['max']} · negativos {i['negativos']} · ceros {i['ceros']}")
        if "outliers" in i:
            o = i["outliers"]
            L.append(f"- Outliers ({o['regla']} = {o['limites']}): {o['n_iqr3']} · z robusto>3.5: {o['n_z_robusto>3.5']} · sesgo {o['sesgo']}")
            L.append(f"  - más altos {o['valores_mas_altos']} · más bajos {o['valores_mas_bajos']}")
            if o["tope_repetido"]:
                L.append(f"  - ⚠ el máximo se repite {o['tope_repetido']['veces']} veces ({o['tope_repetido']['valor']}): ¿tope del sistema o valor de relleno?")
            if o["piso_repetido"]:
                L.append(f"  - ⚠ el mínimo se repite {o['piso_repetido']['veces']} veces ({o['piso_repetido']['valor']}): ¿piso del sistema o valor de relleno?")
        if "frecuencias" in i:
            L.append(f"- Frecuencias: {i['frecuencias']}")
        L.append("")
    L.append("> Este diagnóstico es automático. Antes de decidir, mira las filas completas de los casos raros y piensa en el dominio.")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivo")
    ap.add_argument("--json", help="guardar el diagnóstico también en JSON")
    ap.add_argument("--max-ejemplos", type=int, default=5)
    a = ap.parse_args()
    df, meta = leer_como_texto(Path(a.archivo))
    r = diagnosticar(df, meta, a.max_ejemplos)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(a_markdown(r))
    if a.json:
        Path(a.json).write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
