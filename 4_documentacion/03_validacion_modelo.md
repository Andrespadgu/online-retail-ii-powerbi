# Validación del modelo

| Chequeo | Resultado | Detalle |
|---|---|---|
| Filas fact = filas de entrada | OK | 1044848 vs 1044848 |
| Importe fact = importe de entrada | OK | 18,909,762.12 vs 18,909,762.12 |
| Integridad fecha_key → dim_fecha | OK | 0 claves sin dimensión |
| dim_fecha.fecha_key único | OK |  |
| Integridad producto_key → dim_producto | OK | 0 claves sin dimensión |
| dim_producto.producto_key único | OK |  |
| Integridad cliente_key → dim_cliente | OK | 0 claves sin dimensión |
| dim_cliente.cliente_key único | OK |  |
| Integridad pais_key → dim_pais | OK | 0 claves sin dimensión |
| dim_pais.pais_key único | OK |  |
| dim_fecha continua y sin duplicados | OK | 2009-01-01 a 2011-12-31 |
| Sin líneas sin_clasificar | OK | 0 líneas |

## Tablas

| tabla | filas | columnas |
|---|---:|---:|
| fact_ventas | 1,044,848 | 19 |
| dim_producto | 5,132 | 7 |
| dim_cliente | 5,943 | 7 |
| dim_pais | 44 | 2 |
| dim_fecha | 1,095 | 18 |

Nota: 1110 códigos de producto tienen más de una descripción; se usó la más frecuente.
Nota: 13 clientes compraron desde más de un país; por eso el país va en la fact, no en dim_cliente.

## Columnas de auditoría añadidas a fact_ventas

Las siguientes columnas fueron agregadas al parquet de fact_ventas tras correr el script del modelo (no forman parte
del modelo relacional Power BI pero permiten rastrear cualquier línea hasta el Excel original):

| columna | descripción |
|---|---|
| hoja_origen | Hoja del Excel fuente (Year 2009-2010 / Year 2010-2011) |
| fila_excel | Fila en el Excel fuente (para trazabilidad) |
| alerta_desc_vacia | Marca si la descripción era nula o disfrazada (paso 1) |
| alerta_duplicado_intra_hoja | Marca si la fila es duplicado exacto dentro de su hoja (paso 1) |
| alerta_volumen_extremo | Marca cantidad o precio fuera de umbral (paso 1) |
