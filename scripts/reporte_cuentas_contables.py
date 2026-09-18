#!/usr/bin/env python3
"""Genera un reporte separado de cuentas contables asignadas a egresos."""

import html
import os
from datetime import date, datetime

import pandas as pd
import psycopg2


DB_CONFIG = {
    "host": os.getenv("AVANZIA_DB_HOST", "localhost"),
    "port": os.getenv("AVANZIA_DB_PORT", "5432"),
    "database": os.getenv("AVANZIA_DB_NAME", "va9000-avanzia"),
    "user": os.getenv("AVANZIA_DB_USER", "postgres"),
    "password": os.getenv("AVANZIA_DB_PASSWORD") or os.getenv("PGPASSWORD"),
}

FLOW_IDS = (10150, 10303, 11344, 11433, 11332)
FLOW_IDS_SQL = ", ".join(str(flow_id) for flow_id in FLOW_IDS)

QUERY_DETAIL = f"""
SELECT
    rc.id AS registrocab_id,
    rc.clientid,
    rc.clientname,
    rc.fecha,
    rc.referenciatexto,
    rc.flowid,
    flow.name AS flow_name,
    rc.cuentacontableid,
    account.name AS cuenta_contable,
    rc.totalprecio,
    rc.totalimpuestos
FROM test9000.registrocab rc
JOIN test9000.categorias flow ON flow.id = rc.flowid
LEFT JOIN test9000.categorias account ON account.id = rc.cuentacontableid
WHERE rc.flowid IN ({FLOW_IDS_SQL})
ORDER BY rc.fecha, rc.id;
"""

QUERY_ACCOUNT_SUMMARY = f"""
SELECT
    rc.cuentacontableid,
    COALESCE(account.name, 'SIN CUENTA CONTABLE') AS cuenta_contable,
    CASE
        WHEN rc.cuentacontableid IS NULL THEN 'Sin cuenta contable'
        ELSE 'Con cuenta contable'
    END AS estado_cuenta,
    COUNT(*) AS registros,
    COALESCE(SUM(rc.totalprecio), 0) AS monto_total,
    MIN(rc.fecha) AS primera_fecha,
    MAX(rc.fecha) AS ultima_fecha
FROM test9000.registrocab rc
LEFT JOIN test9000.categorias account ON account.id = rc.cuentacontableid
WHERE rc.flowid IN ({FLOW_IDS_SQL})
GROUP BY rc.cuentacontableid, account.name
ORDER BY rc.cuentacontableid NULLS LAST;
"""

QUERY_FLOW_SUMMARY = f"""
SELECT
    rc.flowid,
    flow.name AS flow_name,
    CASE
        WHEN rc.cuentacontableid IS NULL THEN 'Sin cuenta contable'
        ELSE 'Con cuenta contable'
    END AS estado_cuenta,
    COUNT(*) AS registros,
    COALESCE(SUM(rc.totalprecio), 0) AS monto_total
FROM test9000.registrocab rc
JOIN test9000.categorias flow ON flow.id = rc.flowid
WHERE rc.flowid IN ({FLOW_IDS_SQL})
GROUP BY rc.flowid, flow.name, estado_cuenta
ORDER BY rc.flowid, estado_cuenta;
"""

QUERY_ALL_ACCOUNTS = """
SELECT
    c.id,
    c.name,
    pa.name AS parent_name,
    ab.name AS abuelo_name
FROM test9000.categorias c
LEFT JOIN test9000.categorias pa ON c.parentid = pa.id
LEFT JOIN test9000.categorias ab ON pa.parentid = ab.id
WHERE c.grupo = 'cuentacontable'
  AND pa.parentid IS NOT NULL
ORDER BY c.id;
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


def clean_text(value):
    return " ".join(str(value).split())


def text(value, fallback="-"):
    if empty(value) or str(value).strip() == "":
        return fallback
    return html.escape(clean_text(value))


def attribute(value):
    if empty(value):
        return ""
    return html.escape(clean_text(value), quote=True)


def money(value):
    if empty(value):
        return "$0.00"
    return f"${float(value):,.2f}"


def integer(value):
    if empty(value):
        return "0"
    return f"{int(value):,}"


def identifier(value):
    if empty(value):
        return "-"
    return str(int(float(value)))


def account_key(value):
    if empty(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


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


def account_badge_class(status):
    if status == "Con cuenta contable":
        return "badge-assigned"
    return "badge-unassigned"


def build_account_rows(df):
    rows = []
    for _, row in df.iterrows():
        status = str(row["estado_cuenta"])
        rows.append(
            "<tr>"
            f"<td>{identifier(row['cuentacontableid'])}</td>"
            f"<td>{text(row['cuenta_contable'])}</td>"
            f"<td><span class=\"badge {account_badge_class(status)}\">{text(status)}</span></td>"
            f"<td>{integer(row['registros'])}</td>"
            f"<td class=\"currency\">{money(row['monto_total'])}</td>"
            f"<td>{display_date(row['primera_fecha'])}</td>"
            f"<td>{display_date(row['ultima_fecha'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_flow_rows(df):
    rows = []
    for _, row in df.iterrows():
        status = str(row["estado_cuenta"])
        rows.append(
            "<tr>"
            f"<td>{identifier(row['flowid'])}</td>"
            f"<td>{text(row['flow_name'])}</td>"
            f"<td><span class=\"badge {account_badge_class(status)}\">{text(status)}</span></td>"
            f"<td>{integer(row['registros'])}</td>"
            f"<td class=\"currency\">{money(row['monto_total'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_detail_rows(df):
    rows = []
    for _, row in df.iterrows():
        account_id = account_key(row["cuentacontableid"])
        account_name = "SIN CUENTA CONTABLE" if empty(row["cuenta_contable"]) else str(row["cuenta_contable"])
        status = "Sin cuenta contable" if not account_id else "Con cuenta contable"
        date_value = iso_date(row["fecha"])
        client_name = "" if empty(row["clientname"]) else str(row["clientname"])
        reference = "" if empty(row["referenciatexto"]) else str(row["referenciatexto"])
        flow_name = str(row["flow_name"])
        rows.append(
            f"<tr class=\"detail-row\" data-date=\"{attribute(date_value)}\" "
            f"data-accountid=\"{attribute(account_id)}\" "
            f"data-account=\"{attribute(account_name)}\" "
            f"data-status=\"{attribute(status)}\" "
            f"data-flow=\"{attribute(flow_name)}\" "
            f"data-clientname=\"{attribute(client_name)}\" "
            f"data-reference=\"{attribute(reference)}\" "
            f"data-amount=\"{attribute(row['totalprecio'])}\">"
            f"<td>{identifier(row['registrocab_id'])}</td>"
            f"<td>{display_date(row['fecha'])}</td>"
            f"<td>{text(row['clientname'])}</td>"
            f"<td>{text(row['referenciatexto'])}</td>"
            f"<td>{text(row['flow_name'])}</td>"
            f"<td>{identifier(row['cuentacontableid'])}</td>"
            f"<td>{text(row['cuenta_contable'], 'SIN CUENTA CONTABLE')}</td>"
            f"<td><span class=\"badge {account_badge_class(status)}\">{text(status)}</span></td>"
            f"<td class=\"currency\">{money(row['totalprecio'])}</td>"
            f"<td class=\"currency\">{money(row['totalimpuestos'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def option_rows(values):
    return "\n".join(
        f"<option value=\"{attribute(value)}\">{text(value)}</option>"
        for value in sorted(values)
    )


def build_account_options(df):
    rows = []
    for _, row in df.iterrows():
        label = f"{int(row['id'])} - {row['name']}"
        if not empty(row.get('parent_name')):
            label += f" ({row['parent_name']})"
        rows.append(
            f"<option value=\"{int(row['id'])}\">"
            f"{html.escape(label)}"
            f"</option>"
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
        print("Ejecutando consultas...")
        df_detail = read_query(connection, QUERY_DETAIL)
        df_accounts = read_query(connection, QUERY_ACCOUNT_SUMMARY)
        df_flows = read_query(connection, QUERY_FLOW_SUMMARY)
        df_all_accounts = read_query(connection, QUERY_ALL_ACCOUNTS)

    detail_html = build_detail_rows(df_detail)
    account_html = build_account_rows(df_accounts)
    flow_html = build_flow_rows(df_flows)
    flow_options = option_rows(df_detail["flow_name"].dropna().unique())
    all_account_options = build_account_options(df_all_accounts)

    total_records = len(df_detail)
    assigned = int(df_detail["cuentacontableid"].notna().sum())
    unassigned = total_records - assigned
    total_amount = df_detail["totalprecio"].fillna(0).sum()
    assigned_amount = df_detail.loc[df_detail["cuentacontableid"].notna(), "totalprecio"].fillna(0).sum()
    unassigned_amount = df_detail.loc[df_detail["cuentacontableid"].isna(), "totalprecio"].fillna(0).sum()
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte de Cuentas Contables - Egresos</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: Segoe UI, Tahoma, sans-serif; background: #f3f6f8; color: #263238; line-height: 1.45; }}
        .container {{ max-width: 1550px; margin: auto; padding: 20px; }}
        header {{ padding: 30px; margin-bottom: 24px; border-radius: 12px; color: white; background: linear-gradient(135deg, #17324d, #167d9a); box-shadow: 0 5px 16px #183b4d22; }}
        h1 {{ margin: 0 0 8px; font-size: 2.2rem; }}
        h2 {{ margin: 0 0 18px; color: #17324d; border-bottom: 2px solid #23a6b8; padding-bottom: 8px; }}
        .subtitle {{ margin: 3px 0; opacity: .9; }}
        .section {{ background: white; padding: 24px; margin-bottom: 24px; border-radius: 12px; box-shadow: 0 2px 9px #183b4d14; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 16px 0; }}
        .summary-card {{ padding: 18px; border-radius: 10px; color: white; background: linear-gradient(135deg, #167d9a, #21a9ae); }}
        .summary-card.green {{ background: linear-gradient(135deg, #1f7a5a, #35aa78); }}
        .summary-card.orange {{ background: linear-gradient(135deg, #c87923, #e6a23c); }}
        .summary-card.red {{ background: linear-gradient(135deg, #a94442, #d66b62); }}
        .summary-card h3 {{ margin: 0 0 4px; color: white; font-size: 1.55rem; }}
        .summary-card p {{ margin: 0; opacity: .9; }}
        table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #dce4e8; vertical-align: top; }}
        th {{ position: sticky; top: 0; z-index: 1; color: white; background: #167d9a; }}
        tbody tr:nth-child(even) {{ background: #f8fafb; }}
        tbody tr:hover {{ background: #e5f4f6; }}
        .total-row {{ background: #e6f3f4 !important; }}
        .currency {{ text-align: right; white-space: nowrap; font-family: Consolas, monospace; }}
        .badge {{ display: inline-block; padding: 3px 9px; border-radius: 999px; color: white; font-size: .8rem; font-weight: 600; white-space: nowrap; }}
        .badge-assigned {{ background: #218653; }}
        .badge-unassigned {{ background: #a94442; }}
        .badge-pending {{ background: #c87923; }}
        .table-wrap {{ max-height: 660px; overflow: auto; border: 1px solid #dce4e8; border-radius: 7px; }}
        .filters {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; padding: 14px; margin: 15px 0; background: #eef5f7; border: 1px solid #d5e5e9; border-radius: 8px; }}
        .filters label {{ display: flex; flex-direction: column; gap: 4px; color: #36515e; font-size: .82rem; font-weight: 600; }}
        .filters input, .filters select, .filters button {{ min-height: 36px; padding: 7px 9px; border: 1px solid #b9cbd1; border-radius: 5px; background: white; font: inherit; }}
        .filters button {{ align-self: end; cursor: pointer; color: white; background: #24536b; border-color: #24536b; font-weight: 600; }}
        .filters button:disabled {{ opacity: .55; cursor: not-allowed; }}
        .filters button.positive {{ background: #218653; border-color: #218653; }}
        .filters button.negative {{ background: #a94442; border-color: #a94442; }}
        .step-cards {{ display: flex; flex-direction: column; gap: 18px; margin: 18px 0; }}
        .step-card {{ border: 1px solid #d5e5e9; border-radius: 10px; overflow: hidden; background: white; }}
        .step-card-header {{ display: flex; align-items: center; gap: 12px; padding: 14px 18px; background: #eef5f7; border-bottom: 1px solid #d5e5e9; }}
        .step-number {{ display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 50%; color: white; background: #167d9a; font-weight: 700; font-size: .95rem; flex-shrink: 0; }}
        .step-card-header h4 {{ margin: 0; color: #17324d; font-size: 1rem; }}
        .step-card-header .step-desc {{ margin: 0; color: #506872; font-size: .82rem; font-weight: 400; }}
        .step-card-body {{ padding: 18px; }}
        .step-card-body.no-pad {{ padding: 0; }}
        .step-row {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }}
        .step-row > label {{ display: flex; flex-direction: column; gap: 4px; color: #36515e; font-size: .82rem; font-weight: 600; min-width: 220px; flex: 1; }}
        .step-row > label > select, .step-row > label > input {{ min-height: 40px; padding: 8px 10px; border: 1px solid #b9cbd1; border-radius: 6px; background: white; font: inherit; font-size: .9rem; }}
        .step-row > label > select {{ font-size: .85rem; }}
        .step-actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; padding-top: 14px; border-top: 1px solid #e8eff2; }}
        .step-actions.right {{ justify-content: flex-end; }}
        .btn {{ display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 16px; border: 1px solid transparent; border-radius: 6px; cursor: pointer; font: inherit; font-size: .85rem; font-weight: 600; white-space: nowrap; text-decoration: none; }}
        .btn:disabled {{ opacity: .5; cursor: not-allowed; }}
        .btn-primary {{ background: #167d9a; border-color: #167d9a; color: white; }}
        .btn-primary:hover:not(:disabled) {{ background: #126579; }}
        .btn-success {{ background: #218653; border-color: #218653; color: white; }}
        .btn-success:hover:not(:disabled) {{ background: #1a6b43; }}
        .btn-danger {{ background: #a94442; border-color: #a94442; color: white; }}
        .btn-danger:hover:not(:disabled) {{ background: #8c3635; }}
        .btn-outline {{ background: white; border-color: #b9cbd1; color: #36515e; }}
        .btn-outline:hover:not(:disabled) {{ background: #f0f6f8; border-color: #8aa3ac; }}
        .btn-outline.green {{ border-color: #218653; color: #1a6b43; }}
        .btn-outline.green:hover:not(:disabled) {{ background: #eaf6ef; }}
        .btn-sm {{ padding: 6px 12px; font-size: .8rem; }}
        .batch-cards {{ display: flex; flex-direction: column; gap: 8px; }}
        .batch-card {{ display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: #f7fafb; border: 1px solid #d5e5e9; border-radius: 8px; font-size: .88rem; }}
        .batch-card .batch-num {{ display: flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 50%; background: #167d9a; color: white; font-size: .78rem; font-weight: 700; flex-shrink: 0; }}
        .batch-card .batch-info {{ flex: 1; }}
        .batch-card .batch-info strong {{ color: #17324d; }}
        .batch-card .batch-info .batch-count {{ color: #506872; font-size: .82rem; }}
        .batch-empty {{ color: #8aa3ac; font-style: italic; padding: 10px 14px; }}
        .assignment-feedback {{ color: #1b5e20; font-weight: 600; min-height: 1.2em; padding: 8px 0; font-size: .9rem; }}
        .assignment-feedback.error {{ color: #a94442; }}
        .filter-summary {{ margin: 10px 0; color: #36515e; font-weight: 600; }}
        .empty-row {{ display: none; }}
        details {{ margin: 10px 0; border: 1px solid #dce4e8; border-radius: 6px; }}
        summary {{ padding: 10px 12px; cursor: pointer; color: #24536b; font-weight: 600; }}
        .query-box {{ margin: 0; padding: 15px; overflow: auto; color: #eaf6f7; background: #17232d; font: .78rem Consolas, monospace; white-space: pre-wrap; }}
        footer {{ padding: 18px; text-align: center; color: #60747d; font-size: .85rem; }}
        @media (max-width: 700px) {{ .container {{ padding: 10px; }} header, .section {{ padding: 16px; }} h1 {{ font-size: 1.7rem; }} th, td {{ padding: 8px; }} }}
    </style>
</head>
<body>
<div class="container">
    <header>
        <h1>REPORTE DE CUENTAS CONTABLES</h1>
        <p class="subtitle">Egresos de proveedores y flujos relacionados</p>
        <p class="subtitle">Flujos: 10150, 10303, 11344, 11433 y 11332</p>
        <p class="subtitle">Generado: {generated_at}</p>
    </header>

    <section class="section">
        <h2>Resumen</h2>
        <div class="summary-grid">
            <div class="summary-card green"><h3 id="card-total">{integer(total_records)}</h3><p>Registros</p></div>
            <div class="summary-card"><h3 id="card-total-amount">{money(total_amount)}</h3><p>Monto total</p></div>
            <div class="summary-card orange"><h3 id="card-assigned">{integer(assigned)}</h3><p>Con cuenta contable</p></div>
            <div class="summary-card red"><h3 id="card-unassigned">{integer(unassigned)}</h3><p>Sin cuenta contable</p></div>
        </div>
        <p id="date-summary" class="filter-summary"></p>
    </section>

    <section class="section">
        <h2>Total por Cuenta Contable</h2>
        <p>El total se recalcula según el rango de fechas seleccionado en <strong>Registros Involucrados</strong>. La fila <strong>SIN CUENTA CONTABLE</strong> identifica registros sin <code>cuentacontableid</code>.</p>
        <div class="table-wrap"><table id="account-summary-table" data-excel-table data-excel-title="Total por Cuenta Contable" data-excel-all-source="account-summary-all-table">
            <thead><tr><th>cuentacontableid</th><th>cuenta contable</th><th>estado</th><th>registros</th><th>total</th><th>primera fecha</th><th>última fecha</th></tr></thead>
            <tbody id="account-summary-body">{account_html}</tbody>
        </table><table id="account-summary-all-table" style="display:none">
            <thead><tr><th>cuentacontableid</th><th>cuenta contable</th><th>estado</th><th>registros</th><th>total</th><th>primera fecha</th><th>última fecha</th></tr></thead>
            <tbody>{account_html}</tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Registros Involucrados</h2>
        <p id="detail-summary" class="filter-summary"></p>
        <div id="asignacion-masiva">
            <div class="step-cards">
                <div class="step-card">
                    <div class="step-card-header">
                        <div class="step-number">1</div>
                        <div>
                            <h4>Filtrar y seleccionar registros</h4>
                            <p class="step-desc">Use los filtros para localizar registros pendientes, elegir la cuenta y armar lotes</p>
                        </div>
                    </div>
                    <div class="step-card-body">
                        <div class="step-row">
                            <label>Fecha desde
                                <input id="date-from" type="date">
                            </label>
                            <label>Fecha hasta
                                <input id="date-to" type="date">
                            </label>
                            <label>Estado
                                <select id="status-filter"><option value="">Todos</option><option value="Sin cuenta contable">Sin cuenta contable</option><option value="Con cuenta contable">Con cuenta contable</option></select>
                            </label>
                            <label>Flujo
                                <select id="flow-filter"><option value="">Todos</option>{flow_options}</select>
                            </label>
                            <label>clientname
                                <input id="client-filter" type="search" placeholder="Nombre del perfil">
                            </label>
                            <label>Referencia
                                <input id="reference-filter" type="search" placeholder="Texto de referencia">
                            </label>
                        </div>
                        <div class="step-actions">
                            <button id="clear-date-filters" type="button" class="btn btn-outline btn-sm">Limpiar filtros</button>
                            <span style="flex:1"></span>
                            <button id="assign-select-all" type="button" class="btn btn-primary">Seleccionar todos los visibles</button>
                            <button id="assign-clear-selection" type="button" class="btn btn-outline">Quitar selección</button>
                        </div>
                        <p id="assign-summary" class="filter-summary"></p>
                        <div class="step-row" style="margin-top:14px; border-top:1px solid #e8eff2; padding-top:14px;">
                            <label>Cuenta contable a asignar
                                <select id="assign-account-select">
                                    <option value="">-- Elegir cuenta para los registros seleccionados --</option>
                                    {all_account_options}
                                </select>
                            </label>
                        </div>
                        <div class="step-actions">
                            <button id="assign-btn" type="button" class="btn btn-success" disabled>Agregar lote seleccionado</button>
                        </div>
                        <p id="assign-feedback" class="assignment-feedback" role="status"></p>
                    </div>
                </div>

                <div class="step-card">
                    <div class="step-card-header">
                        <div class="step-number">2</div>
                        <div>
                            <h4>Lotes preparados</h4>
                            <p class="step-desc">Revise los lotes, deshaga si es necesario y descargue el SQL</p>
                        </div>
                    </div>
                    <div class="step-card-body">
                        <div id="batch-list" class="batch-cards"><p class="batch-empty">Sin lotes preparados.</p></div>
                        <div class="step-actions">
                            <button id="assign-undo" type="button" class="btn btn-outline btn-sm">Deshacer último lote</button>
                            <button id="clear-assign-btn" type="button" class="btn btn-danger btn-sm">Deshacer todos</button>
                            <span style="flex:1"></span>
                            <button id="assign-copy" type="button" class="btn btn-primary btn-sm">Copiar SQL</button>
                            <button id="assign-download" type="button" class="btn btn-success btn-sm">Descargar SQL</button>
                        </div>
                    </div>
                </div>
            </div>
            <details open>
                <summary>SQL acumulado</summary>
                <pre id="sql-output" class="query-box">-- Todavía no hay lotes preparados. Seleccione registros y agregue el primer lote.</pre>
            </details>
        </div>
        <div class="table-wrap"><table id="detail-table" data-excel-table data-excel-title="Registros Involucrados">
            <thead><tr><th>registrocab</th><th>fecha</th><th>clientname</th><th>referencia</th><th>flujo</th><th>cuentacontableid</th><th>cuenta contable</th><th>estado</th><th>totalprecio</th><th>impuestos</th></tr></thead>
            <tbody>{detail_html}<tr id="no-results" class="empty-row"><td colspan="10">No hay registros para los filtros seleccionados.</td></tr></tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Resumen por Flujo y Asignación</h2>
        <div class="table-wrap"><table id="flow-summary-table" data-excel-table data-excel-title="Resumen por Flujo y Asignacion" data-excel-all-source="flow-summary-all-table">
            <thead><tr><th>flowid</th><th>flujo</th><th>estado</th><th>registros</th><th>total</th></tr></thead>
            <tbody id="flow-summary-body">{flow_html}</tbody>
        </table><table id="flow-summary-all-table" style="display:none">
            <thead><tr><th>flowid</th><th>flujo</th><th>estado</th><th>registros</th><th>total</th></tr></thead>
            <tbody>{flow_html}</tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Consultas Utilizadas</h2>
        {query_block("1. Registros de los flujos", QUERY_DETAIL)}
        {query_block("2. Total por cuenta contable", QUERY_ACCOUNT_SUMMARY)}
        {query_block("3. Resumen por flujo y asignación", QUERY_FLOW_SUMMARY)}
    </section>

    <footer>Reporte generado automáticamente | Base: va9000-avanzia | Schema: test9000</footer>
</div>
<script>
(function () {{
    const rows = Array.from(document.querySelectorAll('#detail-table .detail-row'));
    const dateFrom = document.getElementById('date-from');
    const dateTo = document.getElementById('date-to');
    const statusFilter = document.getElementById('status-filter');
    const flowFilter = document.getElementById('flow-filter');
    const clientFilter = document.getElementById('client-filter');
    const referenceFilter = document.getElementById('reference-filter');
    const accountBody = document.getElementById('account-summary-body');
    const flowBody = document.getElementById('flow-summary-body');
    const detailSummary = document.getElementById('detail-summary');
    const noResults = document.getElementById('no-results');

    function money(value) {{
        return new Intl.NumberFormat('es-AR', {{ style: 'currency', currency: 'ARS' }}).format(value);
    }}

    function count(value) {{
        return Number(value || 0).toLocaleString('es-AR');
    }}

    function escapeHtml(value) {{
        const entities = {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }};
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {{ return entities[character]; }});
    }}

    function inDateRange(value) {{
        if (!dateFrom.value && !dateTo.value) return true;
        if (!value) return false;
        return (!dateFrom.value || value >= dateFrom.value) && (!dateTo.value || value <= dateTo.value);
    }}

    function displayDate(value) {{
        if (!value) return '-';
        const parts = value.split('-');
        return parts.length === 3 ? parts[2] + '/' + parts[1] + '/' + parts[0] : value;
    }}

    function statusClass(status) {{
        return status === 'Con cuenta contable' ? 'badge-assigned' : 'badge-unassigned';
    }}

    function setSummary(total, assigned, totalAmount) {{
        const unassigned = total - assigned;
        const unassignedAmount = rows.reduce(function (sum, row) {{
            return inDateRange(row.dataset.date) && !row.dataset.accountid ? sum + Number(row.dataset.amount || 0) : sum;
        }}, 0);
        document.getElementById('card-total').textContent = count(total);
        document.getElementById('card-assigned').textContent = count(assigned);
        document.getElementById('card-unassigned').textContent = count(unassigned);
        document.getElementById('card-total-amount').textContent = money(totalAmount);
        document.getElementById('date-summary').textContent = count(total) + ' registros | Con cuenta: ' + count(assigned) + ' | Sin cuenta: ' + count(unassigned) + ' | Total sin cuenta: ' + money(unassignedAmount);
    }}

    function renderAccountSummary() {{
        const groups = {{}};
        let total = 0;
        let assigned = 0;
        let totalAmount = 0;
        rows.forEach(function (row) {{
            if (!inDateRange(row.dataset.date)) return;
            const key = row.dataset.accountid || 'SIN_CUENTA';
            if (!groups[key]) {{
                groups[key] = {{
                    id: row.dataset.accountid,
                    name: row.dataset.account,
                    status: row.dataset.status,
                    count: 0,
                    amount: 0,
                    firstDate: row.dataset.date,
                    lastDate: row.dataset.date
                }};
            }}
            const group = groups[key];
            group.count += 1;
            group.amount += Number(row.dataset.amount || 0);
            if (row.dataset.date && (!group.firstDate || row.dataset.date < group.firstDate)) group.firstDate = row.dataset.date;
            if (row.dataset.date && (!group.lastDate || row.dataset.date > group.lastDate)) group.lastDate = row.dataset.date;
            total += 1;
            totalAmount += Number(row.dataset.amount || 0);
            if (row.dataset.accountid) assigned += 1;
        }});

        const ordered = Object.values(groups).sort(function (left, right) {{
            if (!left.id) return 1;
            if (!right.id) return -1;
            return right.amount - left.amount;
        }});
        let body = '';
        ordered.forEach(function (group) {{
            body += '<tr>'
                + '<td>' + escapeHtml(group.id || '-') + '</td>'
                + '<td>' + escapeHtml(group.name) + '</td>'
                + '<td><span class="badge ' + statusClass(group.status) + '">' + escapeHtml(group.status) + '</span></td>'
                + '<td>' + count(group.count) + '</td>'
                + '<td class="currency">' + money(group.amount) + '</td>'
                + '<td>' + displayDate(group.firstDate) + '</td>'
                + '<td>' + displayDate(group.lastDate) + '</td>'
                + '</tr>';
        }});
        accountBody.innerHTML = body;
        setSummary(total, assigned, totalAmount);
    }}

    function renderFlowSummary() {{
        const groups = {{}};
        rows.forEach(function (row) {{
            if (!inDateRange(row.dataset.date)) return;
            const key = row.dataset.flow + '|' + row.dataset.status;
            if (!groups[key]) groups[key] = {{ flow: row.dataset.flow, status: row.dataset.status, count: 0, amount: 0 }};
            groups[key].count += 1;
            groups[key].amount += Number(row.dataset.amount || 0);
        }});
        let body = '';
        Object.values(groups).forEach(function (group) {{
            body += '<tr>'
                + '<td>-</td><td>' + escapeHtml(group.flow) + '</td>'
                + '<td><span class="badge ' + statusClass(group.status) + '">' + escapeHtml(group.status) + '</span></td>'
                + '<td>' + count(group.count) + '</td><td class="currency">' + money(group.amount) + '</td></tr>';
        }});
        flowBody.innerHTML = body;
    }}

    function applyDetailFilters() {{
        const status = statusFilter.value.toLowerCase();
        const flow = flowFilter.value.toLowerCase();
        const client = clientFilter.value.trim().toLowerCase();
        const reference = referenceFilter.value.trim().toLowerCase();
        let visible = 0;
        let amount = 0;
        rows.forEach(function (row) {{
            const matches = inDateRange(row.dataset.date)
                && (!status || row.dataset.status.toLowerCase() === status)
                && (!flow || row.dataset.flow.toLowerCase() === flow)
                && (!client || row.dataset.clientname.toLowerCase().includes(client))
                && (!reference || row.dataset.reference.toLowerCase().includes(reference));
            row.hidden = !matches;
            if (matches) {{ visible += 1; amount += Number(row.dataset.amount || 0); }}
        }});
        noResults.style.display = visible ? 'none' : 'table-row';
        detailSummary.textContent = count(visible) + ' registros visibles | Total filtrado: ' + money(amount);
    }}

    [dateFrom, dateTo].forEach(function (input) {{
        input.addEventListener('input', function () {{ renderAccountSummary(); renderFlowSummary(); applyDetailFilters(); }});
        input.addEventListener('change', function () {{ renderAccountSummary(); renderFlowSummary(); applyDetailFilters(); }});
    }});
    [statusFilter, flowFilter, clientFilter, referenceFilter].forEach(function (input) {{
        input.addEventListener('input', applyDetailFilters);
        input.addEventListener('change', applyDetailFilters);
    }});
    document.getElementById('clear-date-filters').addEventListener('click', function () {{
        dateFrom.value = ''; dateTo.value = '';
        statusFilter.value = ''; flowFilter.value = '';
        clientFilter.value = ''; referenceFilter.value = '';
        renderAccountSummary(); renderFlowSummary(); applyDetailFilters();
    }});

    window.refreshAccountReport = function () {{
        renderAccountSummary(); renderFlowSummary(); applyDetailFilters();
    }};
    window.refreshAccountReport();
}}());
</script>
<script src="assets/asignacion_cuentas.js"></script>
<script src="assets/export_excel.js"></script>
</body>
</html>
"""

    output_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "reporte_cuentas_contables.html")
    )
    with open(output_path, "w", encoding="utf-8") as report_file:
        report_file.write(html_content)

    print(f"Reporte generado: {output_path}")
    print(f"Registros: {integer(total_records)}")
    print(f"Con cuenta contable: {integer(assigned)}")
    print(f"Sin cuenta contable: {integer(unassigned)}")
    return output_path


if __name__ == "__main__":
    generate_report()
