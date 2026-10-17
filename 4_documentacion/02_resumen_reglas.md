# Resumen de reglas de negocio — v1.1

- Entrada: `trabajo\01_limpieza\online_retail_II_limpio.csv`  
- Generado: 2026-10-15T12:38:28  
- Filas: 1,044,848

## ⚠ Pendientes

- 2 códigos **no reconocidos** (no parecen producto y no están en las listas). Decidir con el usuario y agregarlos al YAML (subiendo la versión).

## Métricas con estas reglas

| Métrica | Valor | Definición |
|---|---:|---|
| ventas_brutas | 19,699,799.72 | Suma de cantidad x precio de las líneas tipo 'venta'. |
| devoluciones | 719,656.34 | Suma del valor absoluto de las líneas tipo 'devolucion' (solo productos). Se reporta en positivo. |
| ventas_netas | 18,980,143.38 | ventas_brutas - devoluciones. No incluye cargos, descuentos ni ajustes. |
| cargos_no_producto | 77,232.82 | Suma de importe de las líneas tipo 'cargo_no_producto' (envío, comisiones, descuentos, tarjetas regalo...), con su signo. Se reporta aparte. No incluye ajustes contables. |
| facturas | 39,516 | Número de facturas distintas con al menos una línea tipo 'venta'. |
| ticket_promedio | 498.5272 | ventas_brutas / facturas. Valor medio de un pedido; las devoluciones no lo reducen porque suelen pertenecer a otros pedidos. |
| clientes_unicos | 5,852 | Clientes distintos con al menos una línea tipo 'venta', excluyendo SIN_CLIENTE. |
| pct_ventas_sin_cliente | 13.07 |  |

## Líneas por tipo

| tipo_linea | líneas | importe |
|---|---:|---:|
| venta | 1,014,947 | 19,699,799.72 |
| devolucion | 17,973 | -719,656.34 |
| cargo_no_producto | 5,981 | 77,232.82 |
| ajuste_inventario | 3,365 | 0.00 |
| ajuste_contable | 6 | -147,614.08 |
| sin_valor | 2,576 | 0.00 |
| cancelado | 0 | 0.00 |
| sin_clasificar | 0 | 0.00 |

**Cuadre:** importe total 18,909,762.12 = suma por tipo 18,909,762.12 → OK

## Conceptos que no son producto

| categoría | líneas | importe |
|---|---:|---:|
| ajuste_contable | 6 | -147,614.08 |
| ajuste_manual | 1,473 | -75,369.28 |
| comision | 136 | -257,002.75 |
| descuento | 173 | -12,879.63 |
| donacion | 16 | -7,933.43 |
| envio | 3,788 | 433,410.51 |
| muestra | 102 | -6,000.85 |
| otro | 193 | 1,321.64 |
| tarjeta_regalo | 100 | 1,686.61 |

## Códigos no reconocidos (top 50 por importe)

| código | líneas | importe | ejemplo |
|---|---:|---:|---|
| `C3` | 1 | 0.00 | nan |
| `GIFT` | 1 | 0.00 | nan |

## Reglas aplicadas

| regla | líneas |
|---|---:|
| R7_venta | 1,014,947 |
| R4_devolucion | 17,973 |
| R3_no_producto | 5,981 |
| R5_ajuste_inventario | 3,365 |
| R6_sin_valor | 2,576 |
| R2_ajuste_contable | 6 |
