#!/usr/bin/env python3
"""Genera un reporte independiente de cuenta corriente y sus saldos."""

import html
import os
from datetime import date, datetime

import pandas as pd
import psycopg2


DB_CONFIG = {
    "host": os.getenv("AVANZIA_DB_HOST", "localhost"),
    "database": os.getenv("AVANZIA_DB_NAME", "va9000-avanzia"),
    "user": os.getenv("AVANZIA_DB_USER", "postgres"),
    "password": os.getenv("AVANZIA_DB_PASSWORD") or os.getenv("PGPASSWORD"),
}


# Se conserva la lógica de la consulta entregada y se agrega la referencia de
# la cuenta contable asociada a registrocab.cuentacontableid.
QUERY_DETAIL = """
WITH datos_agrupados AS (
    SELECT
        rc.id,
        rc.clientid,
        rc.fecha,
        rc.clientname,
        rc.referenciatexto,
        rc.fechacompromiso,
        MAX(CASE
            WHEN rc.flowid = 11304 AND EXISTS (
                SELECT 1
                FROM test9000.categoriasperfiles cp2
                WHERE cp2.perfilid = rc.clientid
                  AND cp2.categoriaid = 1080
            ) THEN rc.totalimpuestos
            WHEN rc.flowid = 11304 THEN 0
            WHEN s.valor = -1 THEN rc.totalimpuestos
            ELSE 0
        END) AS haber,
        MAX(CASE
            WHEN rc.flowid = 11304 AND EXISTS (
                SELECT 1
                FROM test9000.categoriasperfiles cp2
                WHERE cp2.perfilid = rc.clientid
                  AND cp2.categoriaid = 1081
            ) THEN rc.totalimpuestos
            WHEN rc.flowid = 11304 THEN 0
            WHEN s.valor = 1 THEN rc.totalimpuestos
            ELSE 0
        END) AS debe,
        MAX(c.name) AS flows,
        MAX(c.id) AS flowsid,
        MAX(cc.id) AS cuentacontableid,
        MAX(
            CASE
                WHEN cc.id IS NULL THEN NULL
                ELSE cc.id::text || ' - ' || COALESCE(cc.name, '')
            END
        ) AS referencia_cta_contable
    FROM test9000.registrocab rc
    INNER JOIN test9000.statusflows sf ON sf.id = rc.statusflowid
    INNER JOIN test9000.statuses s ON s.id = sf.statusid
    INNER JOIN test9000.flowdocument fd ON fd.statusid = s.id
    LEFT JOIN test9000.perfiles p ON p.id = rc.vendedorid
    INNER JOIN test9000.categorias c ON c.id = sf.categid
    LEFT JOIN test9000.categorias cc ON cc.id = rc.cuentacontableid
    INNER JOIN test9000.registrocuerpo rcu ON rc.id = rcu.presupcabid
    WHERE rc.flowid NOT IN (11213, 11204, 11208, 11180, 11203, 11197, 11206)
      AND rc.id NOT IN (11537, 11558)
      AND rc.fecha BETWEEN DATE '2000-01-01' AND CURRENT_DATE + INTERVAL '3 months'
    GROUP BY
        rc.id,
        rc.clientid,
        rc.fecha,
        rc.clientname,
        rc.referenciatexto,
        rc.fechacompromiso
), datos_con_totales AS (
    SELECT
        *,
        SUM(COALESCE(haber, 0) - COALESCE(debe, 0)) OVER (
            PARTITION BY clientid
            ORDER BY fecha, id
        ) AS saldo_acumulado,
        SUM(COALESCE(haber, 0)) OVER (PARTITION BY clientid) AS total_haber_general,
        SUM(COALESCE(debe, 0)) OVER (PARTITION BY clientid) AS total_debe_general
    FROM datos_agrupados
)
SELECT
    *,
    (total_haber_general - total_debe_general) AS saldo_total
FROM datos_con_totales
ORDER BY clientid, fecha, id;
"""


# Versión de referencia para el informe Jasper, con los parámetros originales.
QUERY_JASPER = """
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
SELECT *, (total_haber_general - total_debe_general) AS saldo_total
FROM datos_con_totales
WHERE (
  $P{referenciatexto} IS NULL
  OR $P{referenciatexto} = ''
  OR UPPER(referenciatexto) LIKE '%' || UPPER($P{referenciatexto}) || '%'
)
ORDER BY clientid,
  CASE WHEN $P{orden} = 'ASC' THEN fecha END ASC,
  CASE WHEN $P{orden} = 'DESC' THEN fecha END DESC,
  id DESC;
"""


def read_query(connection, query):
    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
    return pd.DataFrame(rows, columns=columns)


def empty(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def numeric(value):
    if empty(value):
        return 0.0
    return float(value)


def clean_text(value):
    return " ".join(str(value).split())


def money(value):
    return f"${numeric(value):,.2f}"


def integer(value):
    return f"{int(value):,}"


def text(value, fallback="-"):
    if empty(value) or str(value).strip() == "":
        return fallback
    return html.escape(clean_text(value))


def attribute(value):
    if empty(value):
        return ""
    return html.escape(clean_text(value), quote=True)


def identifier(value):
    if empty(value):
        return "-"
    return str(int(float(value)))


def iso_date(value):
    if empty(value):
        return ""
    if isinstance(value, (datetime, date)):
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
    return str(value)[:10]


def display_date(value):
    value = iso_date(value)
    if not value:
        return "-"
    parts = value.split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return html.escape(value)


def client_key(value):
    return "SIN_CLIENTE" if empty(value) else str(value)


def build_client_summary(df):
    if df.empty:
        return ""
    grouped = []
    for key, group in df.groupby(df["clientid"].map(client_key), sort=False):
        first = group.iloc[0]
        grouped.append(
            {
                "clientid": "" if key == "SIN_CLIENTE" else key,
                "clientname": group["clientname"].dropna().iloc[0] if group["clientname"].notna().any() else "SIN CLIENTE",
                "records": len(group),
                "haber": group["haber"].fillna(0).map(numeric).sum(),
                "debe": group["debe"].fillna(0).map(numeric).sum(),
                "saldo": group["haber"].fillna(0).map(numeric).sum() - group["debe"].fillna(0).map(numeric).sum(),
                "first_date": group["fecha"].min(),
                "last_date": group["fecha"].max(),
            }
        )
    grouped.sort(key=lambda item: abs(item["saldo"]), reverse=True)
    rows = []
    for item in grouped:
        rows.append(
            "<tr>"
            f"<td>{text(item['clientid'])}</td>"
            f"<td>{text(item['clientname'])}</td>"
            f"<td>{integer(item['records'])}</td>"
            f"<td class=\"currency\">{money(item['haber'])}</td>"
            f"<td class=\"currency\">{money(item['debe'])}</td>"
            f"<td class=\"currency\">{money(item['saldo'])}</td>"
            f"<td>{display_date(item['first_date'])}</td>"
            f"<td>{display_date(item['last_date'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_detail_rows(df):
    rows = []
    for _, row in df.iterrows():
        account_reference = row["referencia_cta_contable"]
        rows.append(
            f"<tr class=\"detail-row\" data-id=\"{attribute(row['id'])}\" "
            f"data-date=\"{attribute(iso_date(row['fecha']))}\" "
            f"data-clientid=\"{attribute('' if empty(row['clientid']) else row['clientid'])}\" "
            f"data-clientname=\"{attribute('' if empty(row['clientname']) else row['clientname'])}\" "
            f"data-reference=\"{attribute('' if empty(row['referenciatexto']) else row['referenciatexto'])}\" "
            f"data-account=\"{attribute('' if empty(account_reference) else account_reference)}\" "
            f"data-flow=\"{attribute(row['flows'])}\" "
            f"data-haber=\"{attribute(numeric(row['haber']))}\" "
            f"data-debe=\"{attribute(numeric(row['debe']))}\">"
            f"<td>{identifier(row['id'])}</td>"
            f"<td>{display_date(row['fecha'])}</td>"
            f"<td>{text(row['clientid'])}</td>"
            f"<td>{text(row['clientname'])}</td>"
            f"<td>{text(row['referenciatexto'])}</td>"
            f"<td>{display_date(row['fechacompromiso'])}</td>"
            f"<td>{text(row['flows'])}</td>"
            f"<td>{text(account_reference)}</td>"
            f"<td class=\"currency\">{money(row['haber'])}</td>"
            f"<td class=\"currency\">{money(row['debe'])}</td>"
            f"<td class=\"currency running-balance\">{money(row['saldo_acumulado'])}</td>"
            f"<td class=\"currency total-balance\">{money(row['saldo_total'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def query_block(title, query):
    return (
        f"<details><summary>{html.escape(title)}</summary>"
        f"<pre class=\"query-box\">{html.escape(query.strip())}</pre></details>"
    )


def generate_report():
    print("Conectando a la base de datos...")
    with psycopg2.connect(**DB_CONFIG) as connection:
        print("Ejecutando consulta de cuenta corriente...")
        df = read_query(connection, QUERY_DETAIL)

    if not df.empty:
        df = df.sort_values(["clientid", "fecha", "id"], na_position="last")

    total_haber = df["haber"].fillna(0).map(numeric).sum() if not df.empty else 0
    total_debe = df["debe"].fillna(0).map(numeric).sum() if not df.empty else 0
    total_saldo = total_haber - total_debe
    client_count = df["clientid"].nunique(dropna=True) if not df.empty else 0
    client_summary_html = build_client_summary(df)
    detail_html = build_detail_rows(df)
    flow_options = sorted(df["flows"].dropna().astype(str).unique()) if not df.empty else []
    flow_options_html = "\n".join(
        f"<option value=\"{attribute(flow)}\">{text(flow)}</option>" for flow in flow_options
    )
    years = sorted(
        {iso_date(value)[:4] for value in df["fecha"] if iso_date(value)},
        reverse=True,
    ) if not df.empty else []
    year_options_html = "\n".join(
        f"<option value=\"{attribute(year)}\">{text(year)}</option>" for year in years
    )
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cuenta Corriente - Detalle de Saldos</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: Segoe UI, Tahoma, sans-serif; background: #f3f6f8; color: #263238; line-height: 1.45; }}
        .container {{ max-width: 1700px; margin: auto; padding: 20px; }}
        header {{ padding: 30px; margin-bottom: 24px; border-radius: 12px; color: white; background: linear-gradient(135deg, #39265e, #7d4aa0); box-shadow: 0 5px 16px #39265e22; }}
        h1 {{ margin: 0 0 8px; font-size: 2.2rem; }}
        h2 {{ margin: 0 0 18px; color: #39265e; border-bottom: 2px solid #a477c4; padding-bottom: 8px; }}
        .subtitle {{ margin: 3px 0; opacity: .9; }}
        .section {{ background: white; padding: 24px; margin-bottom: 24px; border-radius: 12px; box-shadow: 0 2px 9px #39265e14; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 14px; margin: 16px 0; }}
        .summary-card {{ padding: 18px; border-radius: 10px; color: white; background: linear-gradient(135deg, #72509a, #9a6ab3); }}
        .summary-card.green {{ background: linear-gradient(135deg, #287a62, #48a984); }}
        .summary-card.orange {{ background: linear-gradient(135deg, #c77925, #e6a23c); }}
        .summary-card.red {{ background: linear-gradient(135deg, #a94442, #d66b62); }}
        .summary-card h3 {{ margin: 0 0 4px; color: white; font-size: 1.45rem; }}
        .summary-card p {{ margin: 0; opacity: .9; }}
        table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
        th, td {{ padding: 9px 11px; text-align: left; border-bottom: 1px solid #dce4e8; vertical-align: top; }}
        th {{ position: sticky; top: 0; z-index: 1; color: white; background: #72509a; }}
        tbody tr:nth-child(even) {{ background: #faf8fc; }}
        tbody tr:hover {{ background: #f0e8f5; }}
        .currency {{ text-align: right; white-space: nowrap; font-family: Consolas, monospace; }}
        .table-wrap {{ max-height: 720px; overflow: auto; border: 1px solid #dce4e8; border-radius: 7px; }}
        .filters {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: 10px; padding: 14px; margin: 15px 0; background: #f3eef7; border: 1px solid #e2d6eb; border-radius: 8px; }}
        .filters label {{ display: flex; flex-direction: column; gap: 4px; color: #49365d; font-size: .82rem; font-weight: 600; }}
        .filters input, .filters select, .filters button {{ min-height: 36px; padding: 7px 9px; border: 1px solid #cbbbd5; border-radius: 5px; background: white; font: inherit; }}
        .filters button {{ align-self: end; cursor: pointer; color: white; background: #543779; border-color: #543779; font-weight: 600; }}
        .filter-summary {{ margin: 10px 0; color: #49365d; font-weight: 600; }}
        .empty-row {{ display: none; }}
        details {{ margin: 10px 0; border: 1px solid #dce4e8; border-radius: 6px; }}
        summary {{ padding: 10px 12px; cursor: pointer; color: #543779; font-weight: 600; }}
        .query-box {{ margin: 0; padding: 15px; overflow: auto; color: #f4eff8; background: #241c2e; font: .78rem Consolas, monospace; white-space: pre-wrap; }}
        footer {{ padding: 18px; text-align: center; color: #60747d; font-size: .85rem; }}
        @media (max-width: 700px) {{ .container {{ padding: 10px; }} header, .section {{ padding: 16px; }} h1 {{ font-size: 1.7rem; }} th, td {{ padding: 7px; }} }}
    </style>
</head>
<body>
<div class="container">
    <header>
        <h1>CUENTA CORRIENTE</h1>
        <p class="subtitle">Detalle de todos los registros que componen cada saldo</p>
        <p class="subtitle">La cuenta se calcula como Haber - Debe según el rango seleccionado</p>
        <p class="subtitle">Generado: {generated_at}</p>
    </header>

    <section class="section">
        <h2>Resumen del Saldo</h2>
        <div class="summary-grid">
            <div class="summary-card green"><h3 id="card-records">{integer(len(df))}</h3><p>Registros visibles</p></div>
            <div class="summary-card"><h3 id="card-clients">{integer(client_count)}</h3><p>Clientes</p></div>
            <div class="summary-card"><h3 id="card-haber">{money(total_haber)}</h3><p>Total Haber</p></div>
            <div class="summary-card orange"><h3 id="card-debe">{money(total_debe)}</h3><p>Total Debe</p></div>
            <div class="summary-card red"><h3 id="card-saldo">{money(total_saldo)}</h3><p>Saldo total</p></div>
        </div>
        <p id="date-summary" class="filter-summary"></p>
    </section>

    <section class="section">
        <h2>Resumen por Cliente</h2>
        <p>Seleccione un año o un rango de fechas para evaluar el saldo de cada cliente.</p>
        <div class="filters">
            <label>Año
                <select id="year-filter"><option value="">Todos los años</option>{year_options_html}</select>
            </label>
            <label>Fecha desde
                <input id="date-from" type="date">
            </label>
            <label>Fecha hasta
                <input id="date-to" type="date">
            </label>
        </div>
        <div class="table-wrap"><table id="client-summary-table" data-excel-table data-excel-title="Resumen por Cliente" data-excel-all-source="client-summary-all-table">
            <thead><tr><th>clientid</th><th>cliente</th><th>registros</th><th>haber</th><th>debe</th><th>saldo</th><th>primera fecha</th><th>última fecha</th></tr></thead>
            <tbody id="client-summary-body">{client_summary_html}</tbody>
        </table><table id="client-summary-all-table" style="display:none">
            <thead><tr><th>clientid</th><th>cliente</th><th>registros</th><th>haber</th><th>debe</th><th>saldo</th><th>primera fecha</th><th>última fecha</th></tr></thead>
            <tbody>{client_summary_html}</tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Registros que Componen el Saldo</h2>
        <p>El detalle utiliza el mismo año o rango de fechas seleccionado en el resumen de clientes.</p>
        <div class="filters">
            <label>Cliente ID o nombre
                <input id="client-filter" type="search" placeholder="ID o nombre">
            </label>
            <label>Referencia
                <input id="reference-filter" type="search" placeholder="Referencia o cuenta contable">
            </label>
            <label>Flujo
                <select id="flow-filter"><option value="">Todos</option>{flow_options_html}</select>
            </label>
            <label>Orden
                <select id="order-filter"><option value="ASC">Fecha ascendente</option><option value="DESC">Fecha descendente</option></select>
            </label>
            <button id="clear-filters" type="button">Limpiar filtros</button>
        </div>
        <p id="detail-summary" class="filter-summary"></p>
        <div class="table-wrap"><table id="detail-table" data-excel-table data-excel-title="Registros que Componen el Saldo">
            <thead><tr><th>registrocab</th><th>fecha</th><th>clientid</th><th>cliente</th><th>referencia</th><th>fecha compromiso</th><th>flujo</th><th>referencia cta contable</th><th>haber</th><th>debe</th><th>saldo acumulado</th><th>saldo total</th></tr></thead>
            <tbody>{detail_html}<tr id="no-results" class="empty-row"><td colspan="12">No hay registros para los filtros seleccionados.</td></tr></tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Consulta Base</h2>
        {query_block("Consulta Jasper con referencia de cuenta contable", QUERY_JASPER)}
        {query_block("Consulta ejecutada para cargar el informe", QUERY_DETAIL)}
    </section>

    <footer>Reporte separado de cuenta corriente | Base: va9000-avanzia | Schema: test9000</footer>
</div>
<script>
(function () {{
    const rows = Array.from(document.querySelectorAll('#detail-table .detail-row'));
    const tbody = document.querySelector('#detail-table tbody');
    const noResults = document.getElementById('no-results');
    const yearFilter = document.getElementById('year-filter');
    const dateFrom = document.getElementById('date-from');
    const dateTo = document.getElementById('date-to');
    const clientFilter = document.getElementById('client-filter');
    const referenceFilter = document.getElementById('reference-filter');
    const flowFilter = document.getElementById('flow-filter');
    const orderFilter = document.getElementById('order-filter');

    function numeric(value) {{ return Number(value || 0); }}
    function money(value) {{ return new Intl.NumberFormat('es-AR', {{ style: 'currency', currency: 'ARS' }}).format(numeric(value)); }}
    function count(value) {{ return numeric(value).toLocaleString('es-AR'); }}
    function escapeHtml(value) {{
        const entities = {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }};
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {{ return entities[character]; }});
    }}
    function displayDate(value) {{
        if (!value) return '-';
        const parts = value.split('-');
        return parts.length === 3 ? parts[2] + '/' + parts[1] + '/' + parts[0] : value;
    }}
    function inDateRange(row) {{
        return (!dateFrom.value || row.dataset.date >= dateFrom.value)
            && (!dateTo.value || row.dataset.date <= dateTo.value);
    }}
    function matches(row) {{
        const clientText = clientFilter.value.trim().toLowerCase();
        const referenceText = referenceFilter.value.trim().toLowerCase();
        const clientValue = (row.dataset.clientid + ' ' + row.dataset.clientname).toLowerCase();
        const referenceValue = (row.dataset.reference + ' ' + row.dataset.account).toLowerCase();
        return inDateRange(row)
            && (!clientText || clientValue.includes(clientText))
            && (!referenceText || referenceValue.includes(referenceText))
            && (!flowFilter.value || row.dataset.flow === flowFilter.value);
    }}
    function compareRows(left, right, descending) {{
        const dateCompare = (left.dataset.date || '').localeCompare(right.dataset.date || '');
        if (dateCompare !== 0) return descending ? -dateCompare : dateCompare;
        const idCompare = numeric(left.dataset.id) - numeric(right.dataset.id);
        return descending ? -idCompare : idCompare;
    }}
    function renderClientSummary(visible) {{
        const groups = {{}};
        visible.forEach(function (row) {{
            const key = row.dataset.clientid || 'SIN_CLIENTE';
            if (!groups[key]) groups[key] = {{ id: row.dataset.clientid, name: row.dataset.clientname || 'SIN CLIENTE', rows: [], haber: 0, debe: 0 }};
            groups[key].rows.push(row);
            groups[key].haber += numeric(row.dataset.haber);
            groups[key].debe += numeric(row.dataset.debe);
        }});
        const ordered = Object.values(groups).sort(function (left, right) {{
            return Math.abs(right.haber - right.debe) - Math.abs(left.haber - left.debe);
        }});
        let body = '';
        ordered.forEach(function (group) {{
            const dates = group.rows.map(function (row) {{ return row.dataset.date; }}).filter(Boolean).sort();
            const saldo = group.haber - group.debe;
            body += '<tr><td>' + escapeHtml(group.id || '-') + '</td>'
                + '<td>' + escapeHtml(group.name) + '</td>'
                + '<td>' + count(group.rows.length) + '</td>'
                + '<td class="currency">' + money(group.haber) + '</td>'
                + '<td class="currency">' + money(group.debe) + '</td>'
                + '<td class="currency">' + money(saldo) + '</td>'
                + '<td>' + displayDate(dates[0]) + '</td>'
                + '<td>' + displayDate(dates[dates.length - 1]) + '</td></tr>';
        }});
        document.getElementById('client-summary-body').innerHTML = body;
    }}
    function render() {{
        const visible = rows.filter(matches);
        const chronological = visible.slice().sort(function (left, right) {{ return compareRows(left, right, false); }});
        const groups = {{}};
        chronological.forEach(function (row) {{
            const key = row.dataset.clientid || 'SIN_CLIENTE';
            if (!groups[key]) groups[key] = {{ running: 0, total: 0 }};
            groups[key].running += numeric(row.dataset.haber) - numeric(row.dataset.debe);
            groups[key].total += numeric(row.dataset.haber) - numeric(row.dataset.debe);
            row.querySelector('.running-balance').textContent = money(groups[key].running);
        }});
        chronological.forEach(function (row) {{
            const key = row.dataset.clientid || 'SIN_CLIENTE';
            row.querySelector('.total-balance').textContent = money(groups[key].total);
        }});
        const descending = orderFilter.value === 'DESC';
        visible.slice().sort(function (left, right) {{ return compareRows(left, right, descending); }}).forEach(function (row) {{ tbody.appendChild(row); }});
        tbody.appendChild(noResults);
        rows.forEach(function (row) {{ row.hidden = !visible.includes(row); }});
        noResults.style.display = visible.length ? 'none' : 'table-row';
        const haber = visible.reduce(function (sum, row) {{ return sum + numeric(row.dataset.haber); }}, 0);
        const debe = visible.reduce(function (sum, row) {{ return sum + numeric(row.dataset.debe); }}, 0);
        const clients = new Set(visible.map(function (row) {{ return row.dataset.clientid || 'SIN_CLIENTE'; }}));
        document.getElementById('card-records').textContent = count(visible.length);
        document.getElementById('card-clients').textContent = count(clients.size);
        document.getElementById('card-haber').textContent = money(haber);
        document.getElementById('card-debe').textContent = money(debe);
        document.getElementById('card-saldo').textContent = money(haber - debe);
        const period = yearFilter.value
            ? 'Año ' + yearFilter.value
            : ((dateFrom.value || dateTo.value) ? (dateFrom.value || 'inicio') + ' a ' + (dateTo.value || 'fin') : 'Todos los años');
        document.getElementById('date-summary').textContent = period + ' | ' + count(visible.length) + ' registros | ' + count(clients.size) + ' clientes | Saldo: ' + money(haber - debe);
        document.getElementById('detail-summary').textContent = 'Se muestran ' + count(visible.length) + ' registros que componen el saldo del filtro seleccionado.';
        renderClientSummary(visible);
    }}
    [clientFilter, referenceFilter, flowFilter, orderFilter].forEach(function (input) {{
        input.addEventListener('input', render);
        input.addEventListener('change', render);
    }});
    [dateFrom, dateTo].forEach(function (input) {{
        input.addEventListener('input', function () {{
            if (yearFilter.value) {{
                const year = yearFilter.value;
                if (dateFrom.value !== year + '-01-01' || dateTo.value !== year + '-12-31') yearFilter.value = '';
            }}
            render();
        }});
        input.addEventListener('change', function () {{
            if (yearFilter.value) {{
                const year = yearFilter.value;
                if (dateFrom.value !== year + '-01-01' || dateTo.value !== year + '-12-31') yearFilter.value = '';
            }}
            render();
        }});
    }});
    yearFilter.addEventListener('change', function () {{
        if (yearFilter.value) {{
            dateFrom.value = yearFilter.value + '-01-01';
            dateTo.value = yearFilter.value + '-12-31';
        }} else {{
            dateFrom.value = '';
            dateTo.value = '';
        }}
        render();
    }});
    document.getElementById('clear-filters').addEventListener('click', function () {{
        yearFilter.value = '';
        dateFrom.value = '';
        dateTo.value = '';
        clientFilter.value = '';
        referenceFilter.value = '';
        flowFilter.value = '';
        orderFilter.value = 'ASC';
        render();
    }});
    render();
}}());
</script>
<script src="assets/export_excel.js"></script>
</body>
</html>
"""

    output_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "reporte_cuenta_corriente.html")
    )
    with open(output_path, "w", encoding="utf-8") as report_file:
        report_file.write(html_content)

    print(f"Reporte generado: {output_path}")
    print(f"Registros: {integer(len(df))}")
    print(f"Clientes: {integer(client_count)}")
    print(f"Haber: {money(total_haber)}")
    print(f"Debe: {money(total_debe)}")
    print(f"Saldo: {money(total_saldo)}")
    return output_path


if __name__ == "__main__":
    generate_report()
