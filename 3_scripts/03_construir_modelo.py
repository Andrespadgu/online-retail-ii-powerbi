#!/usr/bin/env python3
"""Convierte la tabla de líneas clasificadas en un modelo estrella para Power BI.

Uso:
    python construir_modelo.py lineas_clasificadas.parquet --reglas reglas_retail.yaml --salida CARPETA

Entrada: salida del script 02_aplicar_reglas.py (necesita tipo_linea, importe, es_producto,
cliente_identificado, categoria_no_producto, version_reglas).

Salidas en CARPETA:
    fact_ventas.parquet, dim_producto.parquet, dim_cliente.parquet, dim_pais.parquet, dim_fecha.parquet
    relaciones.json      relaciones (1:* , dirección simple) para recrear en Power BI
    metadatos.json       tipo Power BI y descripción de cada columna (lo usa el script de exportaciÃ³n)
    medidas.dax          medidas listas para pegar
    valores_esperados.csv valores que las medidas DEBEN dar en Power BI (total y por año-mes)
    validacion_modelo.md chequeos de integridad
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import yaml

DESCONOCIDO = -1
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def moda_determinista(s: pd.Series):
    """Valor más frecuente; empate -> el primero en orden alfabético. Ignora nulos."""
    s = s.dropna().astype(str).str.strip()
    s = s[s != ""]
    if s.empty:
        return pd.NA
    vc = s.value_counts()
    top = vc[vc == vc.max()].index
    return sorted(top)[0]


def construir(df: pd.DataFrame, r: dict):
    c = r["columnas"]
    sin_id = r["cliente_sin_identificar"]
    req = ["tipo_linea", "importe", "es_producto", "cliente_identificado", "version_reglas"]
    falt = [x for x in req if x not in df.columns]
    if falt:
        sys.exit(f"ERROR: faltan {falt}. Corre primero 02_aplicar_reglas.py.")

    df = df.copy()
    df["_fecha"] = pd.to_datetime(df[c["fecha"]])
    pais_col = c.get("pais") if c.get("pais") in df.columns else None
    desc_col = c.get("descripcion") if c.get("descripcion") in df.columns else None

    # ---------- dim_producto ----------
    g = df.groupby(c["codigo"], sort=True)
    dp = pd.DataFrame({
        "codigo_producto": g.size().index.astype(str),
        "descripcion": (g[desc_col].agg(moda_determinista).values if desc_col else pd.NA),
        "n_descripciones": (g[desc_col].nunique().values if desc_col else 0),
        "es_producto": g["es_producto"].first().values,
        "categoria_no_producto": g["categoria_no_producto"].first().values,
    })
    ventas = df[df.tipo_linea == "venta"]
    precio_ref = ventas.groupby(c["codigo"])[c["precio"]].median()
    dp["precio_referencia"] = dp["codigo_producto"].map(precio_ref).round(2)
    dp["descripcion"] = dp["descripcion"].fillna("(sin descripción)")
    dp.insert(0, "producto_key", range(1, len(dp) + 1))
    dp = pd.concat([pd.DataFrame([{"producto_key": DESCONOCIDO, "codigo_producto": "N/D", "descripcion": "Desconocido",
                                   "n_descripciones": 0, "es_producto": False, "categoria_no_producto": pd.NA,
                                   "precio_referencia": pd.NA}]), dp], ignore_index=True)

    # ---------- dim_pais ----------
    paises = sorted(df[pais_col].dropna().astype(str).str.strip().unique()) if pais_col else []
    dpa = pd.DataFrame({"pais_key": range(1, len(paises) + 1), "pais": paises})
    dpa = pd.concat([pd.DataFrame([{"pais_key": DESCONOCIDO, "pais": "Desconocido"}]), dpa], ignore_index=True)

    # ---------- dim_cliente ----------
    ident = df[df.cliente_identificado]
    gc = ident.groupby(c["cliente"], sort=True)
    dc = pd.DataFrame({"codigo_cliente": gc.size().index.astype(str)})
    if pais_col:
        dc["pais_principal"] = gc[pais_col].agg(moda_determinista).values
        dc["n_paises"] = gc[pais_col].nunique().values
    gv = ventas[ventas.cliente_identificado].groupby(c["cliente"])
    dc["primera_compra"] = dc["codigo_cliente"].map(gv["_fecha"].min()).dt.date
    dc["ultima_compra"] = dc["codigo_cliente"].map(gv["_fecha"].max()).dt.date
    dc["cliente_identificado"] = True
    dc.insert(0, "cliente_key", range(1, len(dc) + 1))
    filler = {"cliente_key": DESCONOCIDO, "codigo_cliente": sin_id, "cliente_identificado": False}
    if pais_col:
        filler.update({"pais_principal": "Desconocido", "n_paises": 0})
    dc = pd.concat([pd.DataFrame([filler]), dc], ignore_index=True)

    # ---------- dim_fecha (años completos, sin huecos) ----------
    ini = pd.Timestamp(df["_fecha"].min().year, 1, 1)
    fin = pd.Timestamp(df["_fecha"].max().year, 12, 31)
    d = pd.DataFrame({"fecha": pd.date_range(ini, fin, freq="D")})
    iso = d.fecha.dt.isocalendar()
    dfe = pd.DataFrame({
        "fecha_key": d.fecha.dt.strftime("%Y%m%d").astype(int),
        "fecha": d.fecha.dt.date,
        "anio": d.fecha.dt.year,
        "trimestre": "T" + d.fecha.dt.quarter.astype(str),
        "trimestre_num": d.fecha.dt.quarter,
        "mes_num": d.fecha.dt.month,
        "mes_nombre": d.fecha.dt.month.map(lambda m: MESES[m - 1].capitalize()),
        "mes_abrev": d.fecha.dt.month.map(lambda m: MESES[m - 1][:3].capitalize()),
        "anio_mes": d.fecha.dt.strftime("%Y-%m"),
        "anio_mes_num": (d.fecha.dt.year * 100 + d.fecha.dt.month),
        "semana_iso": iso.week.astype(int),
        "anio_iso": iso.year.astype(int),
        "dia_mes": d.fecha.dt.day,
        "dia_anio": d.fecha.dt.dayofyear,
        "dia_semana_num": d.fecha.dt.dayofweek + 1,
        "dia_semana_nombre": d.fecha.dt.dayofweek.map(lambda x: DIAS[x].capitalize()),
        "es_fin_de_semana": d.fecha.dt.dayofweek >= 5,
        "es_fin_de_mes": d.fecha.dt.is_month_end,
    })

    # ---------- fact_ventas (grano: una línea de factura) ----------
    mp_prod = dict(zip(dp.codigo_producto, dp.producto_key))
    mp_cli = dict(zip(dc.codigo_cliente, dc.cliente_key))
    mp_pais = dict(zip(dpa.pais, dpa.pais_key))
    f = pd.DataFrame({
        "linea_id": range(1, len(df) + 1),
        "num_factura": df[c["factura"]].astype(str).str.strip().values,
        "fecha_key": df["_fecha"].dt.strftime("%Y%m%d").astype(int).values,
        "hora": df["_fecha"].dt.hour.values,
        "producto_key": df[c["codigo"]].astype(str).map(mp_prod).fillna(DESCONOCIDO).astype(int).values,
        "cliente_key": df[c["cliente"]].astype(str).map(mp_cli).fillna(DESCONOCIDO).astype(int).values,
        "pais_key": (df[pais_col].astype(str).str.strip().map(mp_pais).fillna(DESCONOCIDO).astype(int).values
                     if pais_col else DESCONOCIDO),
        "cantidad": pd.to_numeric(df[c["cantidad"]]).astype("int64").values,
        "precio_unitario": pd.to_numeric(df[c["precio"]]).round(4).values,
        "importe": df["importe"].round(4).values,
        "tipo_linea": df["tipo_linea"].astype(str).values,
        "es_producto": df["es_producto"].astype(bool).values,
        "cliente_identificado": df["cliente_identificado"].astype(bool).values,
        "version_reglas": df["version_reglas"].astype(str).values,
    })
    for col in ["producto_key", "cliente_key", "pais_key", "fecha_key"]:
        f[col] = f[col].astype("int64")
    return {"fact_ventas": f, "dim_producto": dp, "dim_cliente": dc, "dim_pais": dpa, "dim_fecha": dfe}


RELACIONES = [
    {"desde": "fact_ventas[fecha_key]", "hacia": "dim_fecha[fecha_key]"},
    {"desde": "fact_ventas[producto_key]", "hacia": "dim_producto[producto_key]"},
    {"desde": "fact_ventas[cliente_key]", "hacia": "dim_cliente[cliente_key]"},
    {"desde": "fact_ventas[pais_key]", "hacia": "dim_pais[pais_key]"},
]

DESCRIPCIONES = {
    "fact_ventas": {
        "_tabla": "Hechos. Grano: una línea de factura (incluye ventas, devoluciones, cargos y ajustes; las medidas filtran por tipo_linea).",
        "linea_id": "Identificador único de la línea (orden de la fuente).",
        "num_factura": "Número de factura de la fuente. Prefijo C = nota crédito/devolución; A = ajuste contable.",
        "fecha_key": "Fecha de la factura como AAAAMMDD. Relación con dim_fecha.",
        "hora": "Hora de la factura (0-23).",
        "producto_key": "Clave sustituta del producto o concepto. Relación con dim_producto.",
        "cliente_key": "Clave sustituta del cliente; -1 = venta sin cliente identificado. Relación con dim_cliente.",
        "pais_key": "País de la factura (no del cliente: un cliente puede comprar desde varios países). Relación con dim_pais.",
        "cantidad": "Unidades. Negativa en devoluciones y ajustes de inventario.",
        "precio_unitario": "Precio unitario en la moneda de la fuente.",
        "importe": "cantidad x precio_unitario, con signo.",
        "tipo_linea": "Clasificación de reglas de negocio: venta, devolucion, cargo_no_producto, ajuste_inventario, ajuste_contable, sin_valor, cancelado, sin_clasificar.",
        "es_producto": "Falso para envío, comisiones, descuentos, ajustes y similares.",
        "cliente_identificado": "Falso cuando la fuente no trae cliente (SIN_CLIENTE).",
        "version_reglas": "Versión del archivo de reglas que clasificó la línea.",
    },
    "dim_producto": {
        "_tabla": "Productos y conceptos no producto. Una fila por código.",
        "producto_key": "Clave sustituta (entero). -1 = desconocido.",
        "codigo_producto": "Código de la fuente (StockCode).",
        "descripcion": "Descripción más frecuente del código (empates: la primera alfabéticamente).",
        "n_descripciones": "Cuántas descripciones distintas tuvo el código en la fuente (>1 = revisar).",
        "es_producto": "Falso para cargos y conceptos que no son mercancía.",
        "categoria_no_producto": "envio, descuento, comision, ajuste_manual, muestra, tarjeta_regalo, etc. Vacío si es producto.",
        "precio_referencia": "Mediana del precio unitario en líneas de venta.",
    },
    "dim_cliente": {
        "_tabla": "Clientes. Una fila por cliente identificado más la fila -1 para ventas sin cliente.",
        "cliente_key": "Clave sustituta (entero). -1 = sin cliente identificado.",
        "codigo_cliente": "Código de cliente de la fuente (Customer ID).",
        "pais_principal": "País más frecuente en sus facturas.",
        "n_paises": "Número de países distintos desde los que compró.",
        "primera_compra": "Fecha de su primera venta.",
        "ultima_compra": "Fecha de su última venta.",
        "cliente_identificado": "Falso solo para la fila -1.",
    },
    "dim_pais": {
        "_tabla": "Países de facturación.",
        "pais_key": "Clave sustituta (entero). -1 = desconocido.",
        "pais": "Nombre del país tal como viene en la fuente.",
    },
    "dim_fecha": {
        "_tabla": "Calendario continuo de años completos. Marcar como tabla de fechas en Power BI usando la columna fecha.",
        "fecha_key": "AAAAMMDD (entero). Clave de la relación.",
        "fecha": "Fecha (tipo fecha). Columna para 'Marcar como tabla de fechas'.",
        "anio": "Año calendario.", "trimestre": "T1-T4.", "trimestre_num": "1-4.",
        "mes_num": "1-12.", "mes_nombre": "Nombre del mes en español. Ordenar por mes_num.",
        "mes_abrev": "Ene, Feb... Ordenar por mes_num.", "anio_mes": "AAAA-MM. Ordenar por anio_mes_num.",
        "anio_mes_num": "AAAAMM (entero) para ordenar.", "semana_iso": "Semana ISO 8601 (1-53).",
        "anio_iso": "Año ISO de la semana.", "dia_mes": "1-31.", "dia_anio": "1-366.",
        "dia_semana_num": "1 = lunes ... 7 = domingo.", "dia_semana_nombre": "Lunes... Ordenar por dia_semana_num.",
        "es_fin_de_semana": "Sábado o domingo.", "es_fin_de_mes": "Último día del mes.",
    },
}
ORDENAR_POR = {"dim_fecha": {"mes_nombre": "mes_num", "mes_abrev": "mes_num", "anio_mes": "anio_mes_num",
                             "dia_semana_nombre": "dia_semana_num", "trimestre": "trimestre_num"}}
OCULTAR = {"fact_ventas": ["fecha_key", "producto_key", "cliente_key", "pais_key", "linea_id"]}


def tipo_pbi(tabla, col, s):
    if col.endswith("_key") or col in ("linea_id",):
        return "Whole Number"
    if col in ("importe", "precio_unitario", "precio_referencia"):
        return "Fixed Decimal Number"
    if pd.api.types.is_bool_dtype(s):
        return "True/False"
    if pd.api.types.is_integer_dtype(s):
        return "Whole Number"
    if pd.api.types.is_float_dtype(s):
        return "Decimal Number"
    if s.dropna().map(type).astype(str).str.contains("date").any():
        return "Date"
    return "Text"


def metadatos(tablas, r):
    meta = {"version_reglas": str(r["version"]), "tablas": {}}
    for t, df in tablas.items():
        cols = []
        for col in df.columns:
            cols.append({"columna": col, "tipo_powerbi": tipo_pbi(t, col, df[col]),
                         "descripcion": DESCRIPCIONES.get(t, {}).get(col, ""),
                         "ordenar_por": ORDENAR_POR.get(t, {}).get(col),
                         "oculta": col in OCULTAR.get(t, []),
                         "nulos": int(df[col].isna().sum()),
                         "ejemplo": None if df[col].dropna().empty else str(df[col].dropna().iloc[min(1, len(df[col].dropna()) - 1)])})
        meta["tablas"][t] = {"descripcion": DESCRIPCIONES.get(t, {}).get("_tabla", ""),
                             "filas": int(len(df)), "columnas": cols,
                             "clave": next((c for c in df.columns if c.endswith("_key")), None) if t.startswith("dim_") else "linea_id"}
    meta["relaciones"] = RELACIONES
    return meta


def valores_esperados(t):
    f = t["fact_ventas"].merge(t["dim_fecha"][["fecha_key", "anio_mes"]], on="fecha_key")

    def calc(g):
        v = g[g.tipo_linea == "venta"]
        brutas = v.importe.sum()
        dev = -g.loc[g.tipo_linea == "devolucion", "importe"].sum()
        fac = v.num_factura.nunique()
        return pd.Series({
            "Ventas Brutas": round(brutas, 2), "Devoluciones": round(dev, 2), "Ventas Netas": round(brutas - dev, 2),
            "Cargos No Producto": round(g.loc[g.tipo_linea == "cargo_no_producto", "importe"].sum(), 2),
            "Facturas": fac, "Ticket Promedio": round(brutas / fac, 2) if fac else None,
            "Clientes Únicos": v.loc[v.cliente_identificado, "cliente_key"].nunique(),
            "% Devoluciones": round(dev / brutas, 4) if brutas else None,
        })
    tot = calc(f).to_frame().T.assign(anio_mes="TOTAL")
    pm = f.groupby("anio_mes").apply(calc, include_groups=False).reset_index()
    res = pd.concat([tot, pm], ignore_index=True)[["anio_mes"] + list(tot.columns[:-1])]
    for col in ["Facturas", "Clientes Únicos"]:
        res[col] = pd.to_numeric(res[col]).astype("Int64")
    return res


def validar(t, entrada_filas, entrada_importe):
    f = t["fact_ventas"]
    chk = []
    chk.append(("Filas fact = filas de entrada", len(f) == entrada_filas, f"{len(f)} vs {entrada_filas}"))
    chk.append(("Importe fact = importe de entrada", abs(f.importe.sum() - entrada_importe) < 0.01,
                f"{f.importe.sum():,.2f} vs {entrada_importe:,.2f}"))
    for col, dim, key in [("fecha_key", "dim_fecha", "fecha_key"), ("producto_key", "dim_producto", "producto_key"),
                          ("cliente_key", "dim_cliente", "cliente_key"), ("pais_key", "dim_pais", "pais_key")]:
        huer = (~f[col].isin(t[dim][key])).sum()
        chk.append((f"Integridad {col} → {dim}", huer == 0, f"{huer} claves sin dimensión"))
        chk.append((f"{dim}.{key} único", t[dim][key].is_unique, ""))
    dfe = pd.to_datetime(t["dim_fecha"]["fecha"])
    cont = (dfe.diff().dropna() == pd.Timedelta(days=1)).all()
    chk.append(("dim_fecha continua y sin duplicados", bool(cont and dfe.is_unique), f"{dfe.min().date()} a {dfe.max().date()}"))
    chk.append(("Sin líneas sin_clasificar", (f.tipo_linea == "sin_clasificar").sum() == 0,
                f"{(f.tipo_linea == 'sin_clasificar').sum()} líneas"))
    return chk


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("--reglas", type=Path, required=True, help="el mismo YAML usado por aplicar_reglas.py")
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()

    r = yaml.safe_load(a.reglas.read_text(encoding="utf-8"))
    df = pd.read_parquet(a.entrada)
    t = construir(df, r)
    a.salida.mkdir(parents=True, exist_ok=True)
    for nombre, tabla in t.items():
        tabla.to_parquet(a.salida / f"{nombre}.parquet", index=False)

    meta = metadatos(t, r)
    (a.salida / "metadatos.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (a.salida / "relaciones.json").write_text(json.dumps(RELACIONES, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy(Path(__file__).resolve().parent.parent / "medidas.dax", a.salida / "medidas.dax")
    ve = valores_esperados(t)
    ve.to_csv(a.salida / "valores_esperados.csv", index=False, encoding="utf-8")

    chk = validar(t, len(df), float(df["importe"].sum()))
    L = ["# Validación del modelo", "", "| Chequeo | Resultado | Detalle |", "|---|---|---|"]
    L += [f"| {n} | {'OK' if ok else '**FALLA**'} | {d} |" for n, ok, d in chk]
    L += ["", "## Tablas", "", "| tabla | filas | columnas |", "|---|---:|---:|"]
    L += [f"| {n} | {len(x):,} | {x.shape[1]} |" for n, x in t.items()]
    multi = t["dim_producto"].query("n_descripciones > 1")
    if len(multi):
        L += ["", f"Nota: {len(multi)} códigos de producto tienen más de una descripción; se usó la más frecuente."]
    multi_c = t["dim_cliente"].query("n_paises > 1") if "n_paises" in t["dim_cliente"] else []
    if len(multi_c):
        L += [f"Nota: {len(multi_c)} clientes compraron desde más de un país; por eso el país va en la fact, no en dim_cliente."]
    (a.salida / "validacion_modelo.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print("\n".join(L))
    print("\nValores esperados (TOTAL):")
    print(ve.iloc[0].to_string())
    if not all(ok for n, ok, _ in chk if not n.startswith("Sin líneas")):
        sys.exit(1)


if __name__ == "__main__":
    main()
