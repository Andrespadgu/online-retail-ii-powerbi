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

// dim_pais
let
    Origen = Parquet.Document(File.Contents(RutaDatos & "dim_pais.parquet")),
    Tipos = Table.TransformColumnTypes(Origen, {
        {"pais_key", Int64.Type},
        {"pais", type text}
    })
in
    Tipos

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
