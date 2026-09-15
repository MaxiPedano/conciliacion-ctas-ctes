# Conciliacion de Cuentas Corrientes - Clientes y Proveedores

## Estructura del Proyecto

```text
.
|-- index.html                         Centro maestro de navegacion
|-- reporte_cuenta_corriente.html      Cuenta corriente y saldos por cliente
|-- reporte_cuentas_contables.html     Cuentas contables de egresos
|-- reporte_investigacion_egresos.html Investigacion de egresos y perfiles
|-- reporte_conciliacion.html          Reporte HTML interactivo (salida principal)
|-- scripts/
|   |-- reporte_cuenta_corriente.py    Generador del informe de cuenta corriente
|   |-- reporte_cuentas_contables.py   Generador de cuentas contables
|   |-- reporte_investigacion.py      Generador de investigacion de egresos
|   |-- reporte_html.py                Generador del reporte HTML
|   |-- conciliacion_paso1.py          Carga CSV y crea caches pickle
|   |-- conciliacion_paso2.py          Analiza duplicados del mayor
|   `-- conciliacion_final.py          Conciliacion de proveedores (Excel)
|-- cta cte - Proveedores.csv          Datos fuente: cuenta corriente
|-- registro cta ctble...csv           Datos fuente: mayor contable
|-- _ctacte.pkl                        Cache pandas de cuenta corriente
|-- _contable.pkl                      Cache pandas del mayor
|-- _dup_info.pkl                      Analisis de duplicados
|-- backavanzia.sql                    Respaldo base de datos (no utilizado)
|-- docs/
|   `-- prompt_conciliacion.md         Especificacion funcional original
`-- requirements.txt                   Dependencias Python
```

## Flujo de Ejecucion

Los generadores que consultan PostgreSQL toman la contraseña desde una
variable de entorno. No se guardan credenciales en el repositorio.

```powershell
$env:AVANZIA_DB_PASSWORD = "<password-local>"
```

El informe maestro para navegar los reportes es `index.html`.

### 1. Carga de datos (paso 1)

```powershell
python .\scripts\conciliacion_paso1.py
```

Lee los dos CSV y genera los archivos pickle que usan los siguientes pasos.

### 2. Analisis de duplicados (paso 2)

```powershell
python .\scripts\conciliacion_paso2.py
```

Verifica el patron de duplicacion en el mayor contable (misma transaccion
con distintos `categoriaid`). Genera `_dup_info.pkl`.

### 3. Generacion del reporte HTML interactivo

```powershell
python .\scripts\reporte_html.py
```

Genera `reporte_conciliacion.html` con:
- Resumen ejecutivo con KPIs
- 4 graficos embebidos en base64
- Selector interactivo de entidades (220 entidades)
- Tablas de movimientos de cuenta corriente y mayor contable
- Indicadores por ventana temporal (1, 3, 6, 12 meses)
- Filtrado por referencia, fecha y ordenamiento

## Datos de Entrada

- **cta cte - Proveedores.csv**: Movimientos de cuenta corriente con columnas
  `clientid`, `fecha`, `referenciatexto`, `haber`, `debe`, `saldo_acumulado`,
  `flows`, `categoriaid`.

- **registro cta ctble...csv**: Mayor contable con columnas `clientid`, `fecha`,
  `referenciatexto`, `totalprecio`, `cuentacontable`, `categoriaid`. Presenta
  filas duplicadas por categoria.

## Categorizacion de Entidades

Se clasifica segun `categoriaid` del mayor contable:

| Tipo          | Categorias                                          |
|---------------|-----------------------------------------------------|
| Cliente       | 1080, 11318, 1094, 11548                            |
| Proveedor     | 1081, 10685, 11360, 11345                           |
| Ambos         | Un clientid con categorias de ambos tipos           |
| Otro          | Categorias no identificadas                         |

## Algoritmo de Matching

El emparejamiento de movimientos uno a uno usa criterios combinados:

1. **Fecha**: tolerancia de +/- 5 dias
2. **Importe**: tolerancia de $1 (valor absoluto)
3. **Texto**: similitud minima de 70 (rapidfuzz token_set_ratio)

El algoritmo es greedy: para cada movimiento de cuenta corriente busca el
mejor candidato no utilizado en el mayor contable. El orden de procesamiento
puede afectar el resultado final.

## Criterios de Conciliacion

| Categoria | Condicion                                          |
|-----------|-----------------------------------------------------|
| Conciliado | Diferencia de saldo <= $1 Y todos los movimientos matchean |
| No cuadra | Diferencia de saldo > $1                            |

## Hallazgos Importantes

- El 99% de las entidades NO concilia por saldo (218 de 220).
- Solo 2 entidades tienen saldo conciliado.
- Hay 524 clientids en el mayor contable que no estan en cuenta corriente.
- La suma de `totalprecio` no representa el saldo del pasivo: el archivo
  contiene cuentas de gasto/activo, no la cuenta puente de proveedores.
- El mayor contable presenta filas duplicadas (misma transaccion, distinto
  `categoriaid`).

## Limitaciones Tecnicas

- El matching es greedy y depende del orden de las filas.
- No hay pruebas automatizadas.
- La logica de clasificacion esta hardcodeada en los scripts.
- Los HTML contienen datos financieros embebidos; no deben publicarse
  sin revisar confidencialidad.

## Dependencias

```
pandas
numpy
rapidfuzz
openpyxl
matplotlib
python-dateutil
Pillow
```

## Especificacion Funcional

La especificacion completa del negocio esta en `docs/prompt_conciliacion.md`.
