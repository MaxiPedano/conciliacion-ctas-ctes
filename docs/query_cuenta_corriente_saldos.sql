-- =====================================================
-- CUENTA CORRIENTE: DETALLE DE SALDOS
-- Motor/origen: JasperReports
-- Base: va9000-avanzia
-- Schema: test9000
-- =====================================================

-- Parámetros JasperReports:
-- $P{fechaDesde}, $P{fechaHasta}: ventana de movimientos.
-- $P{param_clientid}, $P{clientid}: filtro de cliente.
-- $P{referenciatexto}: búsqueda en la referencia del movimiento.
-- $P{orden}: ASC o DESC.
--
-- referencia_cta_contable combina cuentacontableid y categorias.name.
WITH datos_agrupados AS (
  SELECT
    RC.id,
    RC.clientid,
    RC.fecha,
    RC.clientname,
    RC.referenciatexto,
    RC.fechacompromiso,
    MAX(CASE
      WHEN RC.flowid = 11304 AND EXISTS (
        SELECT 1 FROM test9000.categoriasperfiles cp2
        WHERE cp2.perfilid = RC.clientid AND cp2.categoriaid = 1080
      ) THEN RC.totalimpuestos
      WHEN RC.flowid = 11304 THEN 0
      WHEN S.valor = -1 THEN RC.totalimpuestos
      ELSE 0
    END) AS haber,
    MAX(CASE
      WHEN RC.flowid = 11304 AND EXISTS (
        SELECT 1 FROM test9000.categoriasperfiles cp2
        WHERE cp2.perfilid = RC.clientid AND cp2.categoriaid = 1081
      ) THEN RC.totalimpuestos
      WHEN RC.flowid = 11304 THEN 0
      WHEN S.valor = 1 THEN RC.totalimpuestos
      ELSE 0
    END) AS debe,
    MAX(C.name) AS flows,
    MAX(C.id) AS flowsid,
    MAX(CC.id) AS cuentacontableid,
    MAX(CASE WHEN CC.id IS NULL THEN NULL
             ELSE CC.id::text || ' - ' || COALESCE(CC.name, '') END)
        AS referencia_cta_contable
  FROM test9000.registrocab RC
  INNER JOIN test9000.statusflows SF ON SF.id = RC.statusflowid
  INNER JOIN test9000.statuses S ON S.id = SF.statusid
  INNER JOIN test9000.flowdocument FD ON FD.statusid = S.id
  LEFT JOIN test9000.perfiles P ON P.id = RC.vendedorid
  INNER JOIN test9000.categorias C ON C.id = SF.categid
  LEFT JOIN test9000.categorias CC ON CC.id = RC.cuentacontableid
  INNER JOIN test9000.registrocuerpo RCU ON RC.id = RCU.presupcabid
  WHERE RC.flowid NOT IN (11213, 11204, 11208, 11180, 11203, 11197, 11206)
    AND RC.id NOT IN (11537, 11558)
    AND RC.fecha BETWEEN
      COALESCE(CAST($P{fechaDesde} AS DATE), DATE '2000-01-01')
      AND COALESCE(CAST($P{fechaHasta} AS DATE), CURRENT_DATE) + INTERVAL '3 months'
    AND (
      ($P{param_clientid} IS NOT NULL AND RC.clientid = $P{param_clientid})
      OR
      ($P{param_clientid} IS NULL AND ($P{clientid} IS NULL OR RC.clientid = $P{clientid}))
    )
  GROUP BY RC.id, RC.clientid, RC.fecha, RC.clientname,
           RC.referenciatexto, RC.fechacompromiso
), datos_con_totales AS (
  SELECT
    *,
    SUM(haber - debe) OVER (PARTITION BY clientid ORDER BY fecha, id) AS saldo_acumulado,
    SUM(haber) OVER (PARTITION BY clientid) AS total_haber_general,
    SUM(debe) OVER (PARTITION BY clientid) AS total_debe_general
  FROM datos_agrupados
)
SELECT
  *,
  (total_haber_general - total_debe_general) AS saldo_total
FROM datos_con_totales
WHERE (
  $P{referenciatexto} IS NULL
  OR $P{referenciatexto} = ''
  OR UPPER(referenciatexto) LIKE '%' || UPPER($P{referenciatexto}) || '%'
)
ORDER BY
  clientid,
  CASE WHEN $P{orden} = 'ASC' THEN fecha END ASC,
  CASE WHEN $P{orden} = 'DESC' THEN fecha END DESC,
  id DESC;
