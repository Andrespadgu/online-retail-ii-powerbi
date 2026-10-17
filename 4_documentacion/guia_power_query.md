# Guía de carga en Power BI (Power Query)

Entrega generada el 2026-10-15T12:46:42 · reglas de negocio v1.1 · formato **parquet**
Tablas: `fact_ventas`, `dim_cliente`, `dim_fecha`, `dim_pais`, `dim_producto`

## 1. Preparar (solo la primera vez)

1. Copia la carpeta `datos/` a una ruta fija, p. ej. `C:\BI\ventas\datos\`. **No cambies los nombres de los archivos**: al actualizar se reemplazan con los mismos nombres.
2. En Power BI Desktop: *Archivo > Opciones > Archivo actual > Carga de datos* → desmarca **Fecha y hora automáticas**.

## 2. Crear el parámetro de ruta

*Inicio > Transformar datos > Administrar parámetros > Nuevo*:

- Nombre: `RutaDatos` · Tipo: Texto · Valor: `C:\Users\ANDRES\Desktop\online retail 2\entrega_powerbi\datos\` (**con la barra final**)

Si la carpeta se mueve, solo cambias este valor.

## 3. Crear una consulta por tabla

En el Editor de Power Query: *Nueva fuente > Consulta en blanco > Editor avanzado*, pega el bloque de la tabla y renombra la consulta con el nombre de la tabla. (Todo el código está también en `consultas.pq`.)

```powerquery
// fact_ventas
let
    Origen = Parquet.Document(File.Contents(RutaDatos & "fact_ventas.parquet")),
    Tipos = Table.TransformColumnTypes(Origen, {
        {"linea_id", Int64.Type},
        {"num_factura", type text},
        {"fecha_key", Int64.Type},
        {"hora", Int64.Type},
        {"producto_key", Int64.Type},
        {"cliente_key", Int64.Type},
        {"pais_key", Int64.Type},
        {"cantidad", Int64.Type},
        {"precio_unitario", Currency.Type},
        {"importe", Currency.Type},
        {"tipo_linea", type text},
        {"es_producto", type logical},
        {"cliente_identificado", type logical},
        {"version_reglas", type text},
        {"hoja_origen", type text},
        {"fila_excel", Int64.Type},
        {"alerta_desc_vacia", type text},
        {"alerta_duplicado_intra_hoja", type text},
        {"alerta_volumen_extremo", type text}
    })
in
    Tipos
```
```powerquery
// dim_cliente
let
    Origen = Parquet.Document(File.Contents(RutaDatos & "dim_cliente.parquet")),
    Tipos = Table.TransformColumnTypes(Origen, {
        {"cliente_key", Int64.Type},
        {"codigo_cliente", type text},
        {"cliente_identificado", type logical},
        {"pais_principal", type text},
        {"n_paises", Int64.Type},
        {"primera_compra", type date},
        {"ultima_compra", type date}
    })
in
    Tipos
```
```powerquery
// dim_fecha
let
    Origen = Parquet.Document(File.Contents(RutaDatos & "dim_fecha.parquet")),
    Tipos = Table.TransformColumnTypes(Origen, {
        {"fecha_key", Int64.Type},
        {"fecha", type date},
        {"anio", Int64.Type},
        {"trimestre", type text},
        {"trimestre_num", Int64.Type},
        {"mes_num", Int64.Type},
        {"mes_nombre", type text},
        {"mes_abrev", type text},
        {"anio_mes", type text},
        {"anio_mes_num", Int64.Type},
        {"semana_iso", Int64.Type},
        {"anio_iso", Int64.Type},
        {"dia_mes", Int64.Type},
        {"dia_anio", Int64.Type},
        {"dia_semana_num", Int64.Type},
        {"dia_semana_nombre", type text},
        {"es_fin_de_semana", type logical},
        {"es_fin_de_mes", type logical}
    })
in
    Tipos
```
```powerquery
// dim_pais
let
    Origen = Parquet.Document(File.Contents(RutaDatos & "dim_pais.parquet")),
    Tipos = Table.TransformColumnTypes(Origen, {
        {"pais_key", Int64.Type},
        {"pais", type text}
    })
in
    Tipos
```
```powerquery
// dim_producto
let
    Origen = Parquet.Document(File.Contents(RutaDatos & "dim_producto.parquet")),
    Tipos = Table.TransformColumnTypes(Origen, {
        {"producto_key", Int64.Type},
        {"codigo_producto", type text},
        {"descripcion", type text},
        {"n_descripciones", Int64.Type},
        {"es_producto", type logical},
        {"categoria_no_producto", type text},
        {"precio_referencia", Currency.Type}
    })
in
    Tipos
```

Luego *Cerrar y aplicar*.

## 4. Relaciones (Vista de modelo)

Borra cualquier relación que Power BI haya detectado sola y crea estas:

| Desde | Hacia | Cardinalidad | Filtro cruzado |
|---|---|---|---|
| `fact_ventas[fecha_key]` | `dim_fecha[fecha_key]` | Varios a uno (*:1) | Simple |
| `fact_ventas[producto_key]` | `dim_producto[producto_key]` | Varios a uno (*:1) | Simple |
| `fact_ventas[cliente_key]` | `dim_cliente[cliente_key]` | Varios a uno (*:1) | Simple |
| `fact_ventas[pais_key]` | `dim_pais[pais_key]` | Varios a uno (*:1) | Simple |

## 5. Ajustes del modelo

- `dim_fecha` → *Herramientas de tabla > Marcar como tabla de fechas* → columna `fecha`.
- Ordenar por columna:
  - `dim_fecha[trimestre]` → ordenar por `trimestre_num`
  - `dim_fecha[mes_nombre]` → ordenar por `mes_num`
  - `dim_fecha[mes_abrev]` → ordenar por `mes_num`
  - `dim_fecha[anio_mes]` → ordenar por `anio_mes_num`
  - `dim_fecha[dia_semana_nombre]` → ordenar por `dia_semana_num`
- Ocultar en la vista de informe:
  - `fact_ventas[linea_id]`
  - `fact_ventas[fecha_key]`
  - `fact_ventas[producto_key]`
  - `fact_ventas[cliente_key]`
  - `fact_ventas[pais_key]`

## 6. Medidas

*Vista de consultas DAX* → pega `medidas.dax` → clic en **Actualizar modelo con cambios** → ejecuta la consulta. Los valores deben coincidir con la fila `TOTAL` de `valores_esperados.csv`.

## 7. Comprobar la carga

En la *Vista de tabla*, el número de filas de cada tabla (abajo a la izquierda) debe ser:

| Tabla | Filas |
|---|---:|
| fact_ventas | 1,044,848 |
| dim_cliente | 5,943 |
| dim_fecha | 1,095 |
| dim_pais | 44 |
| dim_producto | 5,132 |

Adicionalmente, la medida **Ventas Netas** (DAX) debe devolver exactamente **£ 18,980,143.38**.

Si no coincide o una medida no da lo esperado: revisa que la ruta apunte a la entrega correcta y que ningún paso de Power Query haya filtrado o cambiado tipos.

## 8. Actualizar con datos nuevos

1. Vuelve a correr el flujo (limpieza → reglas → modelo → entrega) sobre el archivo nuevo.
2. Reemplaza los archivos de `datos/` (mismos nombres). No hace falta tocar Power Query.
3. Power BI Desktop: *Inicio > Actualizar*.
4. Repite la comprobación del paso 7 con el `manifiesto.json` nuevo y la fila TOTAL de `valores_esperados.csv`.

**En el servicio de Power BI (actualización programada):** una ruta local `C:\...` exige una *puerta de enlace* (gateway). Sin gateway, guarda `datos/` en SharePoint u OneDrive para la Empresa y cambia el origen de cada consulta a `SharePoint.Files("https://<tu-sitio>.sharepoint.com/sites/<sitio>", [ApiVersion = 15])`, filtrando por el nombre del archivo.

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| Tildes rotas (`MarÃ­a`) | CSV leído con otra codificación | `Encoding = 65001` en `Csv.Document` |
| Importes 100 veces más grandes o errores de tipo | Configuración regional con coma decimal | Mantén `"en-US"` en `Table.TransformColumnTypes` |
| "No se puede encontrar el archivo" | `RutaDatos` sin barra final o carpeta movida | Corrige el parámetro |
| Totales duplicados o en blanco | Relación bidireccional o de varios a varios | Rehacer como en el paso 4 |
| YTD/año anterior vacíos | `dim_fecha` no marcada | Paso 5 |
