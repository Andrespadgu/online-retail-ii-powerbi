#!/usr/bin/env python3
"""Empaqueta una carpeta de tablas (Parquet) como entrega lista para Power BI.

Uso:
    python exportar_entrega.py CARPETA_MODELO --salida CARPETA_ENTREGA [--formato parquet|csv|ambos]

CARPETA_MODELO: tablas *.parquet y, si existen, metadatos.json, relaciones.json, medidas.dax,
valores_esperados.csv (los produce el script 03_construir_modelo.py). Sin metadatos.json
los tipos se infieren y las descripciones quedan marcadas "COMPLETAR".

Salida:
    datos/<tabla>.parquet|csv     archivos para Power BI (nombres estables: se reemplazan al actualizar)
    diccionario_datos.md / .csv   tabla, columna, tipo, descripción, nulos, ejemplo
    guia_power_query.md           pasos de carga y actualización con el código M de cada tabla
    consultas.pq                  todo el código M en un solo archivo
    manifiesto.json               filas, columnas, hash y totales de control de cada archivo
    medidas.dax, valores_esperados.csv, relaciones.json (copiados si existen)
"""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

M_TIPO = {"Whole Number": "Int64.Type", "Fixed Decimal Number": "Currency.Type", "Decimal Number": "type number",
          "True/False": "type logical", "Date": "type date", "Date/Time": "type datetime", "Text": "type text"}
ES_TIPO = {"Whole Number": "Número entero", "Fixed Decimal Number": "Número decimal fijo", "Decimal Number": "Número decimal",
           "True/False": "Verdadero/falso", "Date": "Fecha", "Date/Time": "Fecha y hora", "Text": "Texto"}


def inferir_tipo(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "True/False"
    if pd.api.types.is_integer_dtype(s):
        return "Whole Number"
    if pd.api.types.is_float_dtype(s):
        return "Decimal Number"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "Date/Time"
    if s.dropna().map(type).astype(str).str.contains("datetime.date").any():
        return "Date"
    return "Text"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def a_csv(df: pd.DataFrame, ruta: Path):
    d = df.copy()
    for col in d.columns:
        s = d[col]
        if pd.api.types.is_bool_dtype(s):
            d[col] = s.map({True: "true", False: "false"})
        elif pd.api.types.is_datetime64_any_dtype(s):
            d[col] = s.dt.strftime("%Y-%m-%d %H:%M:%S")
        elif s.dropna().map(type).astype(str).str.contains("datetime.date").any():
            d[col] = pd.to_datetime(s).dt.strftime("%Y-%m-%d")
    # UTF-8 sin BOM, coma, punto decimal, nulos vacíos. Power Query lo lee con Encoding=65001 y cultura en-US.
    d.to_csv(ruta, index=False, encoding="utf-8", sep=",", float_format="%.4f", lineterminator="\n")


def codigo_m(tabla: str, cols: list, fmt: str) -> str:
    tipos = ",\n        ".join(f'{{"{c["columna"]}", {M_TIPO.get(c["tipo_powerbi"], "type text")}}}' for c in cols)
    if fmt == "parquet":
        origen = f'    Origen = Parquet.Document(File.Contents(RutaDatos & "{tabla}.parquet")),\n'
        paso, prev = "Tipos", "Origen"
    else:
        origen = (f'    Origen = Csv.Document(File.Contents(RutaDatos & "{tabla}.csv"),\n'
                  f'        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),\n'
                  f'    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),\n')
        paso, prev = "Tipos", "Encabezados"
    cultura = ', "en-US"' if fmt == "csv" else ""
    return (f"// {tabla}\nlet\n{origen}"
            f"    {paso} = Table.TransformColumnTypes({prev}, {{\n        {tipos}\n    }}{cultura})\nin\n    {paso}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modelo", type=Path)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--formato", choices=["parquet", "csv", "ambos"], default="parquet")
    a = ap.parse_args()

    tablas = {p.stem: pd.read_parquet(p) for p in sorted(a.modelo.glob("*.parquet"), key=lambda x: (not x.stem.startswith("fact"), x.stem))}
    if not tablas:
        sys.exit(f"ERROR: no hay archivos .parquet en {a.modelo}")
    meta_p = a.modelo / "metadatos.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {"tablas": {}, "relaciones": []}
    if (a.modelo / "relaciones.json").exists() and not meta.get("relaciones"):
        meta["relaciones"] = json.loads((a.modelo / "relaciones.json").read_text(encoding="utf-8"))

    # Completar metadatos faltantes; nunca inventar descripciones
    for t, df in tablas.items():
        mt = meta["tablas"].setdefault(t, {"descripcion": "COMPLETAR", "columnas": []})
        conocidas = {c["columna"]: c for c in mt["columnas"]}
        cols = []
        for col in df.columns:
            c = conocidas.get(col, {"columna": col, "tipo_powerbi": inferir_tipo(df[col]), "descripcion": "",
                                    "ordenar_por": None, "oculta": False})
            c["descripcion"] = c.get("descripcion") or "COMPLETAR"
            c["nulos"] = int(df[col].isna().sum())
            ej = df[col].dropna()
            c["ejemplo"] = None if ej.empty else str(ej.iloc[min(1, len(ej) - 1)])
            cols.append(c)
        mt["columnas"] = cols
        mt["filas"] = int(len(df))

    datos = a.salida / "datos"
    datos.mkdir(parents=True, exist_ok=True)
    formatos = ["parquet", "csv"] if a.formato == "ambos" else [a.formato]
    manif = {"generado": datetime.now().isoformat(timespec="seconds"), "version_reglas": meta.get("version_reglas"),
             "formatos": formatos, "archivos": {}}
    problemas = []
    for t, df in tablas.items():
        for fmt in formatos:
            p = datos / f"{t}.{fmt}"
            if fmt == "parquet":
                df.to_parquet(p, index=False)
                back = pd.read_parquet(p)
            else:
                a_csv(df, p)
                back = pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8")
            # Verificación: releer y comparar
            if len(back) != len(df) or list(back.columns) != list(df.columns):
                problemas.append(f"{p.name}: filas/columnas no coinciden al releer")
            control = {}
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]) and not col.endswith("_key"):
                    orig = float(df[col].sum())
                    rel = float(pd.to_numeric(back[col].replace("", None)).sum())
                    control[col] = round(orig, 4)
                    if abs(orig - rel) > max(0.01, abs(orig) * 1e-9):
                        problemas.append(f"{p.name}: suma de {col} cambió al releer ({orig} vs {rel})")
            manif["archivos"][p.name] = {"tabla": t, "filas": int(len(df)), "columnas": int(df.shape[1]),
                                         "bytes": p.stat().st_size, "sha256": sha256(p), "sumas_control": control}

    # Diccionario
    filas_dic = []
    for t, mt in meta["tablas"].items():
        if t not in tablas:
            continue
        for c in mt["columnas"]:
            filas_dic.append({"tabla": t, "columna": c["columna"], "tipo_powerbi": ES_TIPO.get(c["tipo_powerbi"], c["tipo_powerbi"]),
                              "descripcion": c["descripcion"], "ordenar_por": c.get("ordenar_por") or "",
                              "oculta": "sí" if c.get("oculta") else "", "nulos": c["nulos"], "ejemplo": c["ejemplo"] or ""})
    dic = pd.DataFrame(filas_dic)
    dic.to_csv(a.salida / "diccionario_datos.csv", index=False, encoding="utf-8-sig")
    L = ["# Diccionario de datos", "", f"Generado: {manif['generado']} · Reglas v{meta.get('version_reglas') or 'N/D'}", ""]
    for t, mt in meta["tablas"].items():
        if t not in tablas:
            continue
        L += [f"## {t}", "", f"{mt.get('descripcion', '')}  ", f"Filas: {mt['filas']:,}", "",
              "| Columna | Tipo | Descripción | Nulos | Ejemplo |", "|---|---|---|---:|---|"]
        for c in mt["columnas"]:
            extra = []
            if c.get("ordenar_por"):
                extra.append(f"ordenar por `{c['ordenar_por']}`")
            if c.get("oculta"):
                extra.append("ocultar")
            desc = c["descripcion"] + (f" _({'; '.join(extra)})_" if extra else "")
            L.append(f"| `{c['columna']}` | {ES_TIPO.get(c['tipo_powerbi'], c['tipo_powerbi'])} | {desc} | {c['nulos']} | {c['ejemplo'] or ''} |")
        L.append("")
    (a.salida / "diccionario_datos.md").write_text("\n".join(L), encoding="utf-8")

    # Código M y guía
    fmt_guia = "parquet" if "parquet" in formatos else "csv"
    bloques = [codigo_m(t, meta["tablas"][t]["columnas"], fmt_guia) for t in tablas]
    (a.salida / "consultas.pq").write_text("\n".join(bloques), encoding="utf-8")
    plantilla = (Path(__file__).resolve().parent.parent / "guia_plantilla.md").read_text(encoding="utf-8")
    rel = "\n".join(f"| `{r['desde']}` | `{r['hacia']}` | Varios a uno (*:1) | Simple |" for r in meta.get("relaciones", []))
    orden = "\n".join(f"  - `{t}[{c['columna']}]` → ordenar por `{c['ordenar_por']}`"
                      for t, mt in meta["tablas"].items() if t in tablas for c in mt["columnas"] if c.get("ordenar_por")) or "  - (ninguna)"
    ocultas = "\n".join(f"  - `{t}[{c['columna']}]`" for t, mt in meta["tablas"].items() if t in tablas
                        for c in mt["columnas"] if c.get("oculta")) or "  - (ninguna)"
    conteo = "\n".join(f"| {v['tabla']} | {v['filas']:,} |" for k, v in manif["archivos"].items() if k.endswith(fmt_guia))
    guia = (plantilla.replace("{{FORMATO}}", fmt_guia).replace("{{EXT}}", fmt_guia)
            .replace("{{CONSULTAS}}", "\n".join(f"```powerquery\n{b}```" for b in bloques))
            .replace("{{RELACIONES}}", rel or "| (sin relaciones definidas) | | | |")
            .replace("{{ORDEN}}", orden).replace("{{OCULTAS}}", ocultas).replace("{{CONTEO}}", conteo)
            .replace("{{TABLAS}}", ", ".join(f"`{t}`" for t in tablas))
            .replace("{{FECHA}}", manif["generado"]).replace("{{VERSION}}", str(meta.get("version_reglas") or "N/D")))
    (a.salida / "guia_power_query.md").write_text(guia, encoding="utf-8")

    for extra in ["medidas.dax", "valores_esperados.csv", "relaciones.json"]:
        if (a.modelo / extra).exists():
            shutil.copy(a.modelo / extra, a.salida / extra)
    manif["problemas"] = problemas
    manif["descripciones_pendientes"] = int((dic["descripcion"] == "COMPLETAR").sum())
    (a.salida / "manifiesto.json").write_text(json.dumps(manif, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"salida": str(a.salida), "formatos": formatos,
                      "archivos": {k: v["filas"] for k, v in manif["archivos"].items()},
                      "descripciones_pendientes": manif["descripciones_pendientes"], "problemas": problemas},
                     ensure_ascii=False, indent=2))
    if problemas:
        sys.exit(1)


if __name__ == "__main__":
    main()
