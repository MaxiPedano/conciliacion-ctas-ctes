-- =====================================================
-- CUENTAS CONTABLES POR ABUELO Y RANGO DE FECHAS
-- Motor/origen: JasperReports
-- Base: va9000-avanzia
-- Schema: test9000
-- =====================================================

-- Consulta original con parámetros JasperReports.
-- $P{param_abueloid}: ID del abuelo de las cuentas contables.
-- $P{Fecha_desde}: fecha inicial inclusive.
-- $P{Fecha_hasta}: fecha final inclusive.
--
-- La relación con stocklog se conserva. Si un registrocab tiene varios
-- stocklog, la consulta puede devolver más de una fila para ese registro.
SELECT
    test9000.categorias.id,
    test9000.categorias.name,
    test9000.categorias.parentid,
    test9000.categorias.grupo,
    test9000.categorias.procparentid,
    pr.name AS proceso,
    pa.name AS parent,
    ab.name AS abuelo,
    ab.id AS abueloid,
    test9000.categorias.orden,
    test9000.registrocab.totalimpuestos,
    test9000.registrocab.fecha,
    test9000.registrocab.totalprecio,
    test9000.registrocab.referenciatexto
FROM test9000.categorias
LEFT JOIN test9000.categorias pa
    ON test9000.categorias.parentid = pa.id
LEFT JOIN test9000.categorias ab
    ON pa.parentid = ab.id
LEFT JOIN test9000.categorias pr
    ON test9000.categorias.procparentid = pr.id
LEFT JOIN test9000.registrocab
    ON test9000.registrocab.cuentacontableid = test9000.categorias.id
LEFT JOIN test9000.stocklog sl
    ON sl.registrocabid = test9000.registrocab.id
WHERE test9000.categorias.grupo = 'cuentacontable'
  AND pa.parentid IS NOT NULL
  AND ab.id = $P{param_abueloid}
  AND test9000.registrocab.fecha >= $P{Fecha_desde}
  AND test9000.registrocab.fecha <= $P{Fecha_hasta}
ORDER BY abuelo, parent, name, proceso, fecha DESC;

-- =====================================================
-- Variante para PostgreSQL PREPARE/EXECUTE
-- $1 = abueloid, $2 = fecha desde, $3 = fecha hasta.
-- =====================================================

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
  AND ab.id = $1
  AND rc.fecha >= $2
  AND rc.fecha <= $3
ORDER BY abuelo, parent, name, proceso, fecha DESC;
