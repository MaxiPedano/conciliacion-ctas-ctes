#!/usr/bin/env python3
"""Genera el reporte HTML de egresos y perfiles de proveedores."""

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

FLOW_IDS = (10150, 10303, 11344, 11433, 11332)
FLOW_IDS_SQL = ", ".join(str(flow_id) for flow_id in FLOW_IDS)
FLOW_ORDER = {
    "CAJA: Egresos": 0,
    "Comprobantes Proveedores": 1,
    "CAJA: Egresos Juan": 2,
    "CAJA: Egresos Juan sin Cta. Cte.": 3,
    "CAJA: Egresos sin cta cte": 4,
}
PROFILE_ORDER = {
    "Proveedor": 0,
    "Empleado": 1,
    "Socios": 2,
    "Vendedor": 3,
    "Cliente": 4,
    "Ente Recaudador": 5,
    "Sin clasificar": 6,
}

# La prioridad reproduce la clasificación investigada: un perfil puede tener
# varias categorías, por eso se evalúan las categorías y sus padres una sola vez.
PROFILE_TYPE_CASE = """
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
END
""".strip()

QUERY_CLASIFICACION = f"""
WITH clasificados AS (
    SELECT
        {PROFILE_TYPE_CASE} AS perfil_tipo,
        cat.name AS flow_name,
        rc.totalprecio
    FROM test9000.registrocab rc
    JOIN test9000.categorias cat ON cat.id = rc.flowid
    WHERE rc.flowid IN ({FLOW_IDS_SQL})
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
"""

QUERY_DETALLE = f"""
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
    {PROFILE_TYPE_CASE} AS perfil_tipo
FROM test9000.registrocab rc
JOIN test9000.categorias cat ON cat.id = rc.flowid
LEFT JOIN test9000.perfiles p ON p.id = rc.clientid
    WHERE rc.flowid IN ({FLOW_IDS_SQL})
  AND rc.clientid IS NOT NULL
ORDER BY perfil_tipo, rc.clientname, rc.fecha, rc.id;
"""

QUERY_RESUELTOS = f"""
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
WHERE rc.flowid IN ({FLOW_IDS_SQL})
GROUP BY i.clientid, i.clientname, i.tipo_detectado
ORDER BY i.clientid;
"""

QUERY_SIN_CLIENTID = f"""
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
WHERE rc.flowid IN ({FLOW_IDS_SQL})
  AND rc.clientid IS NULL
ORDER BY rc.fecha, rc.id;
"""

QUERY_RESUMEN_PERFILES = f"""
WITH clasificados AS (
    SELECT
        rc.clientid,
        rc.clientname,
        p.razonsocial,
        rc.fecha,
        rc.totalprecio,
        {PROFILE_TYPE_CASE} AS perfil_tipo
    FROM test9000.registrocab rc
    LEFT JOIN test9000.perfiles p ON p.id = rc.clientid
    WHERE rc.flowid IN ({FLOW_IDS_SQL})
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
"""


def read_query(connection, query):
    """Ejecuta una consulta y devuelve un DataFrame sin depender de SQLAlchemy."""
    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
    return pd.DataFrame(rows, columns=columns)


def value_is_empty(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def clean_text(value):
    return " ".join(str(value).split())


def display_text(value, fallback="-"):
    if value_is_empty(value) or str(value).strip() == "":
        return fallback
    return html.escape(clean_text(value))


def display_attribute(value):
    if value_is_empty(value):
        return ""
    return html.escape(clean_text(value), quote=True)


def format_currency(value):
    if value_is_empty(value):
        return "$0.00"
    return f"${float(value):,.2f}"


def format_integer(value):
    if value_is_empty(value):
        return "0"
    return f"{int(value):,}"


def format_id(value):
    if value_is_empty(value):
        return "-"
    return str(int(float(value)))


def format_date(value):
    if value_is_empty(value):
        return "-"
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%Y")
    return display_text(value)


def iso_date(value):
    if value_is_empty(value):
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def badge_class(profile_type):
    names = {
        "Proveedor": "badge-proveedor",
        "Empleado": "badge-empleado",
        "Vendedor": "badge-vendedor",
        "Cliente": "badge-cliente",
        "Socios": "badge-socios",
        "Ente Recaudador": "badge-ente",
        "Sin clasificar": "badge-sin-clasificar",
    }
    return names.get(str(profile_type), "badge-default")


def build_classification_rows(df):
    rows = []
    for _, row in df.iterrows():
        rows.append(
            "<tr>"
            f"<td><span class=\"badge {badge_class(row['perfil_tipo'])}\">"
            f"{display_text(row['perfil_tipo'])}</span></td>"
            f"<td>{display_text(row['flow_name'])}</td>"
            f"<td>{format_integer(row['registros'])}</td>"
            f"<td class=\"currency\">{format_currency(row['total_monto'])}</td>"
            "</tr>"
        )
    total_records = df["registros"].sum() if not df.empty else 0
    total_amount = df["total_monto"].sum() if not df.empty else 0
    rows.append(
        "<tr class=\"total-row\">"
        "<td colspan=\"2\"><strong>Total</strong></td>"
        f"<td><strong>{format_integer(total_records)}</strong></td>"
        f"<td class=\"currency\"><strong>{format_currency(total_amount)}</strong></td>"
        "</tr>"
    )
    return "\n".join(rows), total_records, total_amount


def build_resolved_rows(df):
    rows = []
    for _, row in df.iterrows():
        rows.append(
            "<tr>"
            f"<td>{format_integer(row['clientid'])}</td>"
            f"<td>{display_text(row['clientname'])}</td>"
            f"<td>{format_integer(row['registros'])}</td>"
            f"<td>{display_text(row['tipo_detectado'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_profile_rows(df):
    rows = []
    for _, row in df.iterrows():
        rows.append(
            "<tr>"
            f"<td>{format_integer(row['clientid'])}</td>"
            f"<td>{display_text(row['clientname'])}</td>"
            f"<td>{display_text(row['razonsocial'])}</td>"
            f"<td><span class=\"badge {badge_class(row['perfil_tipo'])}\">"
            f"{display_text(row['perfil_tipo'])}</span></td>"
            f"<td>{format_integer(row['total_registros'])}</td>"
            f"<td class=\"currency\">{format_currency(row['monto_total'])}</td>"
            f"<td>{format_date(row['primera_fecha'])}</td>"
            f"<td>{format_date(row['ultima_fecha'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_detail_rows(df):
    rows = []
    for _, row in df.iterrows():
        client_name = row["clientname"]
        if value_is_empty(client_name):
            client_name = row["razonsocial"]
        name_for_search = " ".join(
            str(value)
            for value in (row["clientname"], row["razonsocial"], row["nombre"], row["apellido"])
            if not value_is_empty(value)
        )
        reference = "" if value_is_empty(row["referenciatexto"]) else str(row["referenciatexto"])
        client_name_value = "" if value_is_empty(row["clientname"]) else str(row["clientname"])
        company_value = "" if value_is_empty(row["razonsocial"]) else str(row["razonsocial"])
        flow_name = str(row["flow_name"])
        profile_type = str(row["perfil_tipo"])
        date_value = iso_date(row["fecha"])
        rows.append(
            f"<tr class=\"detail-row\" data-id=\"{display_attribute(row['registrocab_id'])}\" "
            f"data-clientid=\"{display_attribute(row['clientid'])}\" "
            f"data-name=\"{display_attribute(name_for_search)}\" "
            f"data-clientname=\"{display_attribute(client_name_value)}\" "
            f"data-razonsocial=\"{display_attribute(company_value)}\" "
            f"data-reference=\"{display_attribute(reference)}\" "
            f"data-flow=\"{display_attribute(flow_name)}\" "
            f"data-type=\"{display_attribute(profile_type)}\" "
            f"data-date=\"{display_attribute(date_value)}\" "
            f"data-amount=\"{display_attribute(row['totalprecio'])}\">"
            f"<td>{format_integer(row['registrocab_id'])}</td>"
            f"<td>{format_integer(row['clientid'])}</td>"
            f"<td>{display_text(client_name)}</td>"
            f"<td>{format_date(row['fecha'])}</td>"
            f"<td>{display_text(row['referenciatexto'])}</td>"
            f"<td>{display_text(row['flow_name'])}</td>"
            f"<td class=\"currency\">{format_currency(row['totalprecio'])}</td>"
            f"<td class=\"currency\">{format_currency(row['totalimpuestos'])}</td>"
            f"<td><span class=\"badge {badge_class(profile_type)}\">"
            f"{display_text(profile_type)}</span></td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_unassigned_rows(df):
    rows = []
    for _, row in df.iterrows():
        rows.append(
            "<tr>"
            f"<td>{format_integer(row['registrocab_id'])}</td>"
            f"<td>{format_date(row['fecha'])}</td>"
            f"<td>{display_text(row['referenciatexto'])}</td>"
            f"<td>{format_id(row['flowid'])}</td>"
            f"<td>{display_text(row['flow_name'])}</td>"
            f"<td class=\"currency\">{format_currency(row['totalprecio'])}</td>"
            f"<td class=\"currency\">{format_currency(row['totalimpuestos'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def option_rows(values):
    return "\n".join(
        f"<option value=\"{display_attribute(value)}\">{display_text(value)}</option>"
        for value in sorted(values)
    )


def query_block(title, query):
    return (
        f"<details><summary>{html.escape(title)}</summary>"
        f"<pre class=\"query-box\">{html.escape(query.strip())}</pre></details>"
    )


def generate_html_report():
    print("Conectando a la base de datos...")
    with psycopg2.connect(**DB_CONFIG) as connection:
        print("Ejecutando consultas...")
        df_clasificacion = read_query(connection, QUERY_CLASIFICACION)
        df_detalle = read_query(connection, QUERY_DETALLE)
        df_resueltos = read_query(connection, QUERY_RESUELTOS)
        df_sin_clientid = read_query(connection, QUERY_SIN_CLIENTID)
        df_perfiles = read_query(connection, QUERY_RESUMEN_PERFILES)

    df_clasificacion = df_clasificacion.assign(
        _order=df_clasificacion["perfil_tipo"].map(lambda value: PROFILE_ORDER.get(value, 999)),
        _flow_order=df_clasificacion["flow_name"].map(lambda value: FLOW_ORDER.get(value, 999)),
    ).sort_values(["_order", "_flow_order"])
    classification_html, total_records, total_amount = build_classification_rows(df_clasificacion)
    resolved_html = build_resolved_rows(df_resueltos)
    unassigned_html = build_unassigned_rows(df_sin_clientid)
    profile_html = build_profile_rows(df_perfiles)
    detail_html = build_detail_rows(df_detalle)

    provider_count = int(
        df_clasificacion.loc[df_clasificacion["perfil_tipo"] == "Proveedor", "registros"].sum()
    )
    employee_count = int(
        df_clasificacion.loc[df_clasificacion["perfil_tipo"] == "Empleado", "registros"].sum()
    )
    partners_count = int(
        df_clasificacion.loc[df_clasificacion["perfil_tipo"] == "Socios", "registros"].sum()
    )

    def percentage(count):
        return f"{(count / total_records * 100):.1f}%" if total_records else "0.0%"

    type_options = option_rows(df_detalle["perfil_tipo"].dropna().unique())
    flow_options = option_rows(df_detalle["flow_name"].dropna().unique())
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte de Investigación - Egresos y Perfiles</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: Segoe UI, Tahoma, sans-serif; background: #f3f6f8; color: #263238; line-height: 1.45; }}
        .container {{ max-width: 1500px; margin: auto; padding: 20px; }}
        header {{ padding: 30px; margin-bottom: 24px; border-radius: 12px; color: white; background: linear-gradient(135deg, #17324d, #167d9a); box-shadow: 0 5px 16px #183b4d22; }}
        h1 {{ margin: 0 0 8px; font-size: 2.2rem; }}
        h2 {{ margin: 0 0 18px; color: #17324d; border-bottom: 2px solid #23a6b8; padding-bottom: 8px; }}
        h3 {{ color: #24536b; margin: 18px 0 8px; }}
        .subtitle {{ margin: 3px 0; opacity: .9; }}
        .section {{ background: white; padding: 24px; margin-bottom: 24px; border-radius: 12px; box-shadow: 0 2px 9px #183b4d14; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 16px 0; }}
        .summary-card {{ padding: 18px; border-radius: 10px; color: white; background: linear-gradient(135deg, #167d9a, #21a9ae); }}
        .summary-card.green {{ background: linear-gradient(135deg, #1f7a5a, #35aa78); }}
        .summary-card.orange {{ background: linear-gradient(135deg, #c87923, #e6a23c); }}
        .summary-card h3 {{ margin: 0 0 4px; color: white; font-size: 1.65rem; }}
        .summary-card p {{ margin: 0; opacity: .9; }}
        .conclusion {{ padding: 16px 20px; border-left: 5px solid #1f7a5a; background: #edf8f1; border-radius: 6px; }}
        .conclusion ul {{ margin: 8px 0 0; }}
        table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #dce4e8; vertical-align: top; }}
        th {{ position: sticky; top: 0; z-index: 1; color: white; background: #167d9a; }}
        tbody tr:nth-child(even) {{ background: #f8fafb; }}
        tbody tr:hover {{ background: #e5f4f6; }}
        .total-row {{ background: #e6f3f4 !important; }}
        .currency {{ text-align: right; white-space: nowrap; font-family: Consolas, monospace; }}
        .badge {{ display: inline-block; padding: 3px 9px; border-radius: 999px; color: white; font-size: .8rem; font-weight: 600; white-space: nowrap; }}
        .badge-proveedor {{ background: #218653; }} .badge-empleado {{ background: #c97922; }}
        .badge-vendedor {{ background: #8252a8; }} .badge-cliente {{ background: #75838b; }}
        .badge-socios {{ background: #267da8; }} .badge-ente {{ background: #159a88; }}
        .badge-sin-clasificar, .badge-default {{ background: #68747b; }}
        .table-wrap {{ max-height: 660px; overflow: auto; border: 1px solid #dce4e8; border-radius: 7px; }}
        .filters {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; padding: 14px; margin: 15px 0; background: #eef5f7; border: 1px solid #d5e5e9; border-radius: 8px; }}
        .filters label {{ display: flex; flex-direction: column; gap: 4px; color: #36515e; font-size: .82rem; font-weight: 600; }}
        .filters input, .filters select, .filters button {{ min-height: 36px; padding: 7px 9px; border: 1px solid #b9cbd1; border-radius: 5px; background: white; font: inherit; }}
        .filters button {{ align-self: end; cursor: pointer; color: white; background: #24536b; border-color: #24536b; font-weight: 600; }}
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
        <h1>REPORTE DE INVESTIGACIÓN</h1>
        <p class="subtitle">Egresos y perfiles de proveedores</p>
        <p class="subtitle">Flujos analizados: 10150, 10303, 11344, 11433 y 11332</p>
        <p class="subtitle">Generado: {generated_at}</p>
    </header>

    <section class="section">
        <h2>Resumen Ejecutivo</h2>
        <div class="summary-grid">
            <div class="summary-card green"><h3>{format_integer(total_records)}</h3><p>Total de registros</p></div>
            <div class="summary-card"><h3>{format_currency(total_amount)}</h3><p>Monto total</p></div>
            <div class="summary-card orange"><h3>{format_integer(len(df_perfiles))}</h3><p>Perfiles involucrados</p></div>
            <div class="summary-card"><h3>{format_integer(len(df_sin_clientid))}</h3><p>Sin clientid</p></div>
        </div>
    </section>

    <section class="section">
        <h2>1. Clasificación Final de Egresos (Proveedores)</h2>
        <div class="filters">
            <label>Desde
                <input id="classification-from" type="date">
            </label>
            <label>Hasta
                <input id="classification-to" type="date">
            </label>
            <button id="clear-classification-filters" type="button">Limpiar fechas</button>
        </div>
        <p id="classification-summary" class="filter-summary"></p>
        <div class="table-wrap"><table data-excel-table data-excel-title="Clasificacion Final de Egresos">
            <thead><tr><th>perfil_tipo</th><th>flow_name</th><th>registros</th><th>total_monto</th></tr></thead>
            <tbody id="classification-body">{classification_html}</tbody>
        </table></div>
        <p>Los montos se muestran con dos decimales, tomados directamente de <code>registrocab.totalprecio</code>.</p>
    </section>

    <section class="section">
        <h2>2. Registros Involucrados</h2>
        <p>Use los filtros para localizar cualquier <code>registrocab</code> por <code>clientname</code>, referencia, fecha, flujo, clientid o tipo de perfil.</p>
        <div class="filters">
            <label>clientname
                <input id="filter-clientname" type="search" placeholder="Nombre del perfil">
            </label>
            <label>Referencia
                <input id="filter-reference" type="search" placeholder="Texto de referencia">
            </label>
            <label>Client ID
                <input id="filter-clientid" type="search" placeholder="Ej. 1130">
            </label>
            <label>Tipo de perfil
                <select id="filter-type"><option value="">Todos</option>{type_options}</select>
            </label>
            <label>Flujo
                <select id="filter-flow"><option value="">Todos</option>{flow_options}</select>
            </label>
            <label>Desde
                <input id="filter-from" type="date">
            </label>
            <label>Hasta
                <input id="filter-to" type="date">
            </label>
            <button id="clear-filters" type="button">Limpiar filtros</button>
        </div>
        <p id="filter-summary" class="filter-summary"></p>
        <div class="table-wrap">
            <table id="detail-table" data-excel-table data-excel-title="Registros Involucrados">
                <thead><tr>
                    <th>registrocab</th><th>clientid</th><th>clientname</th><th>fecha</th>
                    <th>referencia</th><th>flujo</th><th>totalprecio</th><th>impuestos</th><th>perfil_tipo</th>
                </tr></thead>
                <tbody>
                    {detail_html}
                    <tr id="no-results" class="empty-row"><td colspan="9">No hay registros para los filtros seleccionados.</td></tr>
                </tbody>
            </table>
        </div>
    </section>

    <section class="section">
        <h2>3. Resumen por Perfil</h2>
        <div class="filters">
            <label>Desde
                <input id="profile-from" type="date">
            </label>
            <label>Hasta
                <input id="profile-to" type="date">
            </label>
            <button id="clear-profile-filters" type="button">Limpiar fechas</button>
        </div>
        <p id="profile-summary" class="filter-summary"></p>
        <div class="table-wrap"><table data-excel-table data-excel-title="Resumen por Perfil">
            <thead><tr><th>clientid</th><th>clientname</th><th>Razón Social</th><th>Tipo</th><th>Registros</th><th>Monto Total</th><th>Primera Fecha</th><th>Última Fecha</th></tr></thead>
            <tbody id="profile-summary-body">{profile_html}</tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Registros sin clientid</h2>
        <p>{format_integer(len(df_sin_clientid))} registros del flujo 11332 son transferencias internas de caja y no tienen proveedor asociado. Se muestran aquí, pero no se incluyen en la clasificación porcentual.</p>
        <div class="table-wrap"><table data-excel-table data-excel-title="Registros sin clientid">
            <thead><tr><th>registrocab</th><th>fecha</th><th>referencia</th><th>flowid</th><th>flujo</th><th>totalprecio</th><th>impuestos</th></tr></thead>
            <tbody>{unassigned_html}</tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Perfiles Sin Categoría (Resueltos)</h2>
        <p>Estos perfiles fueron investigados por el texto de sus referencias y quedaron identificados operacionalmente.</p>
        <div class="table-wrap"><table data-excel-table data-excel-title="Perfiles Sin Categoria Resueltos">
            <thead><tr><th>clientid</th><th>clientname</th><th>Registros</th><th>Tipo Detectado</th></tr></thead>
            <tbody>{resolved_html}</tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Conclusión</h2>
        <div class="conclusion">
            <p>Los registros clasificables de los cinco flujos analizados son legítimos y corresponden a:</p>
            <ul>
                <li><strong>Proveedores:</strong> {percentage(provider_count)} ({format_integer(provider_count)} registros)</li>
                <li><strong>Empleados:</strong> {percentage(employee_count)} ({format_integer(employee_count)} registros)</li>
                <li><strong>Socios:</strong> {percentage(partners_count)} ({format_integer(partners_count)} registros)</li>
            </ul>
        </div>
    </section>

    <section class="section">
        <h2>Consultas Utilizadas y Contexto</h2>
        {query_block("1. Clasificación Final", QUERY_CLASIFICACION)}
        {query_block("2. Registros involucrados", QUERY_DETALLE)}
        {query_block("3. Resumen por perfil", QUERY_RESUMEN_PERFILES)}
        {query_block("4. Perfiles sin categoría resueltos", QUERY_RESUELTOS)}
        {query_block("5. Registros sin clientid", QUERY_SIN_CLIENTID)}
    </section>

    <footer>
        Reporte generado automáticamente | Base: va9000-avanzia | Schema: test9000
    </footer>
</div>
<script>
(function () {{
    const rows = Array.from(document.querySelectorAll('#detail-table .detail-row'));
    const clientNameInput = document.getElementById('filter-clientname');
    const referenceInput = document.getElementById('filter-reference');
    const clientInput = document.getElementById('filter-clientid');
    const typeInput = document.getElementById('filter-type');
    const flowInput = document.getElementById('filter-flow');
    const fromInput = document.getElementById('filter-from');
    const toInput = document.getElementById('filter-to');
    const summary = document.getElementById('filter-summary');
    const noResults = document.getElementById('no-results');
    const classificationBody = document.getElementById('classification-body');
    const classificationSummary = document.getElementById('classification-summary');
    const classificationFrom = document.getElementById('classification-from');
    const classificationTo = document.getElementById('classification-to');
    const profileBody = document.getElementById('profile-summary-body');
    const profileSummary = document.getElementById('profile-summary');
    const profileFrom = document.getElementById('profile-from');
    const profileTo = document.getElementById('profile-to');

    const profileOrder = {{
        'Proveedor': 0, 'Empleado': 1, 'Socios': 2, 'Vendedor': 3,
        'Cliente': 4, 'Ente Recaudador': 5, 'Sin clasificar': 6
    }};
    const flowOrder = {{
        'CAJA: Egresos': 0,
        'Comprobantes Proveedores': 1,
        'CAJA: Egresos Juan': 2,
        'CAJA: Egresos Juan sin Cta. Cte.': 3,
        'CAJA: Egresos sin cta cte': 4
    }};

    function money(value) {{
        return new Intl.NumberFormat('es-AR', {{ style: 'currency', currency: 'ARS' }}).format(value);
    }}

    function count(value) {{
        return Number(value || 0).toLocaleString('es-AR');
    }}

    function escapeHtml(value) {{
        const entities = {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }};
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {{
            return entities[character];
        }});
    }}

    function badgeClass(type) {{
        const classes = {{
            'Proveedor': 'badge-proveedor',
            'Empleado': 'badge-empleado',
            'Vendedor': 'badge-vendedor',
            'Cliente': 'badge-cliente',
            'Socios': 'badge-socios',
            'Ente Recaudador': 'badge-ente',
            'Sin clasificar': 'badge-sin-clasificar'
        }};
        return classes[type] || 'badge-default';
    }}

    function inDateRange(dateValue, from, to) {{
        if (!from && !to) return true;
        if (!dateValue) return false;
        return (!from || dateValue >= from) && (!to || dateValue <= to);
    }}

    function displayDate(dateValue) {{
        if (!dateValue) return '-';
        const parts = dateValue.split('-');
        return parts.length === 3 ? parts[2] + '/' + parts[1] + '/' + parts[0] : dateValue;
    }}

    function applyDetailFilters() {{
        const clientName = clientNameInput.value.trim().toLowerCase();
        const reference = referenceInput.value.trim().toLowerCase();
        const client = clientInput.value.trim().toLowerCase();
        const type = typeInput.value.toLowerCase();
        const flow = flowInput.value.toLowerCase();
        const from = fromInput.value;
        const to = toInput.value;
        let visible = 0;
        let amount = 0;

        rows.forEach(function (row) {{
            const matches = (!clientName || row.dataset.clientname.toLowerCase().includes(clientName))
                && (!reference || row.dataset.reference.toLowerCase().includes(reference))
                && (!client || row.dataset.clientid.toLowerCase().includes(client))
                && (!type || row.dataset.type.toLowerCase() === type)
                && (!flow || row.dataset.flow.toLowerCase() === flow)
                && (!from || row.dataset.date >= from)
                && (!to || row.dataset.date <= to);
            row.hidden = !matches;
            if (matches) {{
                visible += 1;
                amount += Number(row.dataset.amount || 0);
            }}
        }});

        noResults.style.display = visible ? 'none' : 'table-row';
        summary.textContent = visible.toLocaleString('es-AR') + ' registros visibles | Total filtrado: ' + money(amount);
    }}

    function renderClassification() {{
        const groups = {{}};
        const from = classificationFrom.value;
        const to = classificationTo.value;
        rows.forEach(function (row) {{
            if (!inDateRange(row.dataset.date, from, to)) return;
            const key = row.dataset.type + '|' + row.dataset.flow;
            if (!groups[key]) {{
                groups[key] = {{ type: row.dataset.type, flow: row.dataset.flow, count: 0, amount: 0 }};
            }}
            groups[key].count += 1;
            groups[key].amount += Number(row.dataset.amount || 0);
        }});

        const ordered = Object.values(groups).sort(function (left, right) {{
            return (profileOrder[left.type] ?? 999) - (profileOrder[right.type] ?? 999)
                || (flowOrder[left.flow] ?? 999) - (flowOrder[right.flow] ?? 999);
        }});
        let totalCount = 0;
        let totalAmount = 0;
        let body = '';
        ordered.forEach(function (group) {{
            totalCount += group.count;
            totalAmount += group.amount;
            body += '<tr>'
                + '<td><span class="badge ' + badgeClass(group.type) + '">' + escapeHtml(group.type) + '</span></td>'
                + '<td>' + escapeHtml(group.flow) + '</td>'
                + '<td>' + count(group.count) + '</td>'
                + '<td class="currency">' + money(group.amount) + '</td>'
                + '</tr>';
        }});
        body += '<tr class="total-row">'
            + '<td colspan="2"><strong>Total</strong></td>'
            + '<td><strong>' + count(totalCount) + '</strong></td>'
            + '<td class="currency"><strong>' + money(totalAmount) + '</strong></td>'
            + '</tr>';
        classificationBody.innerHTML = body;
        classificationSummary.textContent = count(totalCount) + ' registros | Total: ' + money(totalAmount);
    }}

    function renderProfileSummary() {{
        const groups = {{}};
        const from = profileFrom.value;
        const to = profileTo.value;
        rows.forEach(function (row) {{
            if (!inDateRange(row.dataset.date, from, to)) return;
            const key = row.dataset.clientid + '|' + row.dataset.type;
            if (!groups[key]) {{
                groups[key] = {{
                    clientid: row.dataset.clientid,
                    clientname: row.dataset.clientname || row.dataset.name || '-',
                    razonsocial: row.dataset.razonsocial || '-',
                    type: row.dataset.type,
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
        }});

        const ordered = Object.values(groups).sort(function (left, right) {{
            return (profileOrder[left.type] ?? 999) - (profileOrder[right.type] ?? 999)
                || right.amount - left.amount;
        }});
        let body = '';
        let totalCount = 0;
        let totalAmount = 0;
        ordered.forEach(function (group) {{
            totalCount += group.count;
            totalAmount += group.amount;
            body += '<tr>'
                + '<td>' + escapeHtml(group.clientid) + '</td>'
                + '<td>' + escapeHtml(group.clientname) + '</td>'
                + '<td>' + escapeHtml(group.razonsocial) + '</td>'
                + '<td><span class="badge ' + badgeClass(group.type) + '">' + escapeHtml(group.type) + '</span></td>'
                + '<td>' + count(group.count) + '</td>'
                + '<td class="currency">' + money(group.amount) + '</td>'
                + '<td>' + displayDate(group.firstDate) + '</td>'
                + '<td>' + displayDate(group.lastDate) + '</td>'
                + '</tr>';
        }});
        profileBody.innerHTML = body;
        profileSummary.textContent = count(totalCount) + ' registros | ' + count(ordered.length) + ' perfiles | Total: ' + money(totalAmount);
    }}

    [clientNameInput, referenceInput, clientInput, typeInput, flowInput, fromInput, toInput].forEach(function (input) {{
        input.addEventListener('input', applyDetailFilters);
        input.addEventListener('change', applyDetailFilters);
    }});

    document.getElementById('clear-filters').addEventListener('click', function () {{
        [clientNameInput, referenceInput, clientInput, fromInput, toInput].forEach(function (input) {{ input.value = ''; }});
        typeInput.value = '';
        flowInput.value = '';
        applyDetailFilters();
    }});

    [classificationFrom, classificationTo].forEach(function (input) {{
        input.addEventListener('input', renderClassification);
        input.addEventListener('change', renderClassification);
    }});
    document.getElementById('clear-classification-filters').addEventListener('click', function () {{
        classificationFrom.value = '';
        classificationTo.value = '';
        renderClassification();
    }});

    [profileFrom, profileTo].forEach(function (input) {{
        input.addEventListener('input', renderProfileSummary);
        input.addEventListener('change', renderProfileSummary);
    }});
    document.getElementById('clear-profile-filters').addEventListener('click', function () {{
        profileFrom.value = '';
        profileTo.value = '';
        renderProfileSummary();
    }});

    applyDetailFilters();
    renderClassification();
    renderProfileSummary();
}}());
</script>
<script src="assets/export_excel.js"></script>
</body>
</html>
"""

    output_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "reporte_investigacion_egresos.html")
    )
    with open(output_path, "w", encoding="utf-8") as report_file:
        report_file.write(html_content)

    print(f"Reporte generado: {output_path}")
    print(f"Registros: {format_integer(total_records)}")
    print(f"Monto total: {format_currency(total_amount)}")
    return output_path


if __name__ == "__main__":
    generate_html_report()
