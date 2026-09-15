# Base de Consultas Avanzia

## Flujos de Trabajo

Los siguientes flujos son los utilizados para la conciliación de cuentas corrientes:

| Flujo | FlowID (macroid) | Descripción |
|-------|------------------|-------------|
| CAJA: Egresos Juan | 11344 | Egresos con cuenta corriente |
| CAJA: Egresos Juan sin Cta. Cte. | 11433 | Egresos sin cuenta corriente |
| CAJA: Egresos sin cta cte | 11332 | Egresos sin cuenta corriente |
| Comprobantes Proveedores | 10303 | Comprobantes de proveedores |
| Ajustes negativos | 11472 | Ajustes con signo negativo |

---

## Consulta: Flujos y Estados

```sql
SET SCHEMA 'test9000';

SELECT
    sf.id AS statusflowid,
    -- Flow
    cat.id AS macroid,
    cat.name AS flow,
    -- Primer actividad
    s1.id,
    s1.descrip AS estado_actual,
    fp.id AS preguntaid,
    fp.pregunta,
    -- Actividad siguiente
    fr.id AS respuestaid,
    fr.respuesta,
    s2.id,
    s2.descrip AS estado_siguiente
FROM statusflows sf
LEFT JOIN statuses s1 ON s1.id = sf.statusid
LEFT JOIN statuses s2 ON s2.id = sf.sigstatusid
LEFT JOIN categorias cat ON cat.id = sf.categid
LEFT JOIN flowpreguntas fp ON fp.statusflowid = sf.id
LEFT JOIN flowrespuestas fr ON fr.flowpreguntasid = fp.id
ORDER BY cat.name, sf.tipo, s1.descrip;
```

---

## Consulta: Cuenta Corriente (Egresos)

Registros de `registrocab` con flows de egresos (cuenta corriente).

```sql
SET SCHEMA 'test9000';

SELECT
    id,
    clientid,
    clientname,
    fecha,
    referenciatexto,
    fechacompromiso,
    flowid,
    statusid,
    totalprecio,
    totalimpuestos,
    cuentacontableid
FROM registrocab
WHERE flowid IN (11344, 11433, 11332, 11472)
ORDER BY clientid, fecha;
```

### Flujos incluidos:
| FlowID | Nombre | Descripción |
|--------|--------|-------------|
| 11344 | CAJA: Egresos Juan | Egresos con cuenta corriente |
| 11433 | CAJA: Egresos Juan sin Cta. Cte. | Egresos sin cuenta corriente |
| 11332 | CAJA: Egresos sin cta cte | Egresos sin cuenta corriente |
| 11472 | Ajustes negativos | Ajustes con signo negativo |

### Conteo por flow:
| flowid | flow_name | record_count |
|--------|-----------|--------------|
| 11332 | CAJA: Egresos sin cta cte | 1,305 |
| 11433 | CAJA: Egresos Juan sin Cta. Cte. | 266 |
| 11344 | CAJA: Egresos Juan | 192 |
| 11472 | Ajustes negativos | 98 |
| **Total** | | **1,861** |

---

## Consulta: Cuenta Corriente con Detalle de Saldos

Esta consulta es independiente de los reportes de egresos y cuentas
contables. Agrupa cada `registrocab`, calcula `haber` y `debe` según el valor
del estado y genera el `saldo_acumulado` por cliente mediante una función de
ventana.

La consulta completa se conserva en
`docs/query_cuenta_corriente_saldos.sql` y el informe HTML se genera con:

```powershell
python .\scripts\reporte_cuenta_corriente.py
```

El informe generado es `reporte_cuenta_corriente.html` e incluye todos los
registros que componen el saldo, con estas columnas contables:

- `haber`
- `debe`
- `saldo acumulado`
- `saldo total`
- `referencia cta contable` (`cuentacontableid` + nombre de `categorias`)

El filtro de fechas recalcula los saldos usando únicamente los movimientos
visibles dentro del período, comenzando el saldo del período en cero. Esto
mantiene el comportamiento de la consulta original, que aplica la fecha antes
de calcular las funciones de ventana.

### Parámetros JasperReports

| Parámetro | Uso |
|-----------|-----|
| `$P{fechaDesde}` | Fecha inicial del movimiento |
| `$P{fechaHasta}` | Fecha final del movimiento |
| `$P{param_clientid}` | Cliente principal, si se informa |
| `$P{clientid}` | Cliente alternativo |
| `$P{referenciatexto}` | Texto a buscar en la referencia |
| `$P{orden}` | Orden de fecha: `ASC` o `DESC` |

---

## Consulta: Mayor Contable

Registros de `registrocab` con `cuentacontableid` definido (asiento contable).

```sql
SET SCHEMA 'test9000';

SELECT
    id,
    clientid,
    clientname,
    fecha,
    referenciatexto,
    fechacompromiso,
    flowid,
    totalprecio,
    totalimpuestos,
    cuentacontableid,
    statusid
FROM registrocab
WHERE cuentacontableid IS NOT NULL
ORDER BY clientid, fecha;
```

**Total: 4,770 registros**

---

## Consulta: Cuentas Contables por Abuelo y Rango de Fechas

Consulta utilizada por JasperReports para listar las cuentas contables dentro
de un abuelo determinado y sus registros de `registrocab` en un rango de
fechas.

### Parámetros del informe

| Parámetro | Uso |
|-----------|-----|
| `$P{param_abueloid}` | ID de la categoría raíz (`abuelo`) de las cuentas contables |
| `$P{Fecha_desde}` | Fecha inicial, inclusive |
| `$P{Fecha_hasta}` | Fecha final, inclusive |

```sql
SELECT
    c.id,
    c.name,
    c.parentid,
    c.grupo,
    c.procparentid,
    pr.name AS proceso,
    pa.name AS parent,
    ab.name AS abuelo,
    ab.id AS abueloid,
    c.orden,
    rc.totalimpuestos,
    rc.fecha,
    rc.totalprecio,
    rc.referenciatexto
FROM test9000.categorias c
LEFT JOIN test9000.categorias pa ON c.parentid = pa.id
LEFT JOIN test9000.categorias ab ON pa.parentid = ab.id
LEFT JOIN test9000.categorias pr ON c.procparentid = pr.id
LEFT JOIN test9000.registrocab rc ON rc.cuentacontableid = c.id
LEFT JOIN test9000.stocklog sl ON sl.registrocabid = rc.id
WHERE c.grupo = 'cuentacontable'
  AND pa.parentid IS NOT NULL
  AND ab.id = $P{param_abueloid}
  AND rc.fecha >= $P{Fecha_desde}
  AND rc.fecha <= $P{Fecha_hasta}
ORDER BY abuelo, parent, name, proceso, fecha DESC;
```

### Notas

- El filtro de `fecha` sobre `registrocab` hace que, en la práctica, solo se
  devuelvan cuentas con un registro dentro del período.
- El `LEFT JOIN` a `stocklog` se conserva porque pertenece a la consulta
  original, aunque puede repetir una fila si un `registrocab` tiene varios
  movimientos en `stocklog`.
- Para ejecutar la misma lógica directamente en PostgreSQL, reemplazar los
  parámetros Jasper por `$1` (`abueloid`), `$2` (`fecha desde`) y `$3` (`fecha
  hasta`) en una sentencia preparada.

---

## Consulta: Sobreposicion CTA_CTE vs MAYOR_CONTABLE

```sql
SET SCHEMA 'test9000';

SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN flowid IN (11344, 11433, 11332, 11472) 
               AND cuentacontableid IS NOT NULL THEN 1 END) as both_cte_and_contable,
    COUNT(CASE WHEN flowid IN (11344, 11433, 11332, 11472) 
               AND cuentacontableid IS NULL THEN 1 END) as cte_only,
    COUNT(CASE WHEN flowid NOT IN (11344, 11433, 11332, 11472) 
               AND cuentacontableid IS NOT NULL THEN 1 END) as contable_only
FROM registrocab 
WHERE flowid IN (11344, 11433, 11332, 11472) OR cuentacontableid IS NOT NULL;
```

Resultado:
| Total | Both | CTE Only | Contable Only |
|-------|------|----------|---------------|
| 5,073 | 1,558 | 303 | 3,212 |

---

## Consulta: Categorías de Perfil (Cliente/Proveedor)

```sql
SET SCHEMA 'test9000';

-- Categorías para clasificación
SELECT id, name, parentid 
FROM categorias 
WHERE id IN (1080, 11318, 1094, 11548,  -- Clientes
             1081, 10685, 11360, 11345) -- Proveedores
ORDER BY id;
```

Resultado:
| id | name | parentid |
|----|------|----------|
| 1080 | Cliente | |
| 1081 | Proveedor | |
| 1094 | Leads | 1080 |
| 10685 | Prov. con cta. cte. en pesos | 1081 |
| 11318 | CLIENTE CON CTA CTE | 1080 |
| 11345 | Prov. con cta. cte. en dólares | 1081 |
| 11360 | Proveedor sin cte. cte. en pesos | 1081 |
| 11548 | MercadoLibre | 1081 |

---

## Consulta: Fuera de Alcance

```sql
SET SCHEMA 'test9000';

SELECT DISTINCT c.clientid, c.clientname
FROM registrocab c
LEFT JOIN registrocab cc ON c.clientid = cc.clientid 
    AND cc.flowid IN (11344, 11433, 11332, 11472)
WHERE c.cuentacontableid IS NOT NULL 
    AND cc.clientid IS NULL
ORDER BY c.clientname;
```

---

## Notas

- Todos los queries usan el schema `test9000`
- Los nombres de tablas son provisorios; ajustar según la estructura real de la base
- Los flujos relevantes para conciliación están filtrados por `macroid` (flowsid)
- Los ajustes negativos (11472) deben revisarse para confirmar si impactan la cuenta corriente
