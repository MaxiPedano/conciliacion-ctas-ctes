#!/usr/bin/env python3
"""Genera un reporte independiente de cuenta corriente y sus saldos."""

import html
import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta

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


# Clasificacion de cada perfil segun sus categorias (raiz y subcategorias).
# La prioridad replica docs/queries_conciliacion.sql y agrega el caso Ambos.
QUERY_PROFILE_TYPES = """
SELECT
    cp.perfilid,
    BOOL_OR(c.id = 1081 OR c.parentid = 1081) AS es_proveedor,
    BOOL_OR(c.id = 1080 OR c.parentid = 1080) AS es_cliente,
    BOOL_OR(c.id = 1082 OR c.parentid = 1082) AS es_empleado,
    BOOL_OR(
        c.id IN (11367, 10659) OR c.parentid IN (11367, 10659)
    ) AS es_vendedor,
    BOOL_OR(c.id = 11364 OR c.parentid = 11364) AS es_socio,
    BOOL_OR(
        c.id IN (10805, 10820, 10821) OR c.parentid IN (10805, 10820, 10821)
    ) AS es_ente
FROM test9000.categoriasperfiles cp
JOIN test9000.categorias c ON c.id = cp.categoriaid
GROUP BY cp.perfilid
"""


TIPO_ORDER = [
    "Ambos",
    "Proveedor",
    "Empleado",
    "Vendedor",
    "Cliente",
    "Socios",
    "Ente Recaudador",
    "Sin clasificar",
    "Sin cliente",
]


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


def slug(value):
    normalized = unicodedata.normalize("NFD", clean_text(value))
    stripped = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-zA-Z0-9]+", "-", stripped).strip("-").lower()


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


def classify_profile(row):
    """Prioridad documentada: Ambos, Proveedor, Empleado, Vendedor, Cliente."""
    if bool(row["es_cliente"]) and bool(row["es_proveedor"]):
        return "Ambos"
    if bool(row["es_proveedor"]):
        return "Proveedor"
    if bool(row["es_empleado"]):
        return "Empleado"
    if bool(row["es_vendedor"]):
        return "Vendedor"
    if bool(row["es_cliente"]):
        return "Cliente"
    if bool(row["es_socio"]):
        return "Socios"
    if bool(row["es_ente"]):
        return "Ente Recaudador"
    return "Sin clasificar"


def build_type_map(connection):
    types = read_query(connection, QUERY_PROFILE_TYPES)
    return {
        int(row["perfilid"]): classify_profile(row)
        for _, row in types.iterrows()
    }


def profile_type(key, type_map):
    if key == "SIN_CLIENTE":
        return "Sin cliente"
    try:
        return type_map.get(int(float(key)), "Sin clasificar")
    except (TypeError, ValueError):
        return "Sin clasificar"


def tipo_rank(tipo):
    try:
        return TIPO_ORDER.index(tipo)
    except ValueError:
        return len(TIPO_ORDER)


def build_account_rows(df, type_map, order="tipo"):
    if df.empty:
        return []
    grouped = []
    for key, group in df.groupby(df["clientid"].map(client_key), sort=False):
        grouped.append(
            {
                "key": key,
                "clientid": "" if key == "SIN_CLIENTE" else key,
                "clientname": group["clientname"].dropna().iloc[0] if group["clientname"].notna().any() else "SIN CLIENTE",
                "tipo": profile_type(key, type_map),
                "records": len(group),
                "haber": group["haber"].fillna(0).map(numeric).sum(),
                "debe": group["debe"].fillna(0).map(numeric).sum(),
                "saldo": group["haber"].fillna(0).map(numeric).sum() - group["debe"].fillna(0).map(numeric).sum(),
                "first_date": group["fecha"].min(),
                "last_date": group["fecha"].max(),
            }
        )
    if order == "actividad":
        grouped.sort(key=lambda item: (iso_date(item["last_date"]), -abs(item["saldo"])), reverse=True)
    elif order == "saldo":
        grouped.sort(key=lambda item: item["saldo"])
    elif order == "registros":
        grouped.sort(key=lambda item: item["records"], reverse=True)
    elif order == "nombre":
        grouped.sort(key=lambda item: clean_text(item["clientname"]).upper())
    else:
        grouped.sort(key=lambda item: (tipo_rank(item["tipo"]), -abs(item["saldo"])))
    return grouped


def summary_row(item):
    return (
        "<tr data-account=\"" + attribute(item["key"]) + "\" data-tipo=\"" + attribute(item["tipo"]) + "\">"
        f"<td>{text(item['clientid'])}</td>"
        f"<td>{text(item['clientname'])}</td>"
        f"<td><span class=\"badge badge-{attribute(slug(item['tipo']))}\">{text(item['tipo'])}</span></td>"
        f"<td>{integer(item['records'])}</td>"
        f"<td class=\"currency\">{money(item['haber'])}</td>"
        f"<td class=\"currency\">{money(item['debe'])}</td>"
        f"<td class=\"currency\">{money(item['saldo'])}</td>"
        f"<td>{display_date(item['first_date'])}</td>"
        f"<td>{display_date(item['last_date'])}</td>"
        "</tr>"
    )


def build_client_summary(df, type_map):
    return "\n".join(
        summary_row(item)
        for item in build_account_rows(df, type_map, order="tipo")
    )


def build_account_options(df, type_map):
    if df.empty:
        return ""
    options = []
    for key, group in df.groupby(df["clientid"].map(client_key), sort=False):
        name = group["clientname"].dropna().iloc[0] if group["clientname"].notna().any() else "SIN CLIENTE"
        label_id = "sin clientid" if key == "SIN_CLIENTE" else key.split(".")[0]
        options.append((profile_type(key, type_map), clean_text(str(name)), key, label_id))
    options.sort(key=lambda item: (tipo_rank(item[0]), item[1].upper()))
    return "\n".join(
        f"<option value=\"{attribute(key)}\">{text(name)} ({text(label_id)})</option>"
        for _, name, key, label_id in options
    )


def build_type_summary(df, type_map):
    rows = []
    accounts = build_account_rows(df, type_map, order="tipo")
    for tipo in TIPO_ORDER:
        subset = [item for item in accounts if item["tipo"] == tipo]
        rows.append(
            "<tr data-type=\"" + attribute(tipo) + "\">"
            f"<td><span class=\"badge badge-{attribute(slug(tipo))}\">{text(tipo)}</span></td>"
            f"<td>{integer(len(subset))}</td>"
            f"<td class=\"currency\">{money(sum(item['haber'] for item in subset))}</td>"
            f"<td class=\"currency\">{money(sum(item['debe'] for item in subset))}</td>"
            f"<td class=\"currency\">{money(sum(item['saldo'] for item in subset))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_detail_rows(df, type_map):
    rows = []
    for _, row in df.iterrows():
        account_reference = row["referencia_cta_contable"]
        account_type = profile_type(client_key(row["clientid"]), type_map)
        def raw(value):
            return "" if empty(value) else clean_text(value)
        rows.append({"dataset": {
            "id": identifier(row["id"]), "date": iso_date(row["fecha"]),
            "clientid": raw(row["clientid"]), "clientname": raw(row["clientname"]),
            "tipo": account_type, "reference": raw(row["referenciatexto"]),
            "account": raw(account_reference), "flow": raw(row["flows"]),
            "haber": numeric(row["haber"]), "debe": numeric(row["debe"]),
        }, "commitment": iso_date(row["fechacompromiso"])})
    # Evita cerrar el script JSON si una referencia contiene HTML.
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


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
        print("Ejecutando consulta de clasificacion de perfiles...")
        type_map = build_type_map(connection)

    return render_report(df, type_map)


def render_report(df, type_map, generated_at=None):
    """Renderiza también snapshots locales sin volver a consultar la base."""
    if not df.empty:
        df = df.sort_values(["clientid", "fecha", "id"], na_position="last")

    total_haber = df["haber"].fillna(0).map(numeric).sum() if not df.empty else 0
    total_debe = df["debe"].fillna(0).map(numeric).sum() if not df.empty else 0
    total_saldo = total_haber - total_debe
    client_count = df["clientid"].nunique(dropna=True) if not df.empty else 0
    client_summary_html = build_client_summary(df, type_map)
    type_summary_html = build_type_summary(df, type_map)
    detail_html = build_detail_rows(df, type_map)

    account_keys = df["clientid"].map(client_key).unique() if not df.empty else []
    present_types = []
    for key in account_keys:
        tipo = profile_type(key, type_map)
        if tipo not in present_types:
            present_types.append(tipo)
    present_types.sort(key=tipo_rank)
    type_options_html = "\n".join(
        f"<option value=\"{attribute(tipo)}\">{text(tipo)}</option>"
        for tipo in present_types
    )
    account_options_html = build_account_options(df, type_map)
    data_max_json = json.dumps(iso_date(df["fecha"].max()) if not df.empty else "")
    tipo_order_json = json.dumps(TIPO_ORDER)

    data_max = iso_date(df["fecha"].max()) if not df.empty else ""
    active_30 = 0
    if not df.empty:
        last_by_account = df.groupby(df["clientid"].map(client_key))["fecha"].max()
        threshold = (datetime.strptime(data_max, "%Y-%m-%d") - timedelta(days=30)).date()
        active_30 = int(sum(1 for value in last_by_account if iso_date(value) >= iso_date(threshold)))

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
    generated_at = generated_at or datetime.now().strftime("%d/%m/%Y %H:%M")

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
        .badge {{ display: inline-block; padding: 3px 9px; border-radius: 99px; color: white; background: #7b8794; font-size: .74rem; font-weight: 700; letter-spacing: .02em; white-space: nowrap; }}
        .badge-cliente {{ background: #287a62; }}
        .badge-proveedor {{ background: #1d3b55; }}
        .badge-ambos {{ background: #7d4aa0; }}
        .badge-empleado {{ background: #c77925; }}
        .badge-vendedor {{ background: #b4622c; }}
        .badge-socios {{ background: #39265e; }}
        .badge-ente-recaudador {{ background: #54757f; }}
        .badge-sin-clasificar {{ background: #a94442; }}
        .badge-sin-cliente {{ background: #6b7480; }}
        #client-summary-body tr, #type-summary-body tr {{ cursor: pointer; }}
        tr.selected-account {{ background: #e4f2ee !important; box-shadow: inset 3px 0 0 #287a62; }}
        tr.account-start td {{ border-top: 2px solid #a477c4; }}
        .account-tag {{ color: #6a4b8c; font-weight: 700; }}
        .window-note {{ margin: 8px 0 0; color: #49365d; font-size: .84rem; }}
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
        <p class="subtitle">Clientes y proveedores: movimientos por cuenta, clasificados por tipo y ordenados por saldo</p>
        <p class="subtitle">La cuenta se calcula como Haber - Debe según el rango seleccionado</p>
        <p class="subtitle">Generado: {generated_at}</p>
    </header>

    <section class="section">
        <h2>Resumen del Saldo</h2>
        <div class="summary-grid">
            <div class="summary-card green"><h3 id="card-records">{integer(len(df))}</h3><p>Movimientos visibles</p></div>
            <div class="summary-card"><h3 id="card-clients">{integer(client_count)}</h3><p>Cuentas corrientes</p></div>
            <div class="summary-card"><h3 id="card-active">{integer(active_30)}</h3><p>Activas últimos 30 días</p></div>
            <div class="summary-card"><h3 id="card-haber">{money(total_haber)}</h3><p>Total Haber</p></div>
            <div class="summary-card orange"><h3 id="card-debe">{money(total_debe)}</h3><p>Total Debe</p></div>
            <div class="summary-card red"><h3 id="card-saldo">{money(total_saldo)}</h3><p>Saldo total</p></div>
        </div>
        <p id="date-summary" class="filter-summary"></p>
    </section>

    <section class="section">
        <h2>Resumen por Tipo de Perfil</h2>
        <p>Clasificación según <span class="account-tag">categoriasperfiles</span> (raíz y subcategorías). La ventana de fechas y la actividad reciente de abajo también aplican aquí.</p>
        <div class="table-wrap"><table id="type-summary-table" data-excel-table data-excel-title="Resumen por Tipo" data-excel-all-source="type-summary-all-table">
            <thead><tr><th>tipo</th><th>cuentas</th><th>haber</th><th>debe</th><th>saldo</th></tr></thead>
            <tbody id="type-summary-body">{type_summary_html}</tbody>
        </table><table id="type-summary-all-table" style="display:none">
            <thead><tr><th>tipo</th><th>cuentas</th><th>haber</th><th>debe</th><th>saldo</th></tr></thead>
            <tbody>{type_summary_html}</tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Cuentas Corrientes (por tipo y saldo)</h2>
        <p>Una fila por cuenta. Haga clic en una fila para ver abajo los movimientos de esa cuenta.</p>
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
            <label>Tipo de perfil
                <select id="type-filter"><option value="">Todos los tipos</option>{type_options_html}</select>
            </label>
            <label>Cuentas con actividad
                <select id="activity-filter">
                    <option value="">Cualquier fecha</option>
                    <option value="7">Últimos 7 días</option>
                    <option value="30">Últimos 30 días</option>
                    <option value="90">Últimos 90 días</option>
                    <option value="180">Últimos 180 días</option>
                    <option value="365">Últimos 365 días</option>
                </select>
            </label>
            <label>Orden
                <select id="summary-order">
                    <option value="tipo">Tipo y saldo</option>
                    <option value="actividad">Actividad reciente</option>
                    <option value="saldo">Saldo deudor</option>
                    <option value="registros">Cantidad de movimientos</option>
                    <option value="nombre">Nombre</option>
                </select>
            </label>
        </div>
        <p id="account-summary" class="filter-summary"></p>
        <div class="table-wrap"><table id="client-summary-table" data-excel-table data-excel-title="Cuentas Corrientes" data-excel-all-source="client-summary-all-table">
            <thead><tr><th>clientid</th><th>cliente</th><th>tipo</th><th>movimientos</th><th>haber</th><th>debe</th><th>saldo</th><th>primera fecha</th><th>última fecha</th></tr></thead>
            <tbody id="client-summary-body">{client_summary_html}</tbody>
        </table><table id="client-summary-all-table" style="display:none">
            <thead><tr><th>clientid</th><th>cliente</th><th>tipo</th><th>movimientos</th><th>haber</th><th>debe</th><th>saldo</th><th>primera fecha</th><th>última fecha</th></tr></thead>
            <tbody>{client_summary_html}</tbody>
        </table></div>
    </section>

    <section class="section">
        <h2>Movimientos por Cuenta</h2>
        <p>Agrupa los movimientos por cuenta y ubica primero las cuentas que tuvieron movimiento más reciente.</p>
        <div class="filters">
            <label>Cuenta corriente
                <select id="account-filter"><option value="">Todas las cuentas</option>{account_options_html}</select>
            </label>
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
                <select id="order-filter">
                    <option value="CUENTA">Por cuenta (actividad reciente)</option>
                    <option value="ASC">Fecha ascendente</option>
                    <option value="DESC">Fecha descendente</option>
                </select>
            </label>
            <button id="clear-filters" type="button">Limpiar filtros</button>
        </div>
        <p id="detail-summary" class="filter-summary"></p>
        <div class="table-wrap"><table id="detail-table" data-excel-table data-excel-title="Movimientos por Cuenta">
            <thead><tr><th>registrocab</th><th>fecha</th><th>clientid</th><th>cliente</th><th>tipo</th><th>referencia</th><th>fecha compromiso</th><th>flujo</th><th>referencia cta contable</th><th>haber</th><th>debe</th><th>saldo acumulado</th><th>saldo total</th></tr></thead>
            <tbody></tbody>
        </table></div>
        <div class="filters" aria-label="Paginación de movimientos">
            <button id="page-prev" type="button">Anterior</button>
            <span id="page-status" role="status" aria-live="polite"></span>
            <button id="page-next" type="button">Siguiente</button>
            <label>Movimientos por página<select id="page-size"><option>50</option><option selected>100</option><option>250</option></select></label>
        </div>
        <p class="window-note">Los saldos y Excel filtrado incluyen todos los movimientos del filtro, no solo esta página.</p>
    </section>

    <section class="section">
        <h2>Consulta Base</h2>
        {query_block("Consulta Jasper con referencia de cuenta contable", QUERY_JASPER)}
        {query_block("Consulta ejecutada para cargar el informe", QUERY_DETAIL)}
        {query_block("Clasificación de perfiles por categoría", QUERY_PROFILE_TYPES)}
    </section>

    <footer>Reporte separado de cuenta corriente | Base: va9000-avanzia | Schema: test9000</footer>
</div>
<script id="movement-data" type="application/json">{detail_html}</script>
<script>
(function () {{
    const rows = JSON.parse(document.getElementById('movement-data').textContent);
    const tbody = document.querySelector('#detail-table tbody');
    rows.forEach(function (row) {{
        row.clientSearch = (row.dataset.clientid + ' ' + row.dataset.clientname).toLowerCase();
        row.referenceSearch = (row.dataset.reference + ' ' + row.dataset.account).toLowerCase();
    }});
    let page = 0, displayRows = [], filterState = {{}}, timer;
    const pageSize = document.getElementById('page-size');
    const currencyFormat = new Intl.NumberFormat('es-AR', {{ style: 'currency', currency: 'ARS' }});
    const yearFilter = document.getElementById('year-filter');
    const dateFrom = document.getElementById('date-from');
    const dateTo = document.getElementById('date-to');
    const clientFilter = document.getElementById('client-filter');
    const referenceFilter = document.getElementById('reference-filter');
    const flowFilter = document.getElementById('flow-filter');
    const orderFilter = document.getElementById('order-filter');
    const accountFilter = document.getElementById('account-filter');
    const typeFilter = document.getElementById('type-filter');
    const activityFilter = document.getElementById('activity-filter');
    const summaryOrder = document.getElementById('summary-order');
    const dataMax = {data_max_json};
    const TIPO_ORDER = {tipo_order_json};
    const TIPO_RANK = {{}};
    TIPO_ORDER.forEach(function (tipo, index) {{ TIPO_RANK[tipo] = index; }});
    let accountInfo = {{}};

    function numeric(value) {{ return Number(value || 0); }}
    function money(value) {{ return currencyFormat.format(numeric(value)); }}
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
    function slug(value) {{
        return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    }}
    function accountKey(row) {{ return row.dataset.clientid || 'SIN_CLIENTE'; }}
    function rankOf(tipo) {{ return Object.prototype.hasOwnProperty.call(TIPO_RANK, tipo) ? TIPO_RANK[tipo] : 99; }}
    function inDateRange(row) {{
        return (!filterState.from || row.dataset.date >= filterState.from)
            && (!filterState.to || row.dataset.date <= filterState.to);
    }}
    function shiftDays(iso, days) {{
        const parts = String(iso).split('-');
        const stamp = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])));
        stamp.setUTCDate(stamp.getUTCDate() - days);
        return stamp.toISOString().slice(0, 10);
    }}
    function activityThreshold() {{
        if (!activityFilter.value || !dataMax) return '';
        return shiftDays(dataMax, Number(activityFilter.value));
    }}
    function matches(row) {{
        return inDateRange(row)
            && (!filterState.account || accountKey(row) === filterState.account)
            && (!filterState.client || row.clientSearch.includes(filterState.client))
            && (!filterState.reference || row.referenceSearch.includes(filterState.reference))
            && (!filterState.flow || row.dataset.flow === filterState.flow);
    }}
    function buildAccounts(base) {{
        const info = {{}};
        base.forEach(function (row) {{
            const key = accountKey(row);
            if (!info[key]) {{
                info[key] = {{ id: row.dataset.clientid, name: row.dataset.clientname || 'SIN CLIENTE',
                    tipo: row.dataset.tipo || 'Sin clasificar', rows: 0, haber: 0, debe: 0, first: '', last: '' }};
            }}
            const item = info[key];
            item.rows += 1;
            item.haber += numeric(row.dataset.haber);
            item.debe += numeric(row.dataset.debe);
            const day = row.dataset.date;
            if (day) {{
                if (!item.first || day < item.first) item.first = day;
                if (!item.last || day > item.last) item.last = day;
            }}
        }});
        return info;
    }}
    function accountPasses(key, checkType) {{
        const item = accountInfo[key];
        if (!item) return false;
        if (checkType && typeFilter.value && item.tipo !== typeFilter.value) return false;
        const threshold = filterState.threshold;
        if (threshold && (!item.last || item.last < threshold)) return false;
        return true;
    }}
    function accountList(checkType) {{
        return Object.keys(accountInfo)
            .filter(function (key) {{ return accountPasses(key, checkType); }})
            .map(function (key) {{ return Object.assign({{ key: key }}, accountInfo[key]); }});
    }}
    function compareRows(left, right, descending) {{
        const dateCompare = (left.dataset.date || '').localeCompare(right.dataset.date || '');
        if (dateCompare !== 0) return descending ? -dateCompare : dateCompare;
        const idCompare = numeric(left.dataset.id) - numeric(right.dataset.id);
        return descending ? -idCompare : idCompare;
    }}
    function saldoOf(item) {{ return item.haber - item.debe; }}
    function sortAccounts(list) {{
        const mode = summaryOrder.value;
        return list.sort(function (left, right) {{
            if (mode === 'actividad') {{
                if ((left.last || '') !== (right.last || '')) return (right.last || '').localeCompare(left.last || '');
                return Math.abs(saldoOf(right)) - Math.abs(saldoOf(left));
            }}
            if (mode === 'saldo') return saldoOf(left) - saldoOf(right);
            if (mode === 'registros') return right.rows - left.rows;
            if (mode === 'nombre') return String(left.name).toUpperCase().localeCompare(String(right.name).toUpperCase());
            if (left.tipo !== right.tipo) return rankOf(left.tipo) - rankOf(right.tipo);
            return Math.abs(saldoOf(right)) - Math.abs(saldoOf(left));
        }});
    }}
    function accountRow(item) {{
        const selected = item.key === accountFilter.value ? ' class="selected-account"' : '';
        return '<tr' + selected + ' data-account="' + escapeHtml(item.key) + '" data-tipo="' + escapeHtml(item.tipo)
            + '" data-last="' + escapeHtml(item.last || '') + '">'
            + '<td>' + escapeHtml(item.id || '-') + '</td>'
            + '<td>' + escapeHtml(item.name) + '</td>'
            + '<td><span class="badge badge-' + slug(item.tipo) + '">' + escapeHtml(item.tipo) + '</span></td>'
            + '<td>' + count(item.rows) + '</td>'
            + '<td class="currency">' + money(item.haber) + '</td>'
            + '<td class="currency">' + money(item.debe) + '</td>'
            + '<td class="currency">' + money(saldoOf(item)) + '</td>'
            + '<td>' + displayDate(item.first) + '</td>'
            + '<td>' + displayDate(item.last) + '</td></tr>';
    }}
    function renderAccountSummary() {{
        const list = sortAccounts(accountList(true));
        document.getElementById('client-summary-body').innerHTML = list.map(accountRow).join('');
        const orderLabels = {{ tipo: 'tipo y saldo', actividad: 'actividad reciente', saldo: 'saldo deudor', registros: 'movimientos', nombre: 'nombre' }};
        const threshold = activityThreshold();
        document.getElementById('account-summary').textContent =
            count(list.length) + ' cuentas'
            + (typeFilter.value ? ' | tipo: ' + typeFilter.value : ' | todos los tipos')
            + (threshold ? ' | con movimiento desde ' + displayDate(threshold) : ' | sin límite de actividad')
            + ' | orden: ' + (orderLabels[summaryOrder.value] || summaryOrder.value);
    }}
    function renderTypeSummary() {{
        const buckets = {{}};
        TIPO_ORDER.forEach(function (tipo) {{ buckets[tipo] = {{ cuentas: 0, haber: 0, debe: 0 }}; }});
        accountList(true).forEach(function (item) {{
            if (!buckets[item.tipo]) buckets[item.tipo] = {{ cuentas: 0, haber: 0, debe: 0 }};
            buckets[item.tipo].cuentas += 1;
            buckets[item.tipo].haber += item.haber;
            buckets[item.tipo].debe += item.debe;
        }});
        document.getElementById('type-summary-body').innerHTML = TIPO_ORDER.map(function (tipo) {{
            const bucket = buckets[tipo];
            return '<tr data-type="' + escapeHtml(tipo) + '">'
                + '<td><span class="badge badge-' + slug(tipo) + '">' + escapeHtml(tipo) + '</span></td>'
                + '<td>' + count(bucket.cuentas) + '</td>'
                + '<td class="currency">' + money(bucket.haber) + '</td>'
                + '<td class="currency">' + money(bucket.debe) + '</td>'
                + '<td class="currency">' + money(bucket.haber - bucket.debe) + '</td></tr>';
        }}).join('');
    }}
    function render() {{
        clearTimeout(timer);
        timer = null;
        page = 0;
        filterState = {{ from: dateFrom.value, to: dateTo.value, account: accountFilter.value,
            client: clientFilter.value.trim().toLowerCase(), reference: referenceFilter.value.trim().toLowerCase(),
            flow: flowFilter.value, threshold: activityThreshold() }};
        const base = rows.filter(matches);
        accountInfo = buildAccounts(base);
        const visible = base.filter(function (row) {{ return accountPasses(accountKey(row), true); }});
        const chronological = visible.slice().sort(function (left, right) {{ return compareRows(left, right, false); }});
        const groups = {{}};
        chronological.forEach(function (row) {{
            const key = accountKey(row);
            if (!groups[key]) groups[key] = {{ running: 0, total: 0 }};
            groups[key].running += numeric(row.dataset.haber) - numeric(row.dataset.debe);
            groups[key].total += numeric(row.dataset.haber) - numeric(row.dataset.debe);
            row.running = groups[key].running;
        }});
        chronological.forEach(function (row) {{
            const key = accountKey(row);
            row.total = groups[key].total;
        }});
        const mode = orderFilter.value;
        const display = visible.slice().sort(function (left, right) {{
            if (mode !== 'CUENTA') return compareRows(left, right, mode === 'DESC');
            const leftKey = accountKey(left);
            const rightKey = accountKey(right);
            if (leftKey !== rightKey) {{
                const leftInfo = accountInfo[leftKey] || {{}};
                const rightInfo = accountInfo[rightKey] || {{}};
                const leftLast = leftInfo.last || '';
                const rightLast = rightInfo.last || '';
                if (leftLast !== rightLast) return rightLast.localeCompare(leftLast);
                const leftName = String(leftInfo.name || '').toUpperCase();
                const rightName = String(rightInfo.name || '').toUpperCase();
                if (leftName !== rightName) return leftName.localeCompare(rightName);
                return leftKey.localeCompare(rightKey);
            }}
            return compareRows(left, right, false);
        }});
        displayRows = display;
        renderPage();
        const haber = visible.reduce(function (sum, row) {{ return sum + numeric(row.dataset.haber); }}, 0);
        const debe = visible.reduce(function (sum, row) {{ return sum + numeric(row.dataset.debe); }}, 0);
        const accounts = accountList(true);
        const clients = new Set(visible.map(accountKey));
        const threshold30 = dataMax ? shiftDays(dataMax, 30) : '';
        const active30 = threshold30 ? accounts.filter(function (item) {{ return item.last && item.last >= threshold30; }}).length : accounts.length;
        document.getElementById('card-records').textContent = count(visible.length);
        document.getElementById('card-clients').textContent = count(clients.size);
        document.getElementById('card-active').textContent = count(active30);
        document.getElementById('card-haber').textContent = money(haber);
        document.getElementById('card-debe').textContent = money(debe);
        document.getElementById('card-saldo').textContent = money(haber - debe);
        const period = yearFilter.value
            ? 'Año ' + yearFilter.value
            : ((dateFrom.value || dateTo.value) ? (dateFrom.value || 'inicio') + ' a ' + (dateTo.value || 'fin') : 'Todos los años');
        const activityLabel = activityThreshold() ? ' | actividad desde ' + displayDate(activityThreshold()) : '';
        document.getElementById('date-summary').textContent = period + ' | ' + count(visible.length) + ' movimientos | ' + count(clients.size) + ' cuentas' + activityLabel + ' | Saldo: ' + money(haber - debe);
        document.getElementById('detail-summary').textContent = 'El filtro incluye ' + count(visible.length) + ' movimientos de ' + count(clients.size) + ' cuentas. Orden: '
            + (mode === 'CUENTA' ? 'cuentas con movimiento más reciente primero' : (mode === 'DESC' ? 'fecha descendente' : 'fecha ascendente')) + '.';
        renderAccountSummary();
        renderTypeSummary();
    }}
    function detailRow(row, index, source) {{
        const d = row.dataset;
        const start = index === 0 || accountKey(source[index - 1]) !== accountKey(row);
        const cells = [d.id, displayDate(d.date), d.clientid || '-', d.clientname || '-',
            d.tipo, d.reference || '-', displayDate(row.commitment), d.flow || '-', d.account || '-'];
        return '<tr class="detail-row' + (start ? ' account-start' : '') + '" data-id="' + escapeHtml(d.id) + '">'
            + cells.map(function (value, i) {{ return '<td>' + (i === 4
                ? '<span class="badge badge-' + slug(d.tipo) + '">' + escapeHtml(value) + '</span>'
                : escapeHtml(value)) + '</td>'; }}).join('')
            + [d.haber, d.debe, row.running, row.total].map(function (value) {{
                return '<td class="currency">' + money(value) + '</td>';
            }}).join('') + '</tr>';
    }}
    function renderPage() {{
        const size = Number(pageSize.value);
        const pages = Math.max(1, Math.ceil(displayRows.length / size));
        page = Math.max(0, Math.min(page, pages - 1));
        const start = page * size;
        tbody.innerHTML = displayRows.slice(start, start + size).map(function (row, index) {{
            return detailRow(row, start + index, displayRows);
        }}).join('') || '<tr id="no-results"><td colspan="13">No hay registros para los filtros seleccionados.</td></tr>';
        document.getElementById('page-status').textContent = 'Página ' + (page + 1) + ' de ' + pages
            + ' | ' + (displayRows.length ? start + 1 : 0) + '–' + Math.min(start + size, displayRows.length)
            + ' de ' + count(displayRows.length) + ' movimientos';
        document.getElementById('page-prev').disabled = page === 0;
        document.getElementById('page-next').disabled = page === pages - 1;
        tbody.closest('.table-wrap').scrollTop = 0;
    }}
    document.getElementById('page-prev').addEventListener('click', function () {{ page--; renderPage(); }});
    document.getElementById('page-next').addEventListener('click', function () {{ page++; renderPage(); }});
    pageSize.addEventListener('change', function () {{ page = 0; renderPage(); }});
    [clientFilter, referenceFilter].forEach(function (input) {{
        input.addEventListener('input', function () {{ clearTimeout(timer); timer = setTimeout(render, 250); }});
    }});
    summaryOrder.addEventListener('change', renderAccountSummary);
    [flowFilter, orderFilter, accountFilter, typeFilter, activityFilter].forEach(function (input) {{
        input.addEventListener('change', render);
    }});
    [dateFrom, dateTo].forEach(function (input) {{
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
    document.getElementById('client-summary-body').addEventListener('click', function (event) {{
        const row = event.target.closest('tr');
        if (!row || !row.dataset.account) return;
        accountFilter.value = row.dataset.account === accountFilter.value ? '' : row.dataset.account;
        render();
        document.getElementById('detail-table').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }});
    document.getElementById('type-summary-body').addEventListener('click', function (event) {{
        const row = event.target.closest('tr');
        if (!row || !row.dataset.type) return;
        typeFilter.value = typeFilter.value === row.dataset.type ? '' : row.dataset.type;
        render();
    }});
    document.getElementById('clear-filters').addEventListener('click', function () {{
        yearFilter.value = '';
        dateFrom.value = '';
        dateTo.value = '';
        accountFilter.value = '';
        clientFilter.value = '';
        referenceFilter.value = '';
        flowFilter.value = '';
        typeFilter.value = '';
        activityFilter.value = '';
        summaryOrder.value = 'tipo';
        orderFilter.value = 'CUENTA';
        render();
    }});
    const table = document.getElementById('detail-table');
    table.excelDataProvider = function (includeAll) {{
        if (timer) render();
        let source = displayRows;
        if (includeAll) {{
            source = rows.map(function (row) {{ return Object.assign({{}}, row); }})
                .sort(function (a, b) {{ return compareRows(a, b, false); }});
            const totals = buildAccounts(source), running = {{}};
            source.forEach(function (row) {{
                const key = accountKey(row);
                running[key] = (running[key] || 0) + row.dataset.haber - row.dataset.debe;
                row.running = running[key];
                row.total = totals[key].haber - totals[key].debe;
            }});
        }}
        return '<table>' + table.tHead.outerHTML + '<tbody>' + source.map(detailRow).join('') + '</tbody></table>';
    }};
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
