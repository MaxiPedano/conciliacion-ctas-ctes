# Estado de resultados gerencial

Página: `reporte_estado_resultados.html`. Acceso desde `index.html`.

Vista **reducida a ventas de producto terminado**: solo los artículos que cuelgan de
`10626 P.T. FABRICADOS` y `11428 P.T. IMPORTADOS`, en estados de venta, por empresa.

## Regeneración

Desde la raíz del repositorio:

```text
python scripts/actualizar_avanzia.py
```

El procedimiento de actualización incluye el generador nuevo. Para regenerar solamente
resultados: `python scripts/reporte_resultados.py`. Usa la conexión privada existente,
PostgreSQL de solo lectura y una única sentencia con snapshot consistente para las cuatro
fuentes (cabeceras, renglones, cuentas, relaciones). No modifica cuentas ni documentos.

`--cache` reutiliza `outputs/estado_resultados_origen.json` (ignorado por Git). La
instantánea debe incluir `categoria_id` en los renglones: si es anterior a este alcance,
el generador se detiene y hay que correrlo sin `--cache` para refrescarla.
El backup completo tampoco se publica. Se publican únicamente el HTML generado, sus assets,
generador, pruebas y documentación. La conciliación histórica conserva sus CSV/pickle.

## Alcance del informe

- **Flujos**: 10781 (VENTA: AVANZIA) y 11547 (VENTAS MERCADOLIBRE).
- **Estado**: `statusflows.statusid` en `{1319, 1291}` — `1319` FACTURA DE VENTA y
  `1291` Notificación a Producción (OV ya enviada a producción). Órdenes (1292/1400) y
  auditoría (1172) quedan en «fuera de alcance», con motivo visible en Control de integridad.
- **Producto terminado**: el artículo debe colgar de `10626 P.T. FABRICADOS` o
  `11428 P.T. IMPORTADOS`, en cualquier subcategoría. Renglones de la misma factura que
  no cuelgan de esas raíces (flete, bordado, logo, almohadones, piezas para mesa) no suman
  ni unidades ni importes; su importe se informa en la cabecera como «Fuera de PT».
- **Renglones de producto en otros flujos** (remitos de recepción/salida, comprobantes
  internos y de proveedores) tampoco entran: se cuentan en el control, desglosados por flujo.

## Empresa por depósito

Las ventas no traen depósito de empresa (`registrocab.depositoarticuloid`,
`registrocuerpo.deposito` y `depositodestinoid` están vacíos) y el depósito del artículo es
de fábrica/depacho, no de compañía. Por eso la empresa se asigna con el depósito del
producto terminado:

- `P.T. FABRICADOS` → **Avanzia**.
- `P.T. IMPORTADOS` → **Condiseño**.
- Si la cuenta propia de resultados es de **Bistro**, se respeta la cuenta por encima de la
  raíz.

Una factura con renglones de ambas raíces se informa como «Varias empresas» en la cabecera
y conserva su empresa en cada renglón. Sin cuenta propia, la empresa sale igual de la raíz.
No se infiere empresa del cliente ni del nombre del flujo.

## Estructura de la página

Sin bloque de título: arriba queda una sola barra con el enlace al índice, el nombre del
informe y la fecha de consulta, seguida de los filtros. El orden es el que trabaja el ojo:

1. **KPIs**: ventas netas de producto terminado, unidades vendidas (con las que están «a
   revisar»), artículos vendidos, comprobantes, empresas con ventas y comprobantes fuera de
   alcance.
2. **Evolución mensual**: promedios del filtro activo (promedio mensual, ticket promedio,
   unidades por mes y meses con ventas) y tres gráficos: dos de barras (unidades e importe
   por mes) y uno de líneas con los primeros N artículos por importe o por unidades. No hay
   listado debajo: el detalle mes por mes sale en el CSV de la línea de tiempo.
3. **Ventas por empresa, categoría y artículo**: tabla plana con subtotales por categoría y
   por empresa y fila de total. El selector **Agrupar por** alterna «Categoría y artículo» y
   «Mes y artículo»; cada fila abre sus comprobantes con «Ver renglones». Cada fila muestra
   además **ticket promedio** (importe / comprobantes que lo vendieron) y **promedio mensual**
   (importe / meses en que vendió). El botón **Contraer todo** pliega la tabla hasta dejar
   solo los encabezados de empresa y de categoría; el clic sobre un encabezado pliega solo
   ese bloque.
4. **Resumen por empresa**: comprobantes, artículos, unidades, importe y participación.
5. **Control de integridad**: conteos de lectura, comprobantes de venta fuera de alcance con
   su motivo, diferencia cabecera/renglones, unidades a revisar y comprobantes sin cuenta.

Los tres filtros globales (desde, hasta, empresa) afectan todos los cuadros, gráficos y CSV;
la búsqueda de producto filtra las tablas sin mover los KPI.

## Decisiones contables verificables

- Base neta: `registrocab.totalprecio` y `registrocuerpo.preciototal`. El total del informe
  es la suma de los renglones de producto terminado; no se recupera el resto del comprobante.
- Estado: `statusflows.statusid`, igual que la consulta de origen.
- Unidades: suma de `registrocuerpo.cantidad` de los renglones de producto. Un importe
  negativo con cantidad positiva puede ser bonificación: resta en dinero y sus unidades
  quedan «a revisar», nunca sumadas como vendidas ni descontadas como devolución.
- Precio unitario promedio = importe sin IVA / unidades; sin unidades no se promedia.
- Ticket promedio = importe sin IVA / comprobantes del mismo filtro; promedio mensual =
  importe sin IVA / meses con ventas del mismo filtro. En la tabla de ventas se calculan por
  artículo, por grupo, por empresa y en el total, con los comprobantes y meses que le tocan
  a cada fila.
- Sin cuenta propia no se bloquea la venta: manda la raíz del producto.
- Relaciones de pago/cobro no intervienen: esta vista no suma caja y no duplica comprobantes.
- No se determina resultado neto ni margen: faltan costo vendido, inventarios y
  devengamiento. Costos y gastos por empresa no forman parte de esta vista reducida.

## Limitaciones visibles en la página

Es un resultado **provisional**: no incluye costos, gastos, remitos ni compras. Tampoco
incluye los artículos que no cuelgan de las dos raíces de producto terminado. Un cero o un
«fuera de alcance» significa «no pertenece a esta vista», no ausencia comprobada de ventas.

## Controles

```text
python scripts/test_resultados.py
node --check assets/estado_resultados.js
python scripts/verificar_resultados_browser.py
```

La última prueba requiere Playwright y Microsoft Edge. Verifica con DOM real la carga, el
alcance (solo 10781/11547 en 1319 o 1291 y solo raíces PT), la empresa por depósito, los totales de
la tabla de ventas contra la línea de tiempo, los gráficos SVG, límites inclusivos de fechas,
rango inválido, filtro de empresa, búsqueda de producto, descarga de los tres CSV, ausencia
de errores JS y vista móvil.

El snapshot se conserva fuera del commit para poder reproducir la generación y auditarla.
