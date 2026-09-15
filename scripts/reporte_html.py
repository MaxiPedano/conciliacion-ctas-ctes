# -*- coding: utf-8 -*-
"""
Genera reporte HTML integral de conciliacion de CLIENTES Y PROVEEDORES.
Resumen ejecutivo + graficos + selector de entidad con movimientos.
Clasificacion cliente/proveedor por categoriaid del mayor contable.
"""
import pandas as pd
import numpy as np
import os
import base64
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from rapidfuzz import fuzz

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_HTML = os.path.join(BASE, "reporte_conciliacion.html")

# ---------------------------------------------------------------------------
# CARGA
# ---------------------------------------------------------------------------
ctacte = pd.read_pickle(os.path.join(BASE, "_ctacte.pkl"))
contable = pd.read_pickle(os.path.join(BASE, "_contable.pkl"))

ctacte["fecha"] = pd.to_datetime(ctacte["fecha"], errors="coerce")
contable["fecha"] = pd.to_datetime(contable["fecha"], errors="coerce")
ctacte["clientid"] = ctacte["clientid"].astype("Int64")
contable["clientid"] = contable["clientid"].astype("Int64")

# Clasificacion por categoriaid (tipos de perfil)
CAT_CLIENTE = {1080, 11318, 1094, 11548}
CAT_PROVEEDOR = {1081, 10685, 11360, 11345}

cats_por_clientid = contable.groupby("clientid")["categoriaid"].apply(
    lambda s: set(s.dropna().unique().tolist()))

def _clasif(cats):
    s = set(cats)
    es_cli = bool(s & CAT_CLIENTE)
    es_prov = bool(s & CAT_PROVEEDOR)
    if es_cli and es_prov:
        return "Cliente+Proveedor"
    if es_cli:
        return "Cliente"
    if es_prov:
        return "Proveedor"
    return "Otro"

clasif_map = cats_por_clientid.apply(_clasif)
ctacte["tipo"] = ctacte["clientid"].map(clasif_map).fillna("Otro")
contable["tipo"] = contable["clientid"].map(clasif_map).fillna("Otro")

ids_ctacte = set(ctacte["clientid"].unique())
contable_prov = contable[contable["clientid"].isin(ids_ctacte)].copy()

ids_fuera = set(contable["clientid"].unique()) - ids_ctacte
fuera_df = contable[contable["clientid"].isin(ids_fuera)].drop_duplicates("clientid")[["clientid", "clientname", "tipo"]]

# Deduplicar contable
dedup_cols = ["clientid", "fecha", "referenciatexto", "totalprecio"]
def _agg_cc(g): return " | ".join(g.dropna().unique().tolist())
cb_dedup = contable_prov.groupby(dedup_cols, as_index=False).agg(
    clientname=("clientname", "first"),
    totalimpuestos=("totalimpuestos", "max"),
    cuentacontable=("cuentacontable", _agg_cc),
    categoriaid=("categoriaid", lambda s: "|".join(s.astype(str).unique())),
)

# Saldos
ctacte_sorted = ctacte.sort_values(["clientid", "fecha"])
ctacte_last = ctacte_sorted.groupby("clientid").last().reset_index()
saldo_ctacte = ctacte_last[["clientid", "clientname", "saldo_cliente", "saldo_acumulado"]].copy()
cb_saldo = cb_dedup.groupby("clientid").agg(sum_totalprecio=("totalprecio", "sum"), n_mov_contable=("totalprecio", "count")).reset_index()
saldos = pd.merge(saldo_ctacte, cb_saldo, on="clientid", how="left")
saldos["sum_totalprecio"] = saldos["sum_totalprecio"].fillna(0)
saldos["n_mov_contable"] = saldos["n_mov_contable"].fillna(0)
saldos["diferencia"] = saldos["saldo_cliente"] - saldos["sum_totalprecio"]
saldos["diferencia_pct"] = (saldos["diferencia"] / saldos["saldo_cliente"].replace(0, np.nan)) * 100

# Categorias segun informe: A) no cuadra saldo, B) mov no coinciden, C) conciliado
# (usamos el criterio de saldo del informe final: dif <= 1 => conciliado)
saldos["categoria"] = np.where(
    saldos["diferencia"].abs() <= 1,
    "Conciliado",
    "No cuadra"
)
nombre_contable = contable.groupby("clientid")["clientname"].first()
saldos["tipo"] = saldos["clientid"].map(clasif_map).fillna("Otro")

# ---------------------------------------------------------------------------
# Emparejamiento de movimientos uno a uno (paso 5) para marcar estado por movimiento
# ---------------------------------------------------------------------------

def matchear(cc_df, cb_df, tol_dias=5, tol_importe=1.0, fuzz_th=70):
    """Devuelve sets de indices emparejados por proveedor."""
    match_cc = {}
    match_cb = {}
    for cid, gcc in cc_df.groupby("clientid"):
        gcb = cb_df[cb_df["clientid"] == cid]
        usados_cb = set()
        matched_cc, matched_cb = set(), set()
        for idx_cc, rcc in gcc.iterrows():
            mejor_punt = -1
            mejor_idx = None
            for idx_cb, rcb in gcb.iterrows():
                if idx_cb in usados_cb:
                    continue
                if pd.isna(rcc["fecha"]) or pd.isna(rcb["fecha"]):
                    continue
                if abs((rcc["fecha"] - rcb["fecha"]).days) > tol_dias:
                    continue
                if abs(abs(rcc["importe"]) - abs(rcb["totalprecio"])) > tol_importe:
                    continue
                txt_cc = str(rcc["referenciatexto"]) if pd.notna(rcc["referenciatexto"]) else ""
                txt_cb = str(rcb["referenciatexto"]) if pd.notna(rcb["referenciatexto"]) else ""
                punt = fuzz.token_set_ratio(txt_cc, txt_cb) if (txt_cc and txt_cb) else 0
                if punt > mejor_punt:
                    mejor_punt, mejor_idx = punt, idx_cb
            if mejor_idx is not None and mejor_punt >= fuzz_th:
                matched_cc.add(idx_cc)
                matched_cb.add(mejor_idx)
                usados_cb.add(mejor_idx)
        match_cc[cid] = matched_cc
        match_cb[cid] = matched_cb
    return match_cc, match_cb

cc_mov = ctacte[["clientid", "fecha", "referenciatexto", "haber", "debe", "saldo_acumulado", "id", "flows"]].copy()
cc_mov["importe"] = cc_mov["haber"].fillna(0) - cc_mov["debe"].fillna(0)

match_cc, match_cb = matchear(cc_mov, cb_dedup)

# ---------------------------------------------------------------------------
# GRAFICOS -> base64 para embeker en HTML
# ---------------------------------------------------------------------------
plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "#FAFAFA",
                     "axes.grid": True, "grid.alpha": 0.3})

def fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode()

def peso_mill(x, _): return f"{x/1e6:.0f}M"

# G1: categorias
cat_a = int((saldos["diferencia"].abs() > 1).sum())
cat_c = int((saldos["diferencia"].abs() <= 1).sum())
fig, ax = plt.subplots(figsize=(6, 4))
ax.pie([cat_a, cat_c],
       labels=[f"A) No cuadra\n{cat_a} ({cat_a/(cat_a+cat_c)*100:.1f}%)",
               f"C) Conciliado\n{cat_c} ({cat_c/(cat_a+cat_c)*100:.1f}%)"],
       colors=["#d9534f", "#5cb85c"], startangle=90, counterclock=False,
       textprops={"fontsize": 10})
ax.set_title("Distribución por categoría", fontweight="bold")
g1 = fig_to_b64(fig)

# G2: alcance
fig, ax = plt.subplots(figsize=(6, 3.5))
bars = ax.bar(["En cta cte\n(analizados)", "Contable\nfuera de alcance"],
              [len(saldos), len(fuera_df)], color=["#5bc0de", "#f0ad4e"])
ax.bar_label(bars, fontsize=10)
ax.set_title("Entidades en cta cte vs clientids fuera de alcance", fontweight="bold")
g2 = fig_to_b64(fig)

# G3: top 10
top10 = saldos.reindex(saldos["diferencia"].abs().sort_values(ascending=False).index).head(10).iloc[::-1]
fig, ax = plt.subplots(figsize=(8, 5))
colors = ["#d9534f" if v < 0 else "#5cb85c" for v in top10["diferencia"]]
labels = [n if len(n) <= 30 else n[:27] + "..." for n in top10["clientname"]]
ax.barh(labels, top10["diferencia"] / 1e6, color=colors)
ax.xaxis.set_major_formatter(FuncFormatter(peso_mill))
ax.set_title("Top 10 mayores diferencias de saldo", fontweight="bold")
ax.set_xlabel("Millones $")
g3 = fig_to_b64(fig)

# G4: patron duplicacion
grp_sizes = contable_prov.groupby(dedup_cols).size()
dist = grp_sizes.value_counts().sort_index()
fig, ax = plt.subplots(figsize=(6, 3.8))
b = ax.bar([str(x) for x in dist.index], dist.values, color="#5cb85c")
ax.bar_label(b, fontsize=8)
ax.set_title("Duplicación en el mayor contable", fontweight="bold")
ax.set_xlabel("Filas por grupo")
ax.set_ylabel("Grupos")
g4 = fig_to_b64(fig)

# ---------------------------------------------------------------------------
# BASE DE DATOS DE MOVIMIENTOS POR PROVEEDOR (para el selector JS)
# ---------------------------------------------------------------------------

def isnan(v): return v is None or (isinstance(v, float) and np.isnan(v))

# Fecha de corte del reporte = fecha maxima de movimientos (consistente para
# todas las ventanas). Las ventanas "1M/3M/6M/12M" son los ultimos N meses
# previos a esa fecha de corte.
from dateutil.relativedelta import relativedelta as _rd
fecha_corte = ctacte["fecha"].max()
window_meses = [1, 3, 6, 12]

def _saldo_cc_ventana(g, corte_inicio, corte_fin):
    """Saldo de cierre de cta cte dentro de la ventana = ultimo saldo_acumulado
    con fecha <= corte_fin (y >= corte_inicio). Si no hay mov, NaN."""
    sub = g[(g["fecha"] >= corte_inicio) & (g["fecha"] <= corte_fin)]
    if sub.empty:
        return None
    return float(sub.iloc[-1]["saldo_acumulado"])

def _suma_cb_ventana(cb_g, corte_inicio, corte_fin):
    """Suma de totalprecio (dedup) de movimientos contable dentro de la ventana."""
    sub = cb_g[(cb_g["fecha"] >= corte_inicio) & (cb_g["fecha"] <= corte_fin)]
    return float(sub["totalprecio"].sum())

prov_data = {}
for cid in sorted(saldos["clientid"].tolist()):
    row = saldos[saldos["clientid"] == cid].iloc[0]
    nombre = str(row["clientname"])
    tipo = str(row["tipo"])
    saldo = 0 if isnan(row["saldo_cliente"]) else row["saldo_cliente"]
    suma_cb = 0 if isnan(row["sum_totalprecio"]) else row["sum_totalprecio"]
    dif = 0 if isnan(row["diferencia"]) else row["diferencia"]
    dif_pct = row["diferencia_pct"]
    dif_pct = 0 if isnan(dif_pct) else dif_pct
    categoria = str(row["categoria"])

    # Movimientos cta cte (para ventanas)
    g_full = cc_mov[cc_mov["clientid"] == cid].sort_values("fecha")
    cb_full = cb_dedup[cb_dedup["clientid"] == cid]

    # Indicadores por ventana temporal (1, 3, 6, 12 meses)
    ventanas = {}
    for nm in window_meses:
        inicio = fecha_corte - _rd(months=nm)
        saldo_cc_w = _saldo_cc_ventana(g_full, inicio, fecha_corte)
        suma_cb_w = _suma_cb_ventana(cb_full, inicio, fecha_corte)
        ventanas[str(nm)] = {
            "saldo_cc": saldo_cc_w,
            "suma_cb": suma_cb_w,
        }

    # Movimientos cta cte
    movs_cc = []
    g = g_full
    matched = match_cc.get(cid, set())
    for _, m in g.iterrows():
        monto = 0 if isnan(m["importe"]) else m["importe"]
        haber = 0 if isnan(m["haber"]) else m["haber"]
        debe = 0 if isnan(m["debe"]) else m["debe"]
        saldo_ac = 0 if isnan(m["saldo_acumulado"]) else m["saldo_acumulado"]
        fecha = m["fecha"].strftime("%Y-%m-%d") if pd.notna(m["fecha"]) else ""
        movs_cc.append({
            "fecha": fecha,
            "referencia": str(m["referenciatexto"]) if pd.notna(m["referenciatexto"]) else "",
            "tipo": "Haber (Factura/Ingreso)" if monto > 0 else ("Debe (Pago/Retiro)" if monto < 0 else "Cero"),
            "haber": haber,
            "debe": debe,
            "importe": monto,
            "saldo_acum": saldo_ac,
            "flows": str(m["flows"]) if pd.notna(m["flows"]) else "",
            "match": m.name in matched,
        })

    # Movimientos contable dedup
    movs_cb = []
    h = cb_dedup[cb_dedup["clientid"] == cid].sort_values("fecha")
    matched_cb = match_cb.get(cid, set())
    for _, m in h.iterrows():
        tp = 0 if isnan(m["totalprecio"]) else m["totalprecio"]
        ti = 0 if isnan(m["totalimpuestos"]) else m["totalimpuestos"]
        fecha = m["fecha"].strftime("%Y-%m-%d") if pd.notna(m["fecha"]) else ""
        movs_cb.append({
            "fecha": fecha,
            "referencia": str(m["referenciatexto"]) if pd.notna(m["referenciatexto"]) else "",
            "totalprecio": tp,
            "totalimpuestos": ti,
            "cuentacontable": str(m["cuentacontable"]) if pd.notna(m["cuentacontable"]) else "",
            "match": m.name in matched_cb,
        })

    prov_data[str(cid)] = {
        "clientid": int(cid),
        "nombre": nombre,
        "tipo": tipo,
        "saldo": saldo,
        "suma_cb": suma_cb,
        "diferencia": dif,
        "diferencia_pct": dif_pct,
        "categoria": categoria,
        "ventanas": ventanas,
        "n_cc": len(movs_cc),
        "n_cb": len(movs_cb),
        "huerf_cc": len([m for m in movs_cc if not m["match"]]),
        "huerf_cb": len([m for m in movs_cb if not m["match"]]),
        "movs_cc": movs_cc,
        "movs_cb": movs_cb,
    }

import json
prov_json = json.dumps(prov_data, ensure_ascii=False)

# ---------------------------------------------------------------------------
# RESUMEN para el HTML
# ---------------------------------------------------------------------------
tot_mov_cc = len(cc_mov)
tot_mov_cb = len(cb_dedup)
mont_dif = saldos["diferencia"].abs().sum()

# Variables usadas por el template HTML
total_proveedores = len(saldos)
n_clientes = int((saldos["tipo"] == "Cliente").sum())
n_provs = int((saldos["tipo"] == "Proveedor").sum())
tot = len(saldos)
cat_a = int((saldos["diferencia"].abs() > 1).sum())
cat_c = int((saldos["diferencia"].abs() <= 1).sum())
monto_abs = saldos["diferencia"].abs().sum()
fecha_reporte = pd.Timestamp.now().strftime("%d/%m/%Y %H:%M")

# ---------------------------------------------------------------------------
# ESCRITURA DEL HTML
# ---------------------------------------------------------------------------
html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conciliación de Proveedores</title>
<style>
:root {{
  --azul:#2F5496; --rojo:#d9534f; --verde:#5cb85c; --ambar:#f0ad4e; --gris:#f5f6fa;
}}
* {{ box-sizing:border-box; }}
body {{ font-family:'Segoe UI',Arial,sans-serif; margin:0; background:#eef1f5; color:#222; }}
header {{ background:linear-gradient(135deg,var(--azul),#1d3a6e); color:#fff; padding:26px 36px; }}
header h1 {{ margin:0; font-size:24px; }}
header p {{ margin:6px 0 0; opacity:.9; font-size:13px; }}
.wrap {{ max-width:1200px; margin:0 auto; padding:20px 24px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin:22px 0; }}
.kpi {{ background:#fff; border-radius:12px; padding:16px 18px; box-shadow:0 2px 8px rgba(0,0,0,.06); border-left:5px solid var(--azul); }}
.kpi .val {{ font-size:22px; font-weight:800; }}
.kpi .lbl {{ font-size:12px; color:#666; margin-top:2px; }}
.kpi.rojo {{ border-left-color:var(--rojo); }} .kpi.verde {{ border-left-color:var(--verde); }}
.kpi.ambar {{ border-left-color:var(--ambar); }} .kpi.ciano {{ border-left-color:#5bc0de; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
.panel {{ background:#fff; border-radius:12px; padding:16px; box-shadow:0 2px 8px rgba(0,0,0,.06); }}
.panel h3 {{ margin:0 0 10px; font-size:15px; color:var(--azul); }}
table.tabla {{ width:100%; border-collapse:collapse; font-size:13px; }}
table.tabla th {{ background:var(--azul); color:#fff; padding:8px; text-align:left; }}
table.tabla td {{ padding:8px; border-bottom:1px solid #eee; }}
tr:nth-child(even) td {{ background:#fafbfc; }}
.sel {{ width:100%; padding:10px; font-size:14px; border:1px solid #ccc; border-radius:8px; margin:10px 0 0; }}
.picker {{ position:sticky; top:0; background:#fff; padding:14px 24px; box-shadow:0 2px 10px rgba(0,0,0,.1); z-index:10; }}
.picker h2 {{ margin:0 0 6px; font-size:16px; color:var(--azul); }}
.fichas {{ display:flex; gap:14px; margin:14px 0; flex-wrap:wrap; }}
.ficha {{ background:#fff; border-radius:10px; padding:12px 16px; min-width:160px; border:1px solid #e3e6ea; }}
.ficha .v {{ font-size:18px; font-weight:700; }} .ficha .l {{ font-size:11px; color:#777; }}
.badge {{ display:inline-block; padding:3px 10px; border-radius:20px; color:#fff; font-size:12px; font-weight:600; }}
.b-ok {{ background:var(--verde); }} .b-bad {{ background:var(--rojo); }} .b-ambar {{ background:var(--ambar); }}
.mov-tabs {{ display:flex; gap:6px; margin:10px 0; }}
.mov-tabs button {{ padding:8px 16px; border:1px solid #ccc; background:#fff; cursor:pointer; border-radius:6px; font-size:13px; }}
.mov-tabs button.active {{ background:var(--azul); color:#fff; border-color:var(--azul); }}
.mov-section {{ display:none; }} .mov-section.active {{ display:block; }}
.tag {{ padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; }}
.tag-h {{ background:#d4edda; color:#155724; }} .tag-d {{ background:#f8d7da; color:#721c24; }}
.matched {{ background:#eafaf1 !important; }} .notmatched {{ background:#fff0f0 !important; }}
.footer {{ text-align:center; color:#999; font-size:12px; padding:24px 0; }}
.toolbar {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:10px; }}
.toolbar input[type=text] {{ flex:1; min-width:220px; padding:8px 10px; border:1px solid #ccc; border-radius:6px; font-size:13px; }}
.toolbar select, .toolbar input[type=date] {{ padding:7px 8px; border:1px solid #ccc; border-radius:6px; font-size:13px; }}
.toolbar .btndir {{ padding:7px 14px; border:1px solid var(--azul); background:#fff; color:var(--azul); border-radius:6px; font-weight:700; cursor:pointer; }}
.toolbar .btndir:hover {{ background:var(--azul); color:#fff; }}
.toolbar .sep {{ color:#888; }}
.rowcount {{ font-size:12px; color:#666; margin:6px 2px; }}
.ventanas {{ background:#fff; border-radius:10px; padding:14px 16px; margin:12px 0; border:1px solid #e3e6ea; }}
.ventanas h3 {{ margin:0 0 10px; font-size:14px; color:var(--azul); }}
.tabla-v {{ max-width:620px; font-size:13px; }}
@media (max-width:800px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
  <h1>Conciliación Cuenta Corriente vs Cuenta Contable — Clientes y Proveedores</h1>
  <p>Reporte integral interactivo · Movimientos por entidad · Referencias, fechas e importes</p>
</header>

<div class="wrap">
  <!-- KPIs -->
  <div class="kpis">
    <div class="kpi"><div class="val">{total_proveedores}</div><div class="lbl">Entidades en cta cte</div></div>
    <div class="kpi ciano"><div class="val">{n_clientes}</div><div class="lbl">Clientes</div></div>
    <div class="kpi"><div class="val">{n_provs}</div><div class="lbl">Proveedores</div></div>
    <div class="kpi rojo"><div class="val">{cat_a} <small>({cat_a/tot*100:.0f}%)</small></div><div class="lbl">No cuadra saldo</div></div>
    <div class="kpi verde"><div class="val">{cat_c} <small>({cat_c/tot*100:.0f}%)</small></div><div class="lbl">Conciliado</div></div>
    <div class="kpi ambar"><div class="val">{len(fuera_df)}</div><div class="lbl">Clientids fuera de alcance</div></div>
    <div class="kpi ciano"><div class="val">{monto_abs:,.0f}</div><div class="lbl">Suma diferencias absolutas ($)</div></div>
  </div>

  <!-- Graficos -->
  <div class="grid2">
    <div class="panel"><h3>Categorías de conciliación</h3><img src="{g1}" style="width:100%"></div>
    <div class="panel"><h3>Proveedores vs fuera de alcance</h3><img src="{g2}" style="width:100%"></div>
    <div class="panel"><h3>Top 10 mayores diferencias de saldo</h3><img src="{g3}" style="width:100%"></div>
    <div class="panel"><h3>Duplicación en el mayor contable</h3><img src="{g4}" style="width:100%"></div>
  </div>

  <!-- Selector de entidad -->
  <div class="picker">
    <h2>Movimientos por entidad (cliente / proveedor)</h2>
    <select id="provSel" class="sel" onchange="loadProv()"></select>
    <div class="toolbar">
      <input type="text" id="searchRef" placeholder="Buscar por referencia..." oninput="render()">
      <select id="sortBy" onchange="render()">
        <option value="fecha">Ordenar por fecha</option>
        <option value="flujo">Ordenar por flujo</option>
      </select>
      <button id="sortDir" class="btndir" onclick="toggleDir()">Asc</button>
      <input type="date" id="dateFrom" title="Desde" onchange="render()">
      <span class="sep">a</span>
      <input type="date" id="dateTo" title="Hasta" onchange="render()">
    </div>
  </div>

  <div id="detail" style="margin-top:14px"></div>
</div>

<div class="footer">Reporte generado automáticamente · {fecha_reporte}</div>

<script>
const PROV = {prov_json};

function fmt(n, dec=0) {{
  if (n === null || n === undefined || isNaN(n)) return "0";
  return Number(n).toLocaleString("es-AR", {{minimumFractionDigits:dec, maximumFractionDigits:dec}});
}}

// Poblar selector
let currentTab = 0;
let sortDir = 1; // 1 = asc, -1 = desc

(function(){{
  const sel = document.getElementById("provSel");
  const ids = Object.keys(PROV).sort((a,b)=>PROV[a].nombre.localeCompare(PROV[b].nombre));
  ids.forEach(id=>{{
    const o=document.createElement("option");
    o.value=id;
    o.text = '['+PROV[id].tipo+'] '+PROV[id].nombre + " (id "+PROV[id].clientid+")";
    sel.appendChild(o);
  }});
  loadProv();
}})();

function loadProv(){{
  currentTab = 0;
  document.getElementById("searchRef").value = "";
  document.getElementById("dateFrom").value = "";
  document.getElementById("dateTo").value = "";
  document.getElementById("sortBy").value = "fecha";
  sortDir = 1;
  document.getElementById("sortDir").textContent = "Asc";
  render();
}}

function toggleDir(){{
  sortDir *= -1;
  document.getElementById("sortDir").textContent = sortDir === 1 ? "Asc" : "Desc";
  render();
}}

function bcat(cat){{
  return cat==="Conciliado" ? '<span class="badge b-ok">Conciliado</span>' : '<span class="badge b-bad">No cuadra</span>';
}}

function fechaFiltroOK(m){{
  const from = document.getElementById("dateFrom").value;
  const to = document.getElementById("dateTo").value;
  if(!m.fecha) return !from && !to;
  if(from && m.fecha < from) return false;
  if(to && m.fecha > to) return false;
  return true;
}}

function refFilter(m){{
  const q = document.getElementById("searchRef").value.trim().toLowerCase();
  if(!q) return true;
  return (m.referencia || "").toLowerCase().includes(q);
}}

// Devuelve copia filtrada + ordenada de la lista segun controles
function prepList(list){{
  let out = list.filter(m => fechaFiltroOK(m) && refFilter(m));
  const by = document.getElementById("sortBy").value;
  out = out.slice();
  if(by === "fecha"){{
    out.sort((a,b)=>{{
      if(!a.fecha && !b.fecha) return 0;
      if(!a.fecha) return 1;
      if(!b.fecha) return -1;
      return (a.fecha < b.fecha ? -1 : a.fecha > b.fecha ? 1 : 0) * sortDir;
    }});
  }} else if(by === "flujo"){{
    out.sort((a,b)=>{{
      const fa = (a.flows||"");
      const fb = (b.flows||"");
      const c = fa.localeCompare(fb);
      return c * sortDir;
    }});
  }}
  return out;
}}

function movRowCC(m){{
  const cls = m.match ? "matched" : "notmatched";
  const tag = m.tipo && m.tipo.startsWith("Haber") ? '<span class="tag tag-h">Haber</span>' : '<span class="tag tag-d">'+(m.tipo||"")+'</span>';
  return '<tr class="'+cls+'"><td>'+m.fecha+'</td><td>'+tag+'</td><td>'+m.referencia+'</td>'+
         '<td style="text-align:right">'+fmt(m.haber)+'</td><td style="text-align:right">'+fmt(m.debe)+'</td>'+
         '<td style="text-align:right">'+fmt(m.importe)+'</td><td style="text-align:right">'+fmt(m.saldo_acum)+'</td>'+
         '<td>'+m.flows+'</td><td>'+(m.match?'<span class="badge b-ok">Encontrado</span>':'<span class="badge b-bad">Huérfano</span>')+'</td></tr>';
}}

function movRowCB(m){{
  const cls = m.match ? "matched" : "notmatched";
  return '<tr class="'+cls+'"><td>'+m.fecha+'</td><td>'+m.referencia+'</td>'+
         '<td style="text-align:right">'+fmt(m.totalprecio)+'</td><td style="text-align:right">'+fmt(m.totalimpuestos)+'</td>'+
         '<td>'+m.cuentacontable+'</td>'+
         '<td>'+(m.match?'<span class="badge b-ok">Encontrado</span>':'<span class="badge b-bad">Huérfano</span>')+'</td></tr>';
}}

function ventanasHTML(p){{
  const rows = [1,3,6,12].map(m=>{{
    const v = (p.ventanas || {{}})[""+m] || {{}};
    const cc = (v.saldo_cc===null || v.saldo_cc===undefined) ? "-" : fmt(v.saldo_cc);
    const cb = (v.suma_cb===null || v.suma_cb===undefined) ? "-" : fmt(v.suma_cb);
    return '<tr><td style="text-align:center">'+m+' mes'+(m>1?'es':'')+'</td>'+
           '<td style="text-align:right">'+cc+'</td>'+
           '<td style="text-align:right">'+cb+'</td></tr>';
  }}).join("");
  return '<div class="ventanas"><h3>Indicadores por período (saldo cierre cta cte / suma contable)</h3>'+
         '<table class="tabla tabla-v" data-excel-table data-excel-title="Indicadores por Periodo"><thead><tr>'+
         '<th>Período</th><th>Saldo cta cte (cierre)</th><th>Suma contable</th>'+
         '</tr></thead><tbody>'+rows+'</tbody></table></div>';
}}

function render(){{
  const id = document.getElementById("provSel").value;
  const p = PROV[id];
  if(!p) return;
  const ccFiltered = prepList(p.movs_cc);
  const cbFiltered = prepList(p.movs_cb);
  const ccHeader = '<thead><tr><th>Fecha</th><th>Tipo</th><th>Referencia</th><th>Haber</th><th>Debe</th><th>Importe</th><th>Saldo Acum</th><th>Flujo</th><th>Estado</th></tr></thead>';
  const cbHeader = '<thead><tr><th>Fecha</th><th>Referencia</th><th>Total Precio</th><th>Impuestos</th><th>Cuenta Contable</th><th>Estado</th></tr></thead>';
  const difPct = (p.diferencia_pct !== 0 && !isNaN(p.diferencia_pct)) ? p.diferencia_pct.toFixed(1)+"%" : "-";
  const html =
    '<div class="fichas">'+
      '<div class="ficha"><div class="v">'+p.tipo+'</div><div class="l">Tipo de entidad</div></div>'+
      '<div class="ficha"><div class="v">'+fmt(p.saldo)+'</div><div class="l">Saldo cta cte</div></div>'+
      '<div class="ficha"><div class="v">'+fmt(p.suma_cb)+'</div><div class="l">Suma contable</div></div>'+
      '<div class="ficha"><div class="v">'+fmt(p.diferencia)+'</div><div class="l">Diferencia $</div></div>'+
      '<div class="ficha"><div class="v">'+difPct+'</div><div class="l">Diferencia %</div></div>'+
      '<div class="ficha"><div class="v">'+p.huerf_cc+' / '+p.n_cc+'</div><div class="l">Mov cta cte huérfanos</div></div>'+
      '<div class="ficha"><div class="v">'+p.huerf_cb+' / '+p.n_cb+'</div><div class="l">Mov contable huérfanos</div></div>'+
      '<div class="ficha"><div class="v">'+bcat(p.categoria)+'</div><div class="l">Estado</div></div>'+
    '</div>'+
    ventanasHTML(p)+
    '<div class="mov-tabs">'+
      '<button id="tb-cc" class="'+(currentTab===0?'active':'')+'" onclick="setTab(0)">Cuenta Corriente ('+(p.n_cc)+')</button>'+
      '<button id="tb-cb" class="'+(currentTab===1?'active':'')+'" onclick="setTab(1)">Mayor Contable ('+(p.n_cb)+')</button>'+
    '</div>'+
    '<div id="sec-cc" class="mov-section'+(currentTab===0?' active':'')+'"><table id="current-cc-table" class="tabla" data-excel-table data-excel-title="Cuenta Corriente" data-excel-all-source="all-cc-table">'+
      ccHeader+'<tbody>'+ccFiltered.map(movRowCC).join("")+
      '</tbody></table>'+
      '<div class="rowcount">'+ccFiltered.length+' de '+p.movs_cc.length+' movimientos</div>'+
      '<table id="all-cc-table" class="tabla" style="display:none">'+ccHeader+'<tbody>'+p.movs_cc.map(movRowCC).join("")+
      '</tbody></table></div>'+
    '<div id="sec-cb" class="mov-section'+(currentTab===1?' active':'')+'"><table id="current-cb-table" class="tabla" data-excel-table data-excel-title="Mayor Contable" data-excel-all-source="all-cb-table">'+
      cbHeader+'<tbody>'+cbFiltered.map(movRowCB).join("")+
      '</tbody></table>'+
      '<div class="rowcount">'+cbFiltered.length+' de '+p.movs_cb.length+' movimientos</div>'+
      '<table id="all-cb-table" class="tabla" style="display:none">'+cbHeader+'<tbody>'+p.movs_cb.map(movRowCB).join("")+
      '</tbody></table></div>';
  document.getElementById("detail").innerHTML = html;
}}

function setTab(which){{
  currentTab = which;
  render();
}}
</script>
<script src="assets/export_excel.js"></script>
</body>
</html>
"""

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Reporte HTML generado: {OUT_HTML}")
print(f"  Proveedores: {total_proveedores}, Mov cta cte: {tot_mov_cc}, Mov contable dedup: {tot_mov_cb}")
