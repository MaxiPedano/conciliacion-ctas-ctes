# Conciliación Cuenta Corriente vs Cuenta Contable — Proveedores

Actuá como analista contable/financiero senior. Tengo dos archivos CSV en esta carpeta:

## 1. `cta_cte_-_Proveedores.csv` (cuenta corriente de proveedores)

Columnas reales:
- `id` → id del movimiento (no del proveedor)
- `clientid` → **id del proveedor**
- `clientname` → nombre del proveedor
- `fecha` → fecha del movimiento
- `referenciatexto` → descripción/concepto del movimiento (factura, sueldo, pago, etc.)
- `fechacompromiso` → fecha de vencimiento/compromiso de pago
- `flows` → categoría del flujo (ej. "Comprobantes de sueldo EMPLEADOS")
- `flowsid`, `categoriaid` → ids internos de clasificación
- `tipo_perfil` → siempre "Proveedor" en este archivo
- `haber` → importe haber del movimiento
- `debe` → importe debe del movimiento
- `saldo_acumulado` → saldo corrido después de ese movimiento
- `total_haber_general`, `total_debe_general` → totales generales (repetidos en todas las filas, ignorar para el análisis por proveedor)
- `saldo_cliente` → saldo final de ese proveedor (repetido en todas sus filas)

## 2. `registro_cta_ctble_-_Proveedores_-_registro_cta_ctble_-_Proveedores.csv` (mayor contable)

Columnas reales:
- `clientname` / `clientname-2` → nombre del proveedor (duplicado en dos columnas, usar `clientname`)
- `clientid` → **id del proveedor** (mismo id que `clientid` en el archivo de cta cte — clave de cruce directa)
- `cuentacontableid` → id de la cuenta contable
- `fecha` → fecha del asiento
- `totalprecio` → importe del movimiento (sin discriminar debe/haber en columna separada — inferir signo según convenga o preguntar si hace falta)
- `totalimpuestos` → impuestos asociados (suele ser igual a `totalprecio` en muchos registros, verificar)
- `referenciatexto` → descripción del asiento
- `cuentacontable` → código y nombre de la cuenta contable que impacta ese movimiento (ej. "4.2.1/08/01 Materias Primas", "4.2.1/01/01 - Sueldos y Jornales Fábrica"). **No existe una cuenta única "Proveedores"** — cada transacción impacta la cuenta de gasto/activo que corresponda, no una cuenta puente de pasivo.
- `categoriaid` → id de categoría/clasificación adicional del asiento (NO es el id del proveedor ni identifica el lado debe/haber — ver advertencia abajo)

## ⚠️ Clave de cruce

Ahora **sí hay `clientid` compartido** entre ambos archivos — usarlo como clave directa de cruce, sin fuzzy matching por nombre. (El archivo contable trae 744 `clientid` únicos en total porque incluye otras entidades además de proveedores; filtrar solo los que están presentes en `cta_cte_-_Proveedores.csv`.)

## ⚠️ ADVERTENCIA CRÍTICA — filas duplicadas por transacción

El archivo contable tiene **filas repetidas para la misma transacción económica**: mismo `clientid` + `fecha` + `referenciatexto` + `totalprecio`, pero con distinto `categoriaid` (2 o 3 filas por transacción en la gran mayoría de los casos — verificado: ~4500 de ~4565 grupos tienen más de 1 fila). El campo `cuentacontable` puede repetirse igual entre esas filas duplicadas, así que `categoriaid` **no representa el lado debe/haber de la partida doble** — su función exacta no es clara a partir de los datos.

Por lo tanto, antes de sumar `totalprecio` por proveedor:
1. Deduplicar por (`clientid`, `fecha`, `referenciatexto`, `totalprecio`) — quedarse con una sola fila por combinación (usar `cuentacontable` de cualquiera de las filas del grupo, o listar todas si difieren, para no perder información de a qué cuenta(s) impactó).
2. Verificar el patrón de duplicación primero: contar cuántas filas tiene cada grupo y mostrarme la distribución (ej. "X grupos con 2 filas, Y grupos con 3 filas, Z grupos con 1 fila"), y si el `totalprecio` es siempre idéntico entre las filas duplicadas de un mismo grupo o varía — si varía, avisame antes de deduplicar a ciegas, porque podría ser que sí son movimientos distintos con fecha/referencia coincidentes por casualidad y no duplicados reales.
3. Solo después de confirmar el patrón, calcular el saldo contable por proveedor sobre las filas deduplicadas.

## TAREA

1. Cargá ambos CSV con pandas (separador coma, encoding utf-8; probar latin-1 si falla). Mostrame un preview de las primeras filas y los dtypes de cada uno antes de seguir, para confirmar que la lectura fue correcta.

2. Ejecutá primero el análisis de duplicados del archivo contable descripto en la advertencia de arriba (paso 2 de esa sección) y mostrame el resultado. No sigas al paso 3 sin mi confirmación si encontrás que el `totalprecio` varía dentro de un mismo grupo duplicado.

3. Filtrá el archivo contable a solo los `clientid` presentes en `cta_cte_-_Proveedores.csv` (dejá aparte, en una lista, los `clientid` del contable que no aparecen en cta cte — puede ser información útil de otras categorías, no de proveedores).

4. Para cada proveedor (agrupando por `clientid`, cruce directo entre ambos archivos):
   - **Saldo según cta cte**: usar el último `saldo_acumulado` por fecha, o `saldo_cliente` (deberían coincidir — si no, marcarlo también como inconsistencia interna del archivo de cta cte).
   - **Saldo según cuenta contable**: sumar `totalprecio` de los movimientos ya deduplicados de ese proveedor (definir signo: para proveedores como pasivo, definí el criterio explícitamente en el código y dejalo comentado; si no es evidente por los datos, preguntame antes de asumir).
   - Diferencia en $ y en %.

5. Comparación de MOVIMIENTOS uno a uno (no solo saldo final), por `clientid`:
   - Cruzar por fecha (tolerancia ± 5 días) + importe (`debe`/`haber` de cta cte vs `totalprecio` deduplicado de contable) + similitud de texto entre `referenciatexto` de ambos archivos (usar `rapidfuzz`, umbral ≥ 70 como señal de apoyo, no como único criterio).
   - Marcar como "movimiento sin contrapartida" todo registro de una planilla que no encuentre par razonable en la otra.

6. Clasificá TODOS los proveedores en 3 categorías:

   **A) "NO CUADRA - Diferencia de saldo"**: saldo cta cte ≠ saldo contable. Ordenado de mayor a menor diferencia absoluta. Columnas: `clientid`, `clientname`, saldo cta cte, saldo contable, diferencia $, diferencia %.

   **B) "MOVIMIENTOS NO COINCIDEN"**: proveedores con movimientos huérfanos en una u otra planilla (aunque el saldo final cuadre). Columnas: `clientid`, `clientname`, cantidad de movimientos sin matchear, detalle (fecha, referenciatexto, importe, origen: cta_cte o contable).

   **C) "CONCILIADO - Al día"**: saldo cta cte = saldo contable (tolerancia $1 por redondeo) Y todos los movimientos matchean. Columnas: `clientid`, `clientname`, saldo actual.

7. Resumen ejecutivo al inicio del informe con:
   - Cantidad total de proveedores analizados (y cuántos `clientid` del contable quedaron fuera por no estar en cta cte, listados aparte)
   - Cantidad y % en cada una de las 3 categorías
   - Monto total de diferencias no conciliadas (suma de valor absoluto de categoría A)
   - Top 10 proveedores con mayor diferencia en $

8. Exportá todo a `informe_conciliacion_proveedores.xlsx` con hojas: `Resumen`, `Duplicados Detectados` (el detalle del paso 2), `No Cuadra - Saldo`, `Movimientos No Coinciden`, `Conciliado`, `Clientid Fuera de Alcance`.

9. Priorizá código pandas legible, funciones separadas por paso, y comentá el criterio contable de signos que uses en cada comparación. Si algo del criterio de signo (debe/haber vs pasivo) no es evidente en los datos, preguntame antes de asumir y seguir.
