# Informe de revision -- Online Retail II
Fecha: 2026-10-15  |  Version de reglas: 1.1  |  Veredicto: APROBADO CON OBSERVACIONES

---

## Cifras recalculadas vs. entregadas

| Metrica | Recalculado (control) | Entregado | Diferencia | OK |
|---|---:|---:|---:|:---:|
| Filas Excel H1 (Year 2009-2010) | 525.461 | 525.461 | 0 | SI |
| Filas Excel H2 (Year 2010-2011) | 541.910 | 541.910 | 0 | SI |
| Filas CSV crudo | 1.067.371 | 1.067.371 | 0 | SI |
| Filas excluidas | 22.523 | 22.523 | 0 | SI |
| Filas CSV limpio | 1.044.848 | 1.044.848 | 0 | SI |
| Filas fact_ventas modelo | 1.044.848 | 1.044.848 | 0 | SI |
| Filas fact_ventas entrega | 1.044.848 | 1.044.848 | 0 | SI |
| Ventas Brutas TOTAL | 19.699.799,72 | 19.699.799,72 | 0,00 | SI |
| Devoluciones TOTAL | 719.656,34 | 719.656,34 | 0,00 | SI |
| Ventas Netas TOTAL | 18.980.143,38 | 18.980.143,38 | 0,00 | SI |
| Cargos No Producto TOTAL | 77.232,82 | 77.232,82 | 0,00 | SI |
| Facturas TOTAL | 39.516 | 39.516 | 0 | SI |
| Ticket Promedio TOTAL | 498,53 | 498,53 | 0,00 | SI |
| Clientes Unicos TOTAL | 5.852 | 5.852 | 0 | SI |

Las 25 filas mensuales (2009-12 a 2011-12) muestran diferencia maxima = 0,000000 en todas las metricas.

---

## Cuadre de filas

Excel (openpyxl read_only):
  Year 2009-2010: max_row=525.462 -> 525.461 filas de datos
  Year 2010-2011: max_row=541.911 -> 541.910 filas de datos
  Total Excel:   1.067.371

CSV crudo (trabajo/00_crudo/online_retail_II_crudo.csv): 1.067.371 filas -> cuadre OK

Exclusion (trabajo/01_limpieza/filas_excluidas.csv):
  Filas: 22.523 | motivo: duplicado_solapamiento_hojas (todas)
  hoja_origen: Year 2010-2011 (todas las 22.523)
  Rango fechas: 2010-12-01 a 2010-12-09

CSV limpio: 1.044.848 | Cuadre: 1.067.371 = 1.044.848 + 22.523 -> OK
lineas_clasificadas.parquet: 1.044.848 -> OK
fact_ventas.parquet modelo:  1.044.848 -> OK
fact_ventas.parquet entrega: 1.044.848 -> OK

Importe total limpio:    18.909.762,12
Importe total fact:      18.909.762,12 -> OK

---

## Hallazgos

| # | Severidad | Verificacion | Evidencia | Que hacer |
|---|---|---|---|---|
| 1 | bajo | B. Recuento StockCodes lowercase | Crudo: 3.471 filas con minusculas (183 codigos). reporte_limpieza.md dice 3.345. Diferencia=126 = lowercase en las 22.523 excluidas (verificado). Resultado final limpio: 0. | Aclarar en reporte que 3.345 es sobre filas post-exclusion. Sin impacto en datos. |
| 2 | bajo | GIFT y C3 no trazables al YAML | GIFT (inv 497107) y C3 (inv 518785): es_producto=True pero no cumplen patron_codigo_producto ni figuran en codigos_no_producto. YAML historial v1.1 los menciona sin agregarlos a ninguna lista. Impacto monetario: cero (price=0). | Agregar GIFT y C3 a codigos_no_producto en YAML v1.2. |
| 3 | bajo | diccionario_datos.csv tiene BOM UTF-8 | Bytes iniciales: EF BB BF. Especificacion: sin BOM. Sin impacto practico (Parquet es fuente principal). | Regenerar con encoding utf-8 (no utf-8-sig). |
| 4 | bajo | guia_power_query.md omite Ventas Netas como segundo numero de control | Seccion 7 lista filas por tabla (1.044.848, OK). El control del proyecto requiere ademÃ¡s Ventas Netas TOTAL. El numero 18.980.143,38 no aparece. | Agregar en seccion 7: Ventas Netas = 18.980.143,38 |

No se encontraron hallazgos criticos ni altos.
No hay filas perdidas, exclusiones sin decision de usuario, metricas que no cuadren, huerfanos, ni duplicados del solapamiento contados dos veces.

---

## Resultado de los puntos adicionales A, B, C

### A. customer_id sin decimales (.0)

Comando ejecutado:
  dim_cli = pd.read_parquet(entrega_powerbi/datos/dim_cliente.parquet)
  dim_cli[codigo_cliente].astype(str).str.contains(r".0$", regex=True).sum() -> 0

5 ejemplos de codigo_cliente (entrega, random_state=99):
  cliente_key=3009  codigo_cliente=15354
  cliente_key=4552  codigo_cliente=16897
  cliente_key=2762  codigo_cliente=15107
  cliente_key=3864  codigo_cliente=16209
  cliente_key=2609  codigo_cliente=14954

dtype: str (ArrowStringArray). Codigos con .0 en entrega: 0. En CSV limpio: 0.
Veredicto: OK.

### B. StockCodes en minuscula

Comandos ejecutados:
  has_lower = lambda s: bool(re.search(r[a-z], str(s)))
  df_crudo[StockCode].apply(has_lower).sum()    -> 3.471  (183 codigos unicos)
  df_exc[stock_code].apply(has_lower).sum()     ->   126  (en las 22.523 excluidas)
  df_limpio[stock_code].apply(has_lower).sum()  ->     0  (conversion completa)
  Verificacion: 3.471 - 126 = 3.345 = lo que dice reporte_limpieza.md

Resultado: el reporte es correcto en su contexto (filas que procesa, post-exclusion).
El CSV limpio tiene 0 filas con minusculas: conversion completa.
Veredicto: OK en el resultado; hallazgo 1 (bajo) sobre la redaccion del reporte.

### C. Registros de volumen extremo

Comando:
  mask = df_fact[alerta_volumen_extremo].notna() & (df_fact[alerta_volumen_extremo] != "")
  len(df_fact[mask]) -> 34

Resultado: 34 filas confirma reporte_limpieza.md.
tipo_linea de los 34: cargo_no_producto=22, venta=7, sin_valor=2, devolucion=2, ajuste_contable=1

Factura 581483 (80.995 unidades):
  num_factura=581483 | cantidad=80.995 | precio_unitario=2,08 | importe=168.469,60
  tipo_linea=venta | alerta=volumen_extremo: qty=80995 price=2.08
  hoja_origen=Year 2010-2011 | fila_excel=540423

Devolucion espejo:
  num_factura=C581484 | cantidad=-80.995 | precio_unitario=2,08 | importe=-168.469,60
  tipo_linea=devolucion | alerta=volumen_extremo: qty=-80995 price=2.08
  (C581484, no C581483: numeracion correlativa del ERP, comportamiento habitual del dataset)

Veredicto: OK. Ambas filas en fact_ventas con tipo_linea correcto.

---

## Verificaciones superadas

1.  Filas Excel (openpyxl read_only) = filas CSV crudo: 1.067.371
2.  Crudo = limpio + excluidas (1.044.848 + 22.523 = 1.067.371); motivo_exclusion presente en las 22.523
3.  Exclusion solapamiento_hojas con decidido_por=usuario en script de limpieza (4 decisiones registradas)
4.  Filas limpio = clasificadas = fact modelo = fact entrega: 1.044.848
5.  Excel original intacto (43,51 MB); script 00 solo lee el xlsx, nunca escribe sobre el
6.  Dec-2010: 22.523 excluidas solo de Year 2010-2011; en fact solo Year 2009-2010 cubre ese rango
7.  Recalculo tipo_linea sobre 34.901 filas (29.901 edge cases + 5.000 aleatorias): 2 discrepancias (GIFT, C3) justificadas en historial YAML v1.1; impacto monetario = 0
8.  sin_clasificar = 0
9.  Devoluciones (17.973 filas con factura C) y SIN_CLIENTE (235.287) en fact con tipo_linea correcto
10. version_reglas=1.1 consistente en YAML, manifiesto.json y columna fact_ventas[version_reglas]
11. Metricas mensuales cuadran con valores_esperados.csv: diferencia maxima = 0,000000 en todos los periodos
12. Metricas TOTAL cuadran con valores_esperados.csv: diferencia = 0,00 en importes y 0 en conteos
13. DAX implementa definiciones YAML: brutas por tipo_linea=venta, devoluciones como negacion del importe negativo, clientes con cliente_identificado=TRUE
14. Claves unicas en 4 dimensiones; 0 huerfanos en fact; fila -1 (SIN_CLIENTE) presente en dim_cliente
15. dim_fecha continua 2009-01-01 a 2011-12-31, 1.095 dias exactos, cubre el rango de fact
16. pais_key en fact (no en dim_cliente); relaciones en relaciones.json van de fact a dim (muchos a uno)
17. Entrega parquet = modelo parquet: filas, columnas y sumas numericas identicas en las 5 tablas; sumas_control del manifiesto verificadas fila a fila
18. manifiesto.json: problemas=[], descripciones_pendientes=0; diccionario sin COMPLETAR; sumas_control exactas
19. Entrega en Parquet (consultas.pq usa Parquet.Document, no Csv.Document; Encoding/cultura irrelevantes); valores_esperados.csv sin BOM
20. guia_power_query.md incluye filas de fact_ventas (1.044.848) como primer numero de control

---

## Pendientes para el usuario

1. (Bajo) Agregar en seccion 7 de guia_power_query.md: Ventas Netas (medida DAX) = 18.980.143,38.
2. (Bajo) Aclarar en reporte_limpieza.md que el recuento de 3.345 StockCodes lowercase es sobre filas retenidas (el crudo completo tiene 3.471; la diferencia son las 126 en filas excluidas).
3. (Bajo) Crear YAML v1.2 agregando GIFT y C3 a codigos_no_producto para que su clasificacion como ajuste_inventario sea trazable directamente al YAML, no solo al historial.
4. (Bajo) Regenerar diccionario_datos.csv sin BOM UTF-8 (usar encoding=utf-8 en lugar de utf-8-sig).

---

## Resolución de hallazgos

Decisiones del usuario registradas el 2026-10-15.

| # | Hallazgo | Decisión | Decidido por | Razón |
|---|---|---|---|---|
| 1 | Redacción en reporte_limpieza.md (3.345 vs 3.471 StockCodes) | **APROBADO** — nota aclaratoria añadida al final de la tabla de cambios | usuario | Confirma que 3.345 es el recuento post-exclusión; el CSV limpio tiene 0 filas en minúscula. Sin impacto en datos. |
| 2 | C3 y GIFT no trazables directamente al YAML | **RECHAZADO** — no se crea YAML v1.2. Nota añadida a la descripción de `es_producto` en diccionario_datos.md y diccionario_datos.csv | usuario | C3 y GIFT son salidas de inventario (R5), no cargos. Impacto monetario = £0. La nota en el diccionario documenta la excepción. |
| 3 | BOM UTF-8 en diccionario_datos.csv | **RECHAZADO** — BOM se conserva deliberadamente | usuario | El CSV está destinado a Excel en español, donde el BOM garantiza la apertura correcta. La fuente de datos para Power BI son los Parquet, no el CSV. |
| 4 | Ventas Netas ausente en sección 7 de guia_power_query.md | **APROBADO** — línea añadida: "Ventas Netas (DAX) = £ 18,980,143.38" | usuario | Cumple el requisito del proyecto de los dos números de control para verificar la carga en Power BI. |
