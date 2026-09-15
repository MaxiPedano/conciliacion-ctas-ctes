-- =====================================================
-- CONSULTAS DE CONCILIACION - CONTEXTO
-- Base: va9000-avanzia
-- Schema: test9000
-- Alcance: proveedores y egresos
-- Flujos: 10150, 10303, 11344, 11433 y 11332
-- =====================================================

-- La prioridad de clasificación es intencional: un perfil puede tener
-- varias categorías asignadas en categoriasperfiles.

-- 1. CLASIFICACION FINAL DE EGRESOS
WITH clasificados AS (
    SELECT
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (cp.categoriaid = 1081 OR c.parentid = 1081)
            ) THEN 'Proveedor'
            WHEN EXISTS (
                SELECT 1
                FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (cp.categoriaid = 1082 OR c.parentid = 1082)
            ) THEN 'Empleado'
            WHEN EXISTS (
                SELECT 1
                FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (
                      cp.categoriaid IN (11367, 10659)
                      OR c.parentid IN (11367, 10659)
                  )
            ) THEN 'Vendedor'
            WHEN EXISTS (
                SELECT 1
                FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (cp.categoriaid = 1080 OR c.parentid = 1080)
            ) THEN 'Cliente'
            WHEN EXISTS (
                SELECT 1
                FROM test9000.categoriasperfiles cp
                WHERE cp.perfilid = rc.clientid
                  AND cp.categoriaid = 11364
            ) THEN 'Socios'
            WHEN EXISTS (
                SELECT 1
                FROM test9000.categoriasperfiles cp
                WHERE cp.perfilid = rc.clientid
                  AND cp.categoriaid IN (10805, 10820, 10821)
            ) THEN 'Ente Recaudador'
            ELSE 'Sin clasificar'
        END AS perfil_tipo,
        cat.name AS flow_name,
        rc.totalprecio
    FROM test9000.registrocab rc
    JOIN test9000.categorias cat ON cat.id = rc.flowid
    WHERE rc.flowid IN (10150, 10303, 11344, 11433, 11332)
      AND rc.clientid IS NOT NULL
)
SELECT
    perfil_tipo,
    flow_name,
    COUNT(*) AS registros,
    SUM(totalprecio) AS total_monto
FROM clasificados
GROUP BY perfil_tipo, flow_name
ORDER BY perfil_tipo, flow_name;

-- 2. REGISTROS INVOLUCRADOS
-- Incluye registrocab, clientid, fecha, referencia, flujo y montos.
WITH clasificados AS (
    SELECT
        rc.id AS registrocab_id,
        rc.clientid,
        rc.clientname,
        p.razonsocial,
        p.nombre,
        p.apellido,
        rc.fecha,
        rc.referenciatexto,
        rc.flowid,
        cat.name AS flow_name,
        rc.totalprecio,
        rc.totalimpuestos,
        CASE
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (cp.categoriaid = 1081 OR c.parentid = 1081)
            ) THEN 'Proveedor'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (cp.categoriaid = 1082 OR c.parentid = 1082)
            ) THEN 'Empleado'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (
                      cp.categoriaid IN (11367, 10659)
                      OR c.parentid IN (11367, 10659)
                  )
            ) THEN 'Vendedor'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (cp.categoriaid = 1080 OR c.parentid = 1080)
            ) THEN 'Cliente'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                WHERE cp.perfilid = rc.clientid AND cp.categoriaid = 11364
            ) THEN 'Socios'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                WHERE cp.perfilid = rc.clientid
                  AND cp.categoriaid IN (10805, 10820, 10821)
            ) THEN 'Ente Recaudador'
            ELSE 'Sin clasificar'
        END AS perfil_tipo
    FROM test9000.registrocab rc
    JOIN test9000.categorias cat ON cat.id = rc.flowid
    LEFT JOIN test9000.perfiles p ON p.id = rc.clientid
    WHERE rc.flowid IN (10150, 10303, 11344, 11433, 11332)
      AND rc.clientid IS NOT NULL
)
SELECT *
FROM clasificados
ORDER BY perfil_tipo, clientname, fecha, registrocab_id;

-- 3. CATEGORIAS ENCONTRADAS
SELECT
    c.id AS categoriaid,
    c.name AS categoria_name,
    c.parentid,
    parent.name AS parent_name,
    COUNT(DISTINCT cp.perfilid) AS perfiles
FROM test9000.categorias c
LEFT JOIN test9000.categorias parent ON parent.id = c.parentid
LEFT JOIN test9000.categoriasperfiles cp ON cp.categoriaid = c.id
WHERE c.id IN (1081, 10685, 11345, 11360, 11548,
               1082, 11326, 11367, 10659, 11364)
GROUP BY c.id, c.name, c.parentid, parent.name
ORDER BY c.id;

-- 4. PERFILES SIN CATEGORIA INVESTIGADOS Y RESUELTOS
WITH investigados (clientid, clientname, tipo_detectado) AS (
    VALUES
        (374, 'Yamila Musa', 'Empleado (sueldo)'),
        (421, 'Julian Musa', 'Empleado (sueldo)'),
        (422, 'Yamil Musa', 'Empleado (sueldo)'),
        (419, 'Scorzelli Valdes Gabriela Lucía', 'Ex-Empleado (honorarios)')
)
SELECT
    i.clientid,
    i.clientname,
    COUNT(rc.id) AS registros,
    i.tipo_detectado
FROM investigados i
JOIN test9000.registrocab rc ON rc.clientid = i.clientid
WHERE rc.flowid IN (10150, 10303, 11344, 11433, 11332)
GROUP BY i.clientid, i.clientname, i.tipo_detectado
ORDER BY i.clientid;

-- 5. REGISTROS SIN CLIENTID
-- Transferencias internas sin proveedor asociado; no se clasifican por perfil.
SELECT
    rc.id AS registrocab_id,
    rc.fecha,
    rc.referenciatexto,
    rc.flowid,
    cat.name AS flow_name,
    rc.totalprecio,
    rc.totalimpuestos
FROM test9000.registrocab rc
JOIN test9000.categorias cat ON cat.id = rc.flowid
WHERE rc.flowid IN (10150, 10303, 11344, 11433, 11332)
  AND rc.clientid IS NULL
ORDER BY rc.fecha, rc.id;

-- 6. RESUMEN POR PERFIL
WITH clasificados AS (
    SELECT
        rc.clientid,
        rc.clientname,
        p.razonsocial,
        rc.fecha,
        rc.totalprecio,
        CASE
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (cp.categoriaid = 1081 OR c.parentid = 1081)
            ) THEN 'Proveedor'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (cp.categoriaid = 1082 OR c.parentid = 1082)
            ) THEN 'Empleado'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (
                      cp.categoriaid IN (11367, 10659)
                      OR c.parentid IN (11367, 10659)
                  )
            ) THEN 'Vendedor'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                JOIN test9000.categorias c ON c.id = cp.categoriaid
                WHERE cp.perfilid = rc.clientid
                  AND (cp.categoriaid = 1080 OR c.parentid = 1080)
            ) THEN 'Cliente'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                WHERE cp.perfilid = rc.clientid AND cp.categoriaid = 11364
            ) THEN 'Socios'
            WHEN EXISTS (
                SELECT 1 FROM test9000.categoriasperfiles cp
                WHERE cp.perfilid = rc.clientid
                  AND cp.categoriaid IN (10805, 10820, 10821)
            ) THEN 'Ente Recaudador'
            ELSE 'Sin clasificar'
        END AS perfil_tipo
    FROM test9000.registrocab rc
    LEFT JOIN test9000.perfiles p ON p.id = rc.clientid
    WHERE rc.flowid IN (10150, 10303, 11344, 11433, 11332)
      AND rc.clientid IS NOT NULL
)
SELECT
    clientid,
    MAX(clientname) AS clientname,
    MAX(razonsocial) AS razonsocial,
    perfil_tipo,
    COUNT(*) AS total_registros,
    SUM(totalprecio) AS monto_total,
    MIN(fecha) AS primera_fecha,
    MAX(fecha) AS ultima_fecha
FROM clasificados
GROUP BY clientid, perfil_tipo
ORDER BY perfil_tipo, monto_total DESC;

-- 7. CUENTAS CONTABLES POR ABUELO Y RANGO DE FECHAS
-- Consulta Jasper documentada en:
-- docs/query_cuentas_contables_jasper.sql
--
-- No se ejecuta aquí porque los parámetros Jasper $P{...} no son sintaxis
-- válida para psql. La variante PostgreSQL parametrizada también está
-- documentada junto con la consulta original.
