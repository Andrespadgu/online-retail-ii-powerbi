# Diccionario de datos

Generado: 2026-10-15T12:46:42 · Reglas v1.1

## fact_ventas

Hechos. Grano: una línea de factura (incluye ventas, devoluciones, cargos y ajustes; las medidas filtran por tipo_linea).  
Filas: 1,044,848

| Columna | Tipo | Descripción | Nulos | Ejemplo |
|---|---|---|---:|---|
| `linea_id` | Número entero | Identificador único de la línea (orden de la fuente). _(ocultar)_ | 0 | 2 |
| `num_factura` | Texto | Número de factura de la fuente. Prefijo C = nota crédito/devolución; A = ajuste contable. | 0 | 489434 |
| `fecha_key` | Número entero | Fecha de la factura como AAAAMMDD. Relación con dim_fecha. _(ocultar)_ | 0 | 20091201 |
| `hora` | Número entero | Hora de la factura (0-23). | 0 | 7 |
| `producto_key` | Número entero | Clave sustituta del producto o concepto. Relación con dim_producto. _(ocultar)_ | 0 | 3651 |
| `cliente_key` | Número entero | Clave sustituta del cliente; -1 = venta sin cliente identificado. Relación con dim_cliente. _(ocultar)_ | 0 | 740 |
| `pais_key` | Número entero | País de la factura (no del cliente: un cliente puede comprar desde varios países). Relación con dim_pais. _(ocultar)_ | 0 | 41 |
| `cantidad` | Número entero | Unidades. Negativa en devoluciones y ajustes de inventario. | 0 | 12 |
| `precio_unitario` | Número decimal fijo | Precio unitario en la moneda de la fuente. | 0 | 6.75 |
| `importe` | Número decimal fijo | cantidad x precio_unitario, con signo. | 0 | 81.0 |
| `tipo_linea` | Texto | Clasificación de reglas de negocio: venta, devolucion, cargo_no_producto, ajuste_inventario, ajuste_contable, sin_valor, cancelado, sin_clasificar. | 0 | venta |
| `es_producto` | Verdadero/falso | Falso para envío, comisiones, descuentos, ajustes y similares. C3 y GIFT figuran como producto pero solo tienen líneas de ajuste_inventario con importe £0; revisados el 2026-10-15, sin impacto en métricas. | 0 | True |
| `cliente_identificado` | Verdadero/falso | Falso cuando la fuente no trae cliente (SIN_CLIENTE). | 0 | True |
| `version_reglas` | Texto | Versión del archivo de reglas que clasificó la línea. | 0 | 1.1 |
| `hoja_origen` | Texto | Hoja del Excel de origen (Year 2009-2010 o Year 2010-2011). Permite filtrar por periodo del archivo fuente. | 0 | Year 2009-2010 |
| `fila_excel` | Número entero | Numero de fila en la hoja de Excel de origen. Permite rastrear cualquier linea hasta el Excel original. | 0 | 3 |
| `alerta_desc_vacia` | Texto | Descripcion nula o disfrazada detectada en la limpieza (p. ej. descripcion_nula_o_disfrazada: ?). Vacio = sin alerta. | 1040446 | descripcion_nula_o_disfrazada:  |
| `alerta_duplicado_intra_hoja` | Texto | Fila identificada como duplicado exacto dentro de su hoja de origen. Valor: duplicado_exacto_en_misma_hoja. Vacio = sin alerta. | 1033036 | duplicado_exacto_en_misma_hoja |
| `alerta_volumen_extremo` | Texto | Linea con |cantidad|>10.000 o precio>10.000. Incluye los valores exactos (p. ej. volumen_extremo: qty=19152 price=0.1). Vacio = sin alerta. | 1044814 | volumen_extremo: qty=12960 price=0.1 |

## dim_producto

Productos y conceptos no producto. Una fila por código.  
Filas: 5,132

| Columna | Tipo | Descripción | Nulos | Ejemplo |
|---|---|---|---:|---|
| `producto_key` | Número entero | Clave sustituta (entero). -1 = desconocido. | 0 | 1 |
| `codigo_producto` | Texto | Código de la fuente (StockCode). | 0 | 10002 |
| `descripcion` | Texto | Descripción más frecuente del código (empates: la primera alfabéticamente). | 0 | INFLATABLE POLITICAL GLOBE |
| `n_descripciones` | Número entero | Cuántas descripciones distintas tuvo el código en la fuente (>1 = revisar). | 0 | 1 |
| `es_producto` | Verdadero/falso | Falso para cargos y conceptos que no son mercancía. | 0 | True |
| `categoria_no_producto` | Texto | envio, descuento, comision, ajuste_manual, muestra, tarjeta_regalo, etc. Vacío si es producto. | 5074 | ajuste_manual |
| `precio_referencia` | Número decimal fijo | Mediana del precio unitario en líneas de venta. | 424 | 5.17 |

## dim_cliente

Clientes. Una fila por cliente identificado más la fila -1 para ventas sin cliente.  
Filas: 5,943

| Columna | Tipo | Descripción | Nulos | Ejemplo |
|---|---|---|---:|---|
| `cliente_key` | Número entero | Clave sustituta (entero). -1 = sin cliente identificado. | 0 | 1 |
| `codigo_cliente` | Texto | Código de cliente de la fuente (Customer ID). | 0 | 12346 |
| `cliente_identificado` | Verdadero/falso | Falso solo para la fila -1. | 0 | True |
| `pais_principal` | Texto | País más frecuente en sus facturas. | 0 | United Kingdom |
| `n_paises` | Número entero | Número de países distintos desde los que compró. | 0 | 1 |
| `primera_compra` | Fecha | Fecha de su primera venta. | 91 | 2010-10-31 |
| `ultima_compra` | Fecha | Fecha de su última venta. | 91 | 2011-12-07 |

## dim_pais

Países de facturación.  
Filas: 44

| Columna | Tipo | Descripción | Nulos | Ejemplo |
|---|---|---|---:|---|
| `pais_key` | Número entero | Clave sustituta (entero). -1 = desconocido. | 0 | 1 |
| `pais` | Texto | Nombre del país tal como viene en la fuente. | 0 | Australia |

## dim_fecha

Calendario continuo de años completos. Marcar como tabla de fechas en Power BI usando la columna fecha.  
Filas: 1,095

| Columna | Tipo | Descripción | Nulos | Ejemplo |
|---|---|---|---:|---|
| `fecha_key` | Número entero | AAAAMMDD (entero). Clave de la relación. | 0 | 20090102 |
| `fecha` | Fecha | Fecha (tipo fecha). Columna para 'Marcar como tabla de fechas'. | 0 | 2009-01-02 |
| `anio` | Número entero | Año calendario. | 0 | 2009 |
| `trimestre` | Texto | T1-T4. _(ordenar por `trimestre_num`)_ | 0 | T1 |
| `trimestre_num` | Número entero | 1-4. | 0 | 1 |
| `mes_num` | Número entero | 1-12. | 0 | 1 |
| `mes_nombre` | Texto | Nombre del mes en español. Ordenar por mes_num. _(ordenar por `mes_num`)_ | 0 | Enero |
| `mes_abrev` | Texto | Ene, Feb... Ordenar por mes_num. _(ordenar por `mes_num`)_ | 0 | Ene |
| `anio_mes` | Texto | AAAA-MM. Ordenar por anio_mes_num. _(ordenar por `anio_mes_num`)_ | 0 | 2009-01 |
| `anio_mes_num` | Número entero | AAAAMM (entero) para ordenar. | 0 | 200901 |
| `semana_iso` | Número entero | Semana ISO 8601 (1-53). | 0 | 1 |
| `anio_iso` | Número entero | Año ISO de la semana. | 0 | 2009 |
| `dia_mes` | Número entero | 1-31. | 0 | 2 |
| `dia_anio` | Número entero | 1-366. | 0 | 2 |
| `dia_semana_num` | Número entero | 1 = lunes ... 7 = domingo. | 0 | 5 |
| `dia_semana_nombre` | Texto | Lunes... Ordenar por dia_semana_num. _(ordenar por `dia_semana_num`)_ | 0 | Viernes |
| `es_fin_de_semana` | Verdadero/falso | Sábado o domingo. | 0 | False |
| `es_fin_de_mes` | Verdadero/falso | Último día del mes. | 0 | False |
