#!/usr/bin/env python3
"""Clasifica cada línea de una tabla de transacciones retail con reglas fijas y versionadas.

Uso:
    python aplicar_reglas.py ENTRADA(.csv|.parquet) --reglas reglas_retail.yaml --salida CARPETA [--estricto]

Salidas en CARPETA:
    lineas_clasificadas.parquet   tabla original + columnas de clasificación
    resumen_reglas.md             conteos, importes por tipo, cuadre y pendientes
    resumen_reglas.json           lo mismo en formato máquina (para comparar entre corridas)

Código de salida: 0 OK; 2 si hay líneas sin clasificar o códigos no reconocidos y se usó --estricto.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

ORDEN_TIPOS = ["venta", "devolucion", "cargo_no_producto", "ajuste_inventario",
               "ajuste_contable", "sin_valor", "cancelado", "sin_clasificar"]


def leer(ruta: Path) -> pd.DataFrame:
    if ruta.suffix.lower() == ".parquet":
        return pd.read_parquet(ruta)
    return pd.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8")


def normalizar_cliente(s: pd.Series, sin_id: str) -> pd.Series:
    s = s.astype("string").str.strip()
    s = s.str.replace(r"\.0+$", "", regex=True)           # 13085.0 -> 13085
    s = s.mask(s.isna() | (s == "") | s.str.lower().isin(["nan", "none", "null"]), sin_id)
    return s


def clasificar(df: pd.DataFrame, r: dict) -> pd.DataFrame:
    c = r["columnas"]
    faltan = [k for k in ["factura", "codigo", "cantidad", "precio", "fecha"] if not c.get(k) or c[k] not in df.columns]
    if faltan:
        sys.exit(f"ERROR: faltan columnas obligatorias {faltan}. Revisa `columnas:` en el YAML. "
                 f"Columnas del archivo: {list(df.columns)}")

    out = df.copy()
    fac = out[c["factura"]].astype("string").str.strip()
    cod = out[c["codigo"]].astype("string").str.strip()
    cant = pd.to_numeric(out[c["cantidad"]], errors="raise")
    prec = pd.to_numeric(out[c["precio"]], errors="raise")
    out[c["cantidad"]] = cant
    out[c["precio"]] = prec
    out[c["fecha"]] = pd.to_datetime(out[c["fecha"]], errors="raise")

    # Conceptos que no son producto
    cod_up = cod.str.upper()
    categoria = pd.Series(pd.NA, index=out.index, dtype="string")
    for cat, lista in (r.get("codigos_no_producto") or {}).items():
        categoria = categoria.mask(categoria.isna() & cod_up.isin([x.upper() for x in lista]), cat)
    for cat, patron in (r.get("patrones_no_producto") or {}).items():
        categoria = categoria.mask(categoria.isna() & cod.str.contains(patron, flags=re.IGNORECASE, regex=True, na=False), cat)
    es_producto = categoria.isna()

    patron_ok = cod.str.fullmatch(r["patron_codigo_producto"], na=False)
    no_reconocido = es_producto & ~patron_ok

    pref_dev = fac.str.upper().str.startswith(r["prefijo_devolucion"].upper(), na=False)
    pref_aj = fac.str.upper().str.startswith(r["prefijo_ajuste_contable"].upper(), na=False)

    cancelado = pd.Series(False, index=out.index)
    if c.get("estado") and c["estado"] in out.columns:
        estados = [e.lower() for e in r.get("estados_cancelado", [])]
        cancelado = out[c["estado"]].astype("string").str.strip().str.lower().isin(estados).fillna(False)

    # Primera regla que aplica gana. El orden ES la regla: no lo cambies sin subir la versión.
    reglas = [
        ("R1_cancelado",          cancelado,                                   "cancelado"),
        ("R2_ajuste_contable",    pref_aj | (prec < 0),                        "ajuste_contable"),
        ("R3_no_producto",        ~es_producto,                                "cargo_no_producto"),
        ("R4_devolucion",         pref_dev & (cant < 0) & (prec > 0),          "devolucion"),
        ("R5_ajuste_inventario",  ~pref_dev & (cant < 0),                      "ajuste_inventario"),
        ("R6_sin_valor",          (prec == 0) & (cant > 0),                    "sin_valor"),
        ("R7_venta",              ~pref_dev & (cant > 0) & (prec > 0),         "venta"),
    ]
    tipo = pd.Series(pd.NA, index=out.index, dtype="string")
    regla = pd.Series(pd.NA, index=out.index, dtype="string")
    for rid, mask, t in reglas:
        m = tipo.isna() & mask.fillna(False)
        tipo = tipo.mask(m, t)
        regla = regla.mask(m, rid)
    tipo = tipo.fillna("sin_clasificar")
    regla = regla.fillna("R0_sin_regla")

    out["importe"] = (cant * prec).round(4)
    out["tipo_linea"] = tipo
    out["regla_aplicada"] = regla
    out["es_producto"] = es_producto.astype(bool)
    out["categoria_no_producto"] = categoria
    out["cuenta_en_ventas"] = tipo.isin(["venta", "devolucion"])
    out["alerta_codigo"] = no_reconocido.map({True: "codigo_no_reconocido", False: pd.NA}).astype("string")

    sin_id = r["cliente_sin_identificar"]
    if c.get("cliente") and c["cliente"] in out.columns:
        out[c["cliente"]] = normalizar_cliente(out[c["cliente"]], sin_id)
    else:
        out["cliente"] = sin_id
        c["cliente"] = "cliente"
    out["cliente_identificado"] = out[c["cliente"]] != sin_id
    out["version_reglas"] = str(r["version"])
    return out


def resumen(out: pd.DataFrame, r: dict, entrada: Path) -> dict:
    c = r["columnas"]
    g = (out.groupby("tipo_linea", dropna=False)
            .agg(lineas=("importe", "size"), importe=("importe", "sum"))
            .reindex(ORDEN_TIPOS).fillna(0))
    v = out[out.tipo_linea == "venta"]
    d = out[out.tipo_linea == "devolucion"]
    brutas = float(v["importe"].sum())
    devol = float(-d["importe"].sum())
    facturas = int(v[c["factura"]].nunique())
    met = {
        "ventas_brutas": round(brutas, 2),
        "devoluciones": round(devol, 2),
        "ventas_netas": round(brutas - devol, 2),
        "cargos_no_producto": round(float(out.loc[out.tipo_linea == "cargo_no_producto", "importe"].sum()), 2),
        "facturas": facturas,
        "ticket_promedio": round(brutas / facturas, 4) if facturas else None,
        "clientes_unicos": int(v.loc[v.cliente_identificado, c["cliente"]].nunique()),
        "pct_ventas_sin_cliente": round(float(v.loc[~v.cliente_identificado, "importe"].sum()) / brutas * 100, 2) if brutas else None,
    }
    no_rec = (out[out.alerta_codigo.notna()]
                .groupby(c["codigo"]).agg(lineas=("importe", "size"), importe=("importe", "sum"),
                                          ejemplo=(c.get("descripcion") or c["codigo"], "first"))
                .sort_values("importe", key=abs, ascending=False))
    return {
        "entrada": str(entrada), "generado": datetime.now().isoformat(timespec="seconds"),
        "version_reglas": str(r["version"]), "filas": int(len(out)),
        "por_tipo": {k: {"lineas": int(row.lineas), "importe": round(float(row.importe), 2)} for k, row in g.iterrows()},
        "por_regla": out["regla_aplicada"].value_counts().to_dict(),
        "por_categoria_no_producto": out.loc[~out.es_producto].groupby("categoria_no_producto")["importe"].agg(["size", "sum"]).round(2).to_dict("index"),
        "metricas": met,
        "cuadre_importe": {"total_entrada": round(float(out["importe"].sum()), 2),
                           "suma_por_tipo": round(float(g["importe"].sum()), 2)},
        "sin_clasificar": int((out.tipo_linea == "sin_clasificar").sum()),
        "codigos_no_reconocidos": {str(k): {"lineas": int(x.lineas), "importe": round(float(x.importe), 2), "ejemplo": str(x.ejemplo)}
                                   for k, x in no_rec.head(50).iterrows()},
    }


def a_markdown(s: dict, r: dict) -> str:
    L = [f"# Resumen de reglas de negocio — v{s['version_reglas']}", "",
         f"- Entrada: `{s['entrada']}`  ", f"- Generado: {s['generado']}  ", f"- Filas: {s['filas']:,}", ""]
    pend = []
    if s["sin_clasificar"]:
        pend.append(f"{s['sin_clasificar']} líneas **sin clasificar** (ninguna regla aplica). Revisar antes de publicar.")
    if s["codigos_no_reconocidos"]:
        pend.append(f"{len(s['codigos_no_reconocidos'])} códigos **no reconocidos** (no parecen producto y no están en las listas). "
                    "Decidir con el usuario y agregarlos al YAML (subiendo la versión).")
    if pend:
        L += ["## ⚠ Pendientes", ""] + [f"- {p}" for p in pend] + [""]
    L += ["## Métricas con estas reglas", "", "| Métrica | Valor | Definición |", "|---|---:|---|"]
    for k, v in s["metricas"].items():
        L.append(f"| {k} | {v:,} | {r['metricas'].get(k, '')} |" if v is not None else f"| {k} | — | |")
    L += ["", "## Líneas por tipo", "", "| tipo_linea | líneas | importe |", "|---|---:|---:|"]
    for k, v in s["por_tipo"].items():
        L.append(f"| {k} | {v['lineas']:,} | {v['importe']:,.2f} |")
    cq = s["cuadre_importe"]
    ok = abs(cq["total_entrada"] - cq["suma_por_tipo"]) < 0.01
    L += ["", f"**Cuadre:** importe total {cq['total_entrada']:,.2f} = suma por tipo {cq['suma_por_tipo']:,.2f} → {'OK' if ok else 'NO CUADRA'}", ""]
    if s["por_categoria_no_producto"]:
        L += ["## Conceptos que no son producto", "", "| categoría | líneas | importe |", "|---|---:|---:|"]
        for k, v in s["por_categoria_no_producto"].items():
            L.append(f"| {k} | {int(v['size']):,} | {v['sum']:,.2f} |")
        L.append("")
    if s["codigos_no_reconocidos"]:
        L += ["## Códigos no reconocidos (top 50 por importe)", "", "| código | líneas | importe | ejemplo |", "|---|---:|---:|---|"]
        for k, v in s["codigos_no_reconocidos"].items():
            L.append(f"| `{k}` | {v['lineas']} | {v['importe']:,.2f} | {v['ejemplo']} |")
        L.append("")
    L += ["## Reglas aplicadas", "", "| regla | líneas |", "|---|---:|"] + [f"| {k} | {v:,} |" for k, v in s["por_regla"].items()]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("--reglas", type=Path, default=Path(__file__).resolve().parent.parent / "reglas_retail.yaml")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--estricto", action="store_true", help="falla si quedan líneas sin clasificar o códigos no reconocidos")
    a = ap.parse_args()

    r = yaml.safe_load(a.reglas.read_text(encoding="utf-8"))
    a.salida.mkdir(parents=True, exist_ok=True)
    df = leer(a.entrada)
    out = clasificar(df, r)
    s = resumen(out, r, a.entrada)

    out.to_parquet(a.salida / "lineas_clasificadas.parquet", index=False)
    (a.salida / "resumen_reglas.json").write_text(json.dumps(s, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (a.salida / "resumen_reglas.md").write_text(a_markdown(s, r), encoding="utf-8")
    # Copia de las reglas usadas, para que la corrida sea auditable
    (a.salida / f"reglas_v{r['version']}.yaml").write_text(a.reglas.read_text(encoding="utf-8"), encoding="utf-8")

    print(json.dumps({"filas": s["filas"], "version_reglas": s["version_reglas"], "metricas": s["metricas"],
                      "sin_clasificar": s["sin_clasificar"], "codigos_no_reconocidos": list(s["codigos_no_reconocidos"])},
                     ensure_ascii=False, indent=2))
    if a.estricto and (s["sin_clasificar"] or s["codigos_no_reconocidos"]):
        sys.exit(2)


if __name__ == "__main__":
    main()
