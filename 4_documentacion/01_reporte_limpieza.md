# Reporte de limpieza — online_retail_II_crudo.csv

Generado: 2026-10-15 12:25

## Cuadre de filas

| Concepto | Valor |
|---|---|
| Filas entrada (crudo) | **1,067,371** |
| Filas limpias (salida) | **1,044,848** |
| Filas excluidas (filas_excluidas.csv) | **22,523** |
| Cuadre (1,067,371 = 1,044,848 + 22,523) | **OK** |

## Cuadre de importes (Quantity × Price)

| Concepto | £ |
|---|---|
| Total crudo (1,067,371 filas) | 19,287,250.57 |
| Excluido D1 (solapamiento) | 377,488.45 |
| Total limpio (1,044,848 filas) | 18,909,762.12 |
| Diferencia residual (debe ser ~0) | -0.00 |

> Nota: este importe incluye cantidades negativas (devoluciones, ajustes) porque no se clasifica en este paso. Las métricas de negocio (Ventas Netas, Devoluciones) las calcula el paso 2 con reglas_retail.yaml.

## Cambios aplicados

| # | Paso | Tipo | Columna | Afectados | Detalle |
|---|---|---|---|---|---|
| 1 | Renombrar columnas a snake_case | SEGURO | — | 8 | Invoice→invoice; StockCode→stock_code; Description→description; Quantity→quantity; InvoiceDate→invoice_date; Price→price; Customer ID→customer_id; Country→country |
| 2 | Espacios normalizados (trim + dobles → uno) | SEGURO | stock_code | 1 |  |
| 3 | Espacios normalizados (trim + dobles → uno) | SEGURO | description | 247,906 |  |
| 4 | Excluir: duplicado_solapamiento_hojas | DECISIÓN | — | 22,523 | decisión 'solapamiento_hojas' |
| 5 | Description nula/disfrazada → NA + alerta_desc_vacia | SEGURO | description | 4,402 | Incluye: vacíos (4,382), '?' (92), 'missing'/'MISSING' (30), '??' (7) |
| 6 | Description: variantes de capitalización → forma más frecuente | SEGURO | description | 68 | p. ej. 'amazon'/'Amazon' → 'AMAZON'; 68 filas actualizadas |
| 7 | StockCode minúsculas → MAYÚSCULAS (todos, incl. 10 con desc. distinta) | DECISIÓN | stock_code | 3,345 | 183 códigos; los 10 con desc. diferente unificados por decisión 'stock_code_lower_10' (solo código, descripciones intactas) |
| 8 | D2: duplicados intra-hoja marcados (conservados) | DECISIÓN | — | 11,812 | Impacto: £54,228.42 | H1=6,865; H2=4,947 |
| 9 | Quantity texto → Int64 | SEGURO | quantity | 1,044,848 | 0 no convertibles |
| 10 | Price texto → float64 | SEGURO | price | 1,044,848 | 0 no convertibles |
| 11 | InvoiceDate texto → datetime64 | SEGURO | invoice_date | 1,044,848 | formato '%Y-%m-%d %H:%M:%S'; 0 NaT |
| 12 | D5: volumen extremo marcado (conservado) | DECISIÓN | — | 34 | |quantity|>10,000 o price>10,000 |

> **Nota (paso 7):** El CSV crudo contiene 3.471 filas con StockCode en minúscula (183 códigos); 126 de esas filas estaban en las 22.523 excluidas por solapamiento. El script opera sobre las 3.345 filas retenidas tras la exclusión. El CSV limpio tiene 0 filas en minúscula. (Verificado en la revisiÃ³n de control de calidad, 2026-10-15.)

## Decisiones del usuario

| Decisión | Acción | Decidido por | Fecha | Nota |
|---|---|---|---|---|
| solapamiento_hojas | excluir | usuario | 2026-10-15 | Conservar las filas de 'Year 2009-2010'. Excluir copias exactas de 'Year 2010-2011' en el rango 1-9 dic 2010. |
| duplicados_intra_hoja | conservar | usuario | 2026-10-15 | Marcar con alerta_duplicado_intra_hoja. Revisión en paso 2 si impacto es material. |
| volumen_extremo | conservar | usuario | 2026-10-15 | |quantity| > 10,000 o price > 10,000. Marcar con alerta_volumen_extremo. |
| stock_code_lower_10 | unificar | usuario | 2026-10-15 | Los 10 StockCodes cuya descripción difería entre lower/UPPER son el mismo producto con redacción distinta. Se unifica SOLO el código a MAYÚSCULAS; las descripciones de las filas NO se tocan. |

## Alertas conservadas (valores NO modificados, solo marcados)

| Alerta | Filas |
|---|---|
| alerta_desc_vacia: descripcion_nula_o_disfrazada | 4,402 |
| alerta_duplicado_intra_hoja: duplicado_exacto_en_misma_hoja | 11,812 |
| alerta_volumen_extremo: volumen_extremo | 34 |

## Pendientes para el paso 2 (reglas_retail.yaml)

- **D3**: Quantity negativa sin prefijo C en invoice (3,457 filas) → clasificar con R5 `ajuste_inventario` o según regla aplicable.
- **D4**: Price = 0 (6,202 filas, de ellas 2,745 con Quantity > 0) → clasificar con R6 `sin_valor` o como muestras según contexto.
- **Customer ID vacío** (243,007 filas) → R4 de reglas_retail.yaml (`cliente_sin_identificar: SIN_CLIENTE`).
- **Invoice C / A** y **StockCodes no-producto** → clasificar con R1, R2, R3 del YAML (no se toca en limpieza).
