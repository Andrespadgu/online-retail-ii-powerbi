#!/usr/bin/env python3
"""
Paso 1 — Limpieza de online_retail_II_crudo.csv
Pipeline: Online Retail II → Power BI

DECISIONES registradas (todas aprobadas por el usuario el 2026-10-15):
  D1 solapamiento_hojas: excluir las 22,523 copias de 'Year 2010-2011' del rango
     dic-2010 (duplicadas en 'Year 2009-2010'). motivo_exclusion = 'duplicado_solapamiento_hojas'.
  D2 duplicados_intra_hoja: conservar y marcar con alerta_duplicado_intra_hoja.
  D5 volumen_extremo: conservar y marcar con alerta_volumen_extremo
     cuando |quantity| > 10,000 o price > 10,000.
  Arreglos SEGUROS 1-7 (aprobados):
     - Description: espacios (trim + dobles), nulos disfrazados → NA + alerta_desc_vacia,
       variantes de capitalización → forma más frecuente.
     - StockCode: trim de espacios, minúsculas → MAYÚSCULAS (solo donde la descripción
       más frecuente de la versión en minúscula coincida con la de la versión en mayúscula).

D3 (Quantity negativa sin factura C) y D4 (Price = 0) NO se tocan aquí.
Los clasifica el paso 2 con reglas_retail.yaml.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

# Forzar UTF-8 en consola (Windows usa cp1252 por defecto)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── DECISIONES DEL USUARIO ───────────────────────────────────────────────────

DECISIONES: dict[str, dict] = {
    "solapamiento_hojas": {
        "accion": "excluir",
        "motivo_exclusion": "duplicado_solapamiento_hojas",
        "decidido_por": "usuario",
        "fecha": "2026-10-15",
        "nota": (
            "Conservar las filas de 'Year 2009-2010'. "
            "Excluir copias exactas de 'Year 2010-2011' en el rango 1-9 dic 2010."
        ),
    },
    "duplicados_intra_hoja": {
        "accion": "conservar",
        "decidido_por": "usuario",
        "fecha": "2026-10-15",
        "nota": "Marcar con alerta_duplicado_intra_hoja. Revisión en paso 2 si impacto es material.",
    },
    "volumen_extremo": {
        "accion": "conservar",
        "decidido_por": "usuario",
        "fecha": "2026-10-15",
        "nota": "|quantity| > 10,000 o price > 10,000. Marcar con alerta_volumen_extremo.",
    },
    "stock_code_lower_10": {
        "accion": "unificar",
        "decidido_por": "usuario",
        "fecha": "2026-10-15",
        "nota": (
            "Los 10 StockCodes cuya descripción difería entre lower/UPPER son el mismo producto "
            "con redacción distinta. Se unifica SOLO el código a MAYÚSCULAS; "
            "las descripciones de las filas NO se tocan."
        ),
    },
}

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────

# Columnas de negocio (sin columnas de auditoría). Se usan para comparar duplicados.
COLS_DATOS = [
    "invoice", "stock_code", "description", "quantity",
    "invoice_date", "price", "customer_id", "country",
]

# Mapeo explícito a snake_case (convención del proyecto)
MAPEO_COLUMNAS = {
    "Invoice":     "invoice",
    "StockCode":   "stock_code",
    "Description": "description",
    "Quantity":    "quantity",
    "InvoiceDate": "invoice_date",
    "Price":       "price",
    "Customer ID": "customer_id",
    "Country":     "country",
    "hoja_origen": "hoja_origen",   # ya en snake_case, no cambia
    "fila_excel":  "fila_excel",    # ya en snake_case, no cambia
}

# Tokens de texto que representan un valor vacío (los 0 NO son nulos aquí)
NULOS_TEXTO = {
    "", "na", "n/a", "n.a.", "nan", "null", "none", "nil",
    "-", "--", "---", "?", "??", ".", "sin dato", "sin datos",
    "s/d", "sd", "#n/a", "#n/d", "#na", "#value!", "#valor!",
    "#ref!", "#div/0!", "#name?", "missing", "undefined",
    "vacío", "vacio", "x", "xx", "xxx",
}

UMBRAL_QTY   = 10_000   # |quantity| > este valor → alerta_volumen_extremo
UMBRAL_PRICE = 10_000   # price > este valor → alerta_volumen_extremo


# ─── REGISTRO DE CAMBIOS ──────────────────────────────────────────────────────

class Registro:
    def __init__(self) -> None:
        self.pasos: list[dict] = []
        self.excluidas: list[pd.DataFrame] = []
        self.alertas: dict[str, int] = {}
        self.notas: list[str] = []

    def paso(self, nombre: str, tipo: str, columna: str | None,
             n: int, detalle: str = "") -> None:
        """tipo: 'SEGURO' o 'DECISIÓN'."""
        self.pasos.append({
            "paso": nombre, "tipo": tipo,
            "columna": columna or "—", "afectados": int(n), "detalle": detalle,
        })


REG = Registro()


# ─── HELPERS (funciones de apoyo para la limpieza) ────────────────────────────

def excluir(df: pd.DataFrame, mascara: pd.Series,
            motivo: str, decision: str) -> pd.DataFrame:
    """Saca filas del dataset guardándolas con su motivo. Falla si no hay aprobación."""
    accion = DECISIONES.get(decision, {}).get("accion", "")
    if accion != "excluir":
        raise RuntimeError(
            f"Intento de excluir filas sin aprobación: '{decision}' tiene acción '{accion!r}'"
        )
    fuera = df[mascara].copy()
    if len(fuera):
        fuera["motivo_exclusion"] = motivo
        REG.excluidas.append(fuera)
        REG.paso(f"Excluir: {motivo}", "DECISIÓN", None, len(fuera),
                 f"decisión '{decision}'")
    return df[~mascara]


def marcar(df: pd.DataFrame, mascara: pd.Series, columna_alerta: str,
           motivo: str, detalle_por_fila: pd.Series | None = None) -> pd.DataFrame:
    """Agrega texto de alerta sin tocar el valor. Varias alertas se concatenan con ' | '."""
    if columna_alerta not in df.columns:
        df[columna_alerta] = pd.Series(pd.NA, index=df.index, dtype="string")
    texto = pd.Series(motivo, index=df.index, dtype="string")
    if detalle_por_fila is not None:
        texto = texto + ": " + detalle_por_fila.astype("string").fillna("")
    previo = df.loc[mascara, columna_alerta]
    df.loc[mascara, columna_alerta] = (
        previo.where(previo.isna(), previo + " | ").fillna("") + texto[mascara]
    )
    n = int(mascara.sum())
    if n:
        key = f"{columna_alerta}: {motivo}"
        REG.alertas[key] = REG.alertas.get(key, 0) + n
    return df


def limpiar_espacios(s: pd.Series) -> pd.Series:
    """Quita espacios de ancho cero, normaliza secuencias de espacios y hace strip."""
    return (
        s.str.replace(" ", " ", regex=False)
         .str.replace("​", "", regex=False)
         .str.replace(r"\s+", " ", regex=True)
         .str.strip()
    )


# ─── PIPELINE ────────────────────────────────────────────────────────────────

def main() -> None:
    # ── Rutas ──────────────────────────────────────────────────────────────
    raiz = Path(__file__).resolve().parent.parent.parent
    entrada = (
        Path(sys.argv[1]) if len(sys.argv) > 1
        else raiz / "trabajo" / "00_crudo" / "online_retail_II_crudo.csv"
    )
    salida_dir = (
        Path(sys.argv[2]) if len(sys.argv) > 2
        else raiz / "trabajo" / "01_limpieza"
    )
    salida_dir.mkdir(parents=True, exist_ok=True)

    # ── 0. CARGAR ───────────────────────────────────────────────────────────
    print("Cargando CSV crudo…")
    df = pd.read_csv(entrada, dtype=str, keep_default_na=False, encoding="utf-8")
    n_in = len(df)
    if n_in != 1_067_371:
        print(f"AVISO: se esperaban 1,067,371 filas crudas; CSV tiene {n_in:,}")
    else:
        print(f"  {n_in:,} filas cargadas — OK")

    # Cuadre £ inicial (antes de cualquier modificación)
    qty0   = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    price0 = pd.to_numeric(df["Price"],    errors="coerce").fillna(0)
    importe_crudo = float((qty0 * price0).sum())

    # ── 1. RENOMBRAR COLUMNAS ───────────────────────────────────────────────
    df = df.rename(columns=MAPEO_COLUMNAS)
    cambios_col = {k: v for k, v in MAPEO_COLUMNAS.items() if k != v}
    REG.paso("Renombrar columnas a snake_case", "SEGURO", None, len(cambios_col),
             "; ".join(f"{k}→{v}" for k, v in cambios_col.items()))
    print(f"  Columnas renombradas: {list(df.columns)}")

    # ── 2. NORMALIZAR ESPACIOS (todas las columnas de texto) ────────────────
    cols_texto = [c for c in df.columns if c != "fila_excel"]
    n_cambios_esp = 0
    for c in cols_texto:
        antes = df[c].copy()
        df[c] = limpiar_espacios(df[c])
        nc = int((df[c] != antes).sum())
        if nc > 0:
            REG.paso("Espacios normalizados (trim + dobles → uno)", "SEGURO", c, nc)
            n_cambios_esp += nc
    print(f"  Espacios normalizados: {n_cambios_esp:,} valores modificados")

    # ── 3. D1 — IDENTIFICAR Y EXCLUIR SOLAPAMIENTO ENTRE HOJAS ────────────
    # Trabajamos ANTES de normalizar el contenido de description/stock_code para
    # que el merge use exactamente los valores que quedaron tras el trim.
    print("Detectando solapamiento entre hojas (dic-2010)…")
    h1 = df[df["hoja_origen"] == "Year 2009-2010"]
    h2 = df[df["hoja_origen"] == "Year 2010-2011"]

    # Para cada grupo de filas idénticas en H2, numerar las copias (cumcount)
    # y hacer lo mismo en H1. El merge inner encuentra las H2 que tienen
    # una copia exacta en H1 con el mismo ordinal dentro del grupo.
    h2_reset = h2.reset_index()   # columna 'index' guarda el índice original
    h2_cn = h2_reset[COLS_DATOS].assign(
        _n=h2_reset[COLS_DATOS].groupby(COLS_DATOS, sort=False).cumcount()
    )
    h1_cn = h1[COLS_DATOS].assign(
        _n=h1[COLS_DATOS].groupby(COLS_DATOS, sort=False).cumcount()
    )
    matches = h2_cn.merge(h1_cn, on=COLS_DATOS + ["_n"], how="inner")
    idxs_excluir = h2_reset.loc[matches.index, "index"].values
    n_solap = len(idxs_excluir)

    if n_solap != 22_523:
        print(f"  ⚠ Se esperaban 22,523 copias del solapamiento; se encontraron {n_solap:,}. "
              "Revisa si el archivo crudo es el correcto.")
    else:
        print(f"  Solapamiento confirmado: {n_solap:,} filas de H2 son copia exacta de H1 — OK")

    # Cuadre £ de las filas a excluir (para reportar)
    q_excl = pd.to_numeric(df.loc[idxs_excluir, "quantity"], errors="coerce").fillna(0)
    p_excl = pd.to_numeric(df.loc[idxs_excluir, "price"],    errors="coerce").fillna(0)
    importe_excluido_d1 = float((q_excl * p_excl).sum())

    mask_solap = df.index.isin(idxs_excluir)
    df = excluir(df, mask_solap, "duplicado_solapamiento_hojas", "solapamiento_hojas")
    print(f"  D1: {n_solap:,} filas excluidas → filas_excluidas.csv")

    # ── 4. DESCRIPTION: NULOS DISFRAZADOS → NA + alerta_desc_vacia ─────────
    bajo = df["description"].str.lower()
    mask_nulo_desc = bajo.isin(NULOS_TEXTO)
    n_nulos_desc = int(mask_nulo_desc.sum())
    if n_nulos_desc > 0:
        # Marcar ANTES de borrar el valor original
        df = marcar(df, mask_nulo_desc, "alerta_desc_vacia", "descripcion_nula_o_disfrazada",
                    detalle_por_fila=df["description"].where(mask_nulo_desc))
        df.loc[mask_nulo_desc, "description"] = pd.NA
        REG.paso(
            "Description nula/disfrazada → NA + alerta_desc_vacia", "SEGURO",
            "description", n_nulos_desc,
            "Incluye: vacíos (4,382), '?' (92), 'missing'/'MISSING' (30), '??' (7)",
        )
    print(f"  Description nulas marcadas: {n_nulos_desc:,}")

    # ── 5. DESCRIPTION: UNIFICAR VARIANTES DE CAPITALIZACIÓN ───────────────
    # Solo para valores no-nulos. Cada descripción se normaliza a la forma más
    # frecuente de su clave (lowercase+strip). Afecta ~30 grupos detectados
    # (amazon/AMAZON, damaged/DAMAGED, etc.). Las descripciones con una sola
    # forma no cambian (su forma más frecuente ES esa misma forma).
    mask_not_na = df["description"].notna()
    if mask_not_na.any():
        desc_vals = df.loc[mask_not_na, "description"]
        clave = desc_vals.str.lower().str.strip()
        # Forma más frecuente de cada clave normalizada
        canonical_map = (
            desc_vals.groupby(clave, sort=False)
                     .agg(lambda v: v.value_counts().index[0])
        )
        canonical = clave.map(canonical_map)
        mask_cambio = (desc_vals != canonical)
        n_cambio_desc = int(mask_cambio.sum())
        if n_cambio_desc > 0:
            df.loc[desc_vals.index[mask_cambio], "description"] = canonical[mask_cambio]
            REG.paso(
                "Description: variantes de capitalización → forma más frecuente",
                "SEGURO", "description", n_cambio_desc,
                f"p. ej. 'amazon'/'Amazon' → 'AMAZON'; {n_cambio_desc:,} filas actualizadas",
            )
        print(f"  Description variantes normalizadas: {n_cambio_desc:,}")

    # ── 6. STOCK_CODE: VERIFICAR + NORMALIZAR MINÚSCULAS → MAYÚSCULAS ──────
    # Solo para valores que no están completamente en mayúsculas.
    mask_lower_sc = (
        df["stock_code"].notna()
        & (df["stock_code"] != df["stock_code"].str.upper())
    )
    if mask_lower_sc.any():
        scs_lower_uniq = df.loc[mask_lower_sc, "stock_code"].unique()
        normalizar = []
        no_unificar = []

        for sc_low in sorted(scs_lower_uniq):
            sc_up = sc_low.upper()
            desc_low_vc = (
                df.loc[df["stock_code"] == sc_low, "description"]
                .dropna().value_counts()
            )
            desc_up_vc = (
                df.loc[df["stock_code"] == sc_up, "description"]
                .dropna().value_counts()
            )
            top_low = desc_low_vc.index[0] if len(desc_low_vc) else None
            top_up  = desc_up_vc.index[0]  if len(desc_up_vc)  else None

            if top_low is None or top_up is None or top_low == top_up:
                normalizar.append(sc_low)
            else:
                no_unificar.append({
                    "sc_lower": sc_low, "n_lower": int(len(desc_low_vc)),
                    "sc_upper": sc_up,  "n_upper": int(len(desc_up_vc)),
                    "desc_lower_top": top_low, "desc_upper_top": top_up,
                })

        # Si el usuario aprobó unificar los 10 con descripción distinta (stock_code_lower_10),
        # se incluyen en la normalización. SOLO se cambia el código; las descripciones no se tocan.
        if DECISIONES.get("stock_code_lower_10", {}).get("accion") == "unificar":
            normalizar.extend(item["sc_lower"] for item in no_unificar)
            n_decision_10 = len(no_unificar)
            no_unificar = []
        else:
            n_decision_10 = 0

        mask_norm_sc = df["stock_code"].isin(normalizar)
        df.loc[mask_norm_sc, "stock_code"] = df.loc[mask_norm_sc, "stock_code"].str.upper()

        if n_decision_10:
            REG.paso(
                "StockCode minúsculas → MAYÚSCULAS (todos, incl. 10 con desc. distinta)",
                "DECISIÓN", "stock_code", int(mask_norm_sc.sum()),
                f"{len(normalizar)} códigos; los 10 con desc. diferente unificados por decisión "
                f"'stock_code_lower_10' (solo código, descripciones intactas)",
            )
        else:
            REG.paso(
                "StockCode minúsculas → MAYÚSCULAS (solo consistentes)", "SEGURO",
                "stock_code", int(mask_norm_sc.sum()),
                f"{len(normalizar)} códigos normalizados; {len(no_unificar)} NO normalizados",
            )
        print(f"  StockCode normalizados: {int(mask_norm_sc.sum()):,} filas "
              f"({len(normalizar)} códigos, {n_decision_10} con desc. distinta aprobados)")
        if no_unificar:
            lines = [
                "StockCodes en minúscula cuya descripción NO coincide con la versión en "
                "MAYÚSCULA (NO se normalizaron — requieren revisión):"
            ]
            for item in no_unificar:
                lines.append(
                    f"  {item['sc_lower']} (n filas lowercase={item['n_lower']}, "
                    f"desc='{item['desc_lower_top']}') vs "
                    f"{item['sc_upper']} (n filas uppercase={item['n_upper']}, "
                    f"desc='{item['desc_upper_top']}')"
                )
            REG.notas.append("\n".join(lines))
            print(f"  ⚠  {len(no_unificar)} StockCode(s) NO normalizados — ver reporte")

    # ── 7. D2 — MARCAR DUPLICADOS INTRA-HOJA ──────────────────────────────
    # Se detecta DESPUÉS de D1 (el solapamiento ya fue excluido).
    # Duplicados: filas idénticas en las 8 columnas de dato DENTRO de la misma hoja.
    print("Detectando duplicados intra-hoja…")
    h1_post = df[df["hoja_origen"] == "Year 2009-2010"]
    h2_post = df[df["hoja_origen"] == "Year 2010-2011"]

    mask_dup_h1 = pd.Series(
        h1_post[COLS_DATOS].duplicated(keep="first"),
        index=h1_post.index,
    )
    mask_dup_h2 = pd.Series(
        h2_post[COLS_DATOS].duplicated(keep="first"),
        index=h2_post.index,
    )
    mask_dup = (
        mask_dup_h1.reindex(df.index, fill_value=False)
        | mask_dup_h2.reindex(df.index, fill_value=False)
    )

    if mask_dup.any():
        # Calcular impacto £ antes de marcar
        q_dup   = pd.to_numeric(df.loc[mask_dup, "quantity"], errors="coerce").fillna(0)
        p_dup   = pd.to_numeric(df.loc[mask_dup, "price"],    errors="coerce").fillna(0)
        importe_dup = float((q_dup * p_dup).sum())
        df = marcar(df, mask_dup, "alerta_duplicado_intra_hoja",
                    "duplicado_exacto_en_misma_hoja")
        REG.paso(
            "D2: duplicados intra-hoja marcados (conservados)", "DECISIÓN", None,
            int(mask_dup.sum()),
            f"Impacto: £{importe_dup:,.2f} | H1={int(mask_dup_h1.sum()):,}; "
            f"H2={int(mask_dup_h2.sum()):,}",
        )
    n_d2 = int(mask_dup.sum())
    print(f"  D2: {n_d2:,} filas marcadas con alerta_duplicado_intra_hoja")

    # ── 8. CONVERTIR TIPOS ─────────────────────────────────────────────────
    # Quantity → Int64
    q_bad = pd.to_numeric(df["quantity"], errors="coerce").isna().sum()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
    REG.paso("Quantity texto → Int64", "SEGURO", "quantity",
             int(df["quantity"].notna().sum()), f"{q_bad} no convertibles")

    # Price → float64
    p_bad = pd.to_numeric(df["price"], errors="coerce").isna().sum()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    REG.paso("Price texto → float64", "SEGURO", "price",
             int(df["price"].notna().sum()), f"{p_bad} no convertibles")

    # invoice_date → datetime
    df["invoice_date"] = pd.to_datetime(
        df["invoice_date"], format="%Y-%m-%d %H:%M:%S", errors="coerce"
    )
    n_nat = int(df["invoice_date"].isna().sum())
    REG.paso("InvoiceDate texto → datetime64", "SEGURO", "invoice_date",
             int(df["invoice_date"].notna().sum()),
             f"formato '%Y-%m-%d %H:%M:%S'; {n_nat} NaT")

    # fila_excel → Int64 (columna de auditoría)
    df["fila_excel"] = pd.to_numeric(df["fila_excel"], errors="coerce").astype("Int64")

    # ── 9. D5 — MARCAR VOLUMEN EXTREMO ─────────────────────────────────────
    mask_vol = (
        (df["quantity"].abs() > UMBRAL_QTY) | (df["price"] > UMBRAL_PRICE)
    )
    # Asegurar que no propagamos NA en la comparación
    mask_vol = mask_vol.fillna(False)
    if mask_vol.any():
        detalle = df.loc[mask_vol].apply(
            lambda r: f"qty={r['quantity']} price={r['price']}", axis=1
        )
        df = marcar(df, mask_vol, "alerta_volumen_extremo",
                    "volumen_extremo", detalle)
        REG.paso(
            "D5: volumen extremo marcado (conservado)", "DECISIÓN", None,
            int(mask_vol.sum()),
            f"|quantity|>{UMBRAL_QTY:,} o price>{UMBRAL_PRICE:,}",
        )
    print(f"  D5: {int(mask_vol.sum()):,} filas marcadas con alerta_volumen_extremo")

    # ── 10. VERIFICAR CUADRE ───────────────────────────────────────────────
    excluidas_df = (
        pd.concat(REG.excluidas, ignore_index=True) if REG.excluidas
        else pd.DataFrame()
    )
    n_limpias   = len(df)
    n_excluidas = len(excluidas_df)
    cuadre_filas_ok = (n_in == n_limpias + n_excluidas)

    # Qty*Price del archivo limpio (tipos ya convertidos)
    importe_limpio = float(
        (df["quantity"].astype("Float64") * df["price"]).sum()
    )
    # Diferencia debe ser exactamente el importe del solapamiento excluido
    diferencia = importe_crudo - importe_limpio - importe_excluido_d1

    # ── 11. GUARDAR ────────────────────────────────────────────────────────
    salida_csv = salida_dir / "online_retail_II_limpio.csv"
    df.to_csv(salida_csv, index=False, encoding="utf-8",
              date_format="%Y-%m-%d %H:%M:%S")
    print(f"  CSV limpio: {salida_csv.name}")

    if not excluidas_df.empty:
        excluidas_df.to_csv(salida_dir / "filas_excluidas.csv", index=False,
                            encoding="utf-8")
        print(f"  Excluidas: filas_excluidas.csv")

    # ── 12. REPORTE ────────────────────────────────────────────────────────
    _escribir_reporte(
        salida_dir, entrada, n_in, df, excluidas_df,
        importe_crudo, importe_limpio, importe_excluido_d1,
        diferencia, cuadre_filas_ok,
    )

    # ── Resumen consola ────────────────────────────────────────────────────
    print()
    print("=" * 64)
    print(f"Cuadre filas : {n_in:,} = {n_limpias:,} + {n_excluidas:,}"
          f"  →  {'OK' if cuadre_filas_ok else '*** NO CUADRA ***'}")
    print(f"Qty×Price crudo   : £{importe_crudo:>17,.2f}")
    print(f"Qty×Price excluido: £{importe_excluido_d1:>17,.2f}  (D1 solapamiento)")
    print(f"Qty×Price limpio  : £{importe_limpio:>17,.2f}")
    print(f"Diferencia residual: £{diferencia:>16,.2f}  (debe ser ~0)")
    print(f"Reporte: {salida_dir / 'reporte_limpieza.md'}")
    print("=" * 64)


# ─── REPORTE ──────────────────────────────────────────────────────────────────

def _escribir_reporte(
    salida: Path,
    entrada: Path,
    n_in: int,
    df: pd.DataFrame,
    excluidas: pd.DataFrame,
    importe_crudo: float,
    importe_limpio: float,
    importe_excluido: float,
    diferencia: float,
    cuadre_ok: bool,
) -> None:
    n_limpias   = len(df)
    n_excluidas = len(excluidas)
    cuadre_filas = "OK" if cuadre_ok else "**NO CUADRA**"

    L: list[str] = [
        f"# Reporte de limpieza — {entrada.name}",
        "",
        f"Generado: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## Cuadre de filas",
        "",
        f"| Concepto | Valor |",
        f"|---|---|",
        f"| Filas entrada (crudo) | **{n_in:,}** |",
        f"| Filas limpias (salida) | **{n_limpias:,}** |",
        f"| Filas excluidas (filas_excluidas.csv) | **{n_excluidas:,}** |",
        f"| Cuadre ({n_in:,} = {n_limpias:,} + {n_excluidas:,}) | **{cuadre_filas}** |",
        "",
        "## Cuadre de importes (Quantity × Price)",
        "",
        f"| Concepto | £ |",
        f"|---|---|",
        f"| Total crudo (1,067,371 filas) | {importe_crudo:,.2f} |",
        f"| Excluido D1 (solapamiento) | {importe_excluido:,.2f} |",
        f"| Total limpio ({n_limpias:,} filas) | {importe_limpio:,.2f} |",
        f"| Diferencia residual (debe ser ~0) | {diferencia:,.2f} |",
        "",
        "> Nota: este importe incluye cantidades negativas (devoluciones, ajustes) porque "
        "no se clasifica en este paso. Las métricas de negocio (Ventas Netas, Devoluciones) "
        "las calcula el paso 2 con reglas_retail.yaml.",
        "",
        "## Cambios aplicados",
        "",
        "| # | Paso | Tipo | Columna | Afectados | Detalle |",
        "|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(REG.pasos, 1):
        L.append(
            f"| {i} | {p['paso']} | {p['tipo']} | {p['columna']} "
            f"| {p['afectados']:,} | {p['detalle']} |"
        )

    L += [
        "",
        "## Decisiones del usuario",
        "",
        "| Decisión | Acción | Decidido por | Fecha | Nota |",
        "|---|---|---|---|---|",
    ]
    for k, d in DECISIONES.items():
        L.append(
            f"| {k} | {d['accion']} | {d.get('decidido_por', '—')} "
            f"| {d.get('fecha', '—')} | {d.get('nota', '')} |"
        )

    L += [
        "",
        "## Alertas conservadas (valores NO modificados, solo marcados)",
        "",
    ]
    if REG.alertas:
        L += [f"| Alerta | Filas |", "|---|---|"]
        for k, v in REG.alertas.items():
            L.append(f"| {k} | {v:,} |")
    else:
        L.append("_Ninguna._")

    if REG.notas:
        L += ["", "## Notas adicionales (requieren revisión)", ""]
        for nota in REG.notas:
            L.append(nota)
            L.append("")

    # Pendientes (D3, D4 se resuelven en paso 2)
    L += [
        "",
        "## Pendientes para el paso 2 (reglas_retail.yaml)",
        "",
        "- **D3**: Quantity negativa sin prefijo C en invoice (3,457 filas) "
        "→ clasificar con R5 `ajuste_inventario` o según regla aplicable.",
        "- **D4**: Price = 0 (6,202 filas, de ellas 2,745 con Quantity > 0) "
        "→ clasificar con R6 `sin_valor` o como muestras según contexto.",
        "- **Customer ID vacío** (243,007 filas) → R4 de reglas_retail.yaml "
        "(`cliente_sin_identificar: SIN_CLIENTE`).",
        "- **Invoice C / A** y **StockCodes no-producto** → clasificar con R1, R2, R3 "
        "del YAML (no se toca en limpieza).",
    ]

    (salida / "reporte_limpieza.md").write_text(
        "\n".join(L) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
