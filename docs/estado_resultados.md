# Estado de resultados gerencial

Página: `reporte_estado_resultados.html`. Acceso desde `index.html`.

## Regeneración

Desde la raíz del repositorio:

```text
python scripts/actualizar_avanzia.py
```

El procedimiento de actualización incluye el generador nuevo. Para regenerar solamente
resultados: `python scripts/reporte_resultados.py`. Usa la conexión privada existente,
PostgreSQL de solo lectura y una única sentencia con snapshot consistente para las cuatro
fuentes (cabeceras, renglones, cuentas, relaciones). No modifica cuentas ni documentos.

`--cache` reutiliza `outputs/estado_resultados_origen.json` (ignorado por Git).
El backup completo tampoco se publica. Se publican únicamente el HTML generado, sus assets,
generador, pruebas y documentación. La conciliación histórica conserva sus CSV/pickle.

## Vista principal: ventas por artículo

La primera sección es una tabla plana, sin menús, para leer cantidades e importes de un
vistazo (misma forma que la consulta agrupada por categoría/artículo del usuario):

- Columnas: **Categoría / Artículo**, **Unidades facturadas**, **Importe sin IVA**.
- Encabezado de categoría con subtotal propio, encabezado de empresa con subtotal propio
  y fila de **TOTAL VENTAS FACTURADAS** al pie. Todo visible sin desplegar nada.
- Cada fila de artículo tiene «Ver renglones», que abre los comprobantes que la componen
  (registro, fecha, cliente, cantidad e importe) y se vuelve a plegar.
- Filtros globales (desde/hasta/empresa) y búsqueda de artículo aplican a la tabla;
  el selector **Agrupar por** alterna «Categoría y artículo» y «Mes y artículo».
- Unidades: solo bienes de ventas facturadas; servicios y artículos genéricos no cuentan
  unidades. Los 8 comprobantes con importe negativo y cantidad positiva no suman unidades:
  aparecen marcados «a revisar».
- El total de renglones de venta coincide con las ventas reconocidas en el estado de
  resultados (diferencia informada debajo de la tabla; hoy es 0,00).
- Remitos de salida nunca suman en esta tabla: quedan en «Remitos · separados de ventas».
- CSV de artículos filtrados: empresa, agrupación, artículo, ID, unidades, ajustes a
  revisar, ventas netas, costo registrado y otros ingresos.

## Decisiones contables verificables

- Empresa/unidad contable: ancestros 10986 Avanzia, 11369 Condiseño y 11477 Bistro.
  No se supone que el flujo llamado VENTA AVANZIA pertenece siempre a esa empresa:
  también contiene comprobantes imputados a Condiseño y Bistro.
- Ventas: flujos 10781/11547, estado de `statusflows` 1319. No sumar órdenes (1292/1400),
  producción (1291), auditoría (1172) ni remitos (1114). Los remitos de recepción tampoco
  entran a ventas ni despachos de salida.
- Neto: `registrocab.totalprecio` y `registrocuerpo.preciototal`.
  Total con impuestos: `totalimpuestos` y `preciototalimpu`. Se verificó en origen la
  igualdad de renglones con la fórmula neto × (1 + alícuota / 100), con tolerancia de
  redondeo. Hay diferencias puntuales de cabecera/renglones, que se separan para revisión.
- Los estados de reconocimiento están explícitos en `ESTADOS`. Los no reconocidos se
  separan: no se considera un registro devengado solamente porque tenga cuenta asignada.
- Una cabecera = una decisión. Relaciones como conjunto en ambos sentidos. Pago/cobro
  de caja ligado a comprobante se excluye de resultados aunque tenga cuenta propia.
  Un pago para varias facturas no agrupa esas facturas. No se deduplican por importe/fecha.
- Caja independiente: se admite si su cuenta es de resultados y su estado archivado
  está reconocido. Flujo y naturaleza de cuenta incompatibles requieren revisión.
- Activo, pasivo, patrimonio, transferencias, capital y cheques no se convierten en gasto.
- Sin cuenta propia y relacionado con cuenta: solo resumen, sin heredar la cuenta del
  pago ni listarlo como pendiente real. Sigue fuera del resultado reconocido.
- Materias primas (rama 11355): compra pendiente de consumo/variación de inventario,
  no costo vendido automático. Costos explícitamente asignados a cuentas de costo de
  ventas se muestran como **registrados**, sin afirmar que su devengamiento sea correcto.
- Gastos por artículo: artículo identificado en el renglón. No se imputan insumos a
  productos terminados ni se reparten gastos generales. Artículos financieros/genéricos
  figuran sin imputación a producto. Cantidad de bienes vendidos separada de servicios,
  agrupada por ID de artículo. El sistema no carga unidad de medida (`articulos.um`
  vacío en todas las filas de venta), por eso las cantidades se leen como unidades.
  Margen por producto no determinado.
- Renglones explícitos de IVA/percepciones/retenciones se separan de resultados,
  salvo cuenta IVA no computable. El resto de los impuestos sigue la imputación original.
- Importes expresados en moneda de registro. No hay conversión cambiaria verificable ni
  consolidación/eliminación interempresa. Mantener signos originales; posibles notas de
  crédito positivas se apartan para revisión, sin inventar una regla de signo.
  Los ajustes de importe negativo con cantidad positiva conservan el signo monetario,
  pero sus unidades se marcan para revisión (pueden ser bonificaciones, no devoluciones).
- Estado: `statusflows.statusid`, igual que la consulta proporcionada. Las diferencias
  respecto de `registrocab.statusid` se exponen en el control de integridad.

## Limitaciones visibles en la página

Es un resultado **provisional/parcial según cuentas**, no un balance legal cerrado.
Se necesitan validación de inventarios, costos consumidos, devengamientos, amortizaciones,
impuesto a las ganancias y clasificación de pendientes para afirmar utilidad neta.
Revisar rescates FIMA imputados a intereses. No confundir «sin importe reconocido» con
ausencia de gasto, ni costo faltante con cero. No se infiere empresa del cliente o artículo.

## Controles

```text
python scripts/test_resultados.py
node --check assets/estado_resultados.js
python scripts/verificar_resultados_browser.py
```

La última prueba requiere Playwright y Microsoft Edge. Verifica con DOM real la carga,
totales, límites inclusivos de fechas, rango inválido, filtro de empresa, despliegue
de comprobantes/renglones, descarga CSV filtrada, ausencia de errores JS y vista móvil.
El snapshot se conserva fuera del commit para poder reproducir la generación y auditarla.
