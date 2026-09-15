# -*- coding: utf-8 -*-
"""
Conciliación Cuenta Corriente vs Cuenta Contable - Proveedores
Pasos 3 a 8 del prompt_conciliacion.md

Enfoque: priorizar la CONCILIACIÓN DE MOVIMIENTOS uno a uno (paso 5)
como núcleo del análisis, dado el hallazgo estructural de que el archivo
contable no contiene una cuenta de pasivo "Proveedores".
"""
import pandas as pd
import os
from rapidfuzz import fuzz

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# CARGA (paso 1, listo)
# ---------------------------------------------------------------------------
ctacte = pd.read_pickle(os.path.join(BASE, "_ctacte.pkl"))
contable = pd.read_pickle(os.path.join(BASE, "_contable.pkl"))

ctacte["fecha"] = pd.to_datetime(ctacte["fecha"], errors="coerce")
contable["fecha"] = pd.to_datetime(contable["fecha"], errors="coerce")
ctacte["clientid"] = ctacte["clientid"].astype("Int64")
contable["clientid"] = contable["clientid"].astype("Int64")

# ---------------------------------------------------------------------------
# PASO 3: Filtrar contable a clientids presentes en cta cte
# ---------------------------------------------------------------------------
ids_ctacte = set(ctacte["clientid"].unique())
contable_prov = contable[contable["clientid"].isin(ids_ctacte)].copy()

# Clientids del contable que NO están en cta cte (fuera de alcance)
ids_fuera = set(contable["clientid"].unique()) - ids_ctacte
fuera_df = contable[contable["clientid"].isin(ids_fuera)].drop_duplicates("clientid")[["clientid", "clientname"]].copy()
fuera_df.columns = ["clientid", "clientname"]

# ---------------------------------------------------------------------------
# PASO 2 (ya ejecutado) -> deduplicar el archivo contable
# Clave de dedup: (clientid, fecha, referenciatexto, totalprecio)
# El paso 2 confirmó que totalprecio es SIEMPRE idéntico dentro de cada grupo.
# Agrupar las cuentas contables de todas las filas del grupo para no perder info.
# ---------------------------------------------------------------------------
dedup_cols = ["clientid", "fecha", "referenciatexto", "totalprecio"]

def _agg_cc(group):
    cuentas = group.dropna().unique().tolist()
    return " | ".join(cuentas)

def _agg_imp(group):
    return group.dropna().max()

grp_meta = contable_prov.groupby(dedup_cols, as_index=False).agg(
    clientname=("clientname", "first"),
    totalimpuestos=("totalimpuestos", lambda s: s.max()),
    cuentacontable=("cuentacontable", _agg_cc),
    cuentas_count=("cuentacontable", "nunique"),
)
# Ahora las filas dedup (una por grupo)
cb_dedup = grp_meta.copy()

# ---------------------------------------------------------------------------
# PASO 4: Saldos por proveedor
# ---------------------------------------------------------------------------
# Saldo según CTA CTE: usar saldo_cliente (saldo final del proveedor).
# Verificar consistencia con saldo_acumulado del último movimiento.
ctacte_sorted = ctacte.sort_values(["clientid", "fecha"])
ctacte_last = ctacte_sorted.groupby("clientid").last().reset_index()

# CRITERIO DE SIGNO (documentado):
# - cta cte: "haber" = facturas/acreencia del proveedor (aumenta deuda que la
#   empresa debe pagar). "debe" = pagos/retiros (disminuye deuda). El saldo
#   final (saldo_cliente) es el saldo deudor/acreedor tal cual lo reporta la app.
# - contable: totalprecio registrado por cuenta de gasto/activo (el archivo no
#   trae la cuenta de pasivo "Proveedores"). Se toma el signo tal cual figura.
#   Como el contable acumula facturación histórica y netea pagos en otras
#   cuentas, la suma de totalprecio NO representa el saldo de pasivo. Por eso
#   el núcleo del análisis es la conciliación de movimientos (paso 5).
saldo_ctacte = ctacte_last[["clientid", "clientname", "saldo_cliente", "saldo_acumulado"]].copy()
saldo_ctacte["inconsistencia_ctacte"] = (saldo_ctacte["saldo_cliente"] - saldo_ctacte["saldo_acumulado"]).abs() > 1

# Saldo según contable (suma totalprecio dedup) - con advertencia estructural
cb_saldo = cb_dedup.groupby("clientid").agg(
    sum_totalprecio=("totalprecio", "sum"),
    n_mov_contable=("totalprecio", "count"),
).reset_index()

saldos = pd.merge(saldo_ctacte, cb_saldo, on="clientid", how="left")
saldos["sum_totalprecio"] = saldos["sum_totalprecio"].fillna(0)
saldos["n_mov_contable"] = saldos["n_mov_contable"].fillna(0)

# Diferencia (con advertencia estructural)
saldos["diferencia"] = saldos["saldo_cliente"] - saldos["sum_totalprecio"]
saldos["diferencia_pct"] = (saldos["diferencia"] / saldos["saldo_cliente"].replace(0, pd.NA)) * 100

# ---------------------------------------------------------------------------
# PASO 5: Conciliación de movimientos uno a uno (NÚCLEO)
# Criterios: fecha (±5 días) + importe (debe/haber de cta cte vs totalprecio
# dedup de contable) + similitud de texto (rapidfuzz, umbral >=70 como apoyo).
# ---------------------------------------------------------------------------

# Preparar movimientos de CTA CTE
cc_mov = ctacte[["clientid", "fecha", "referenciatexto", "haber", "debe", "saldo_acumulado", "id"]].copy()
cc_mov["importe"] = cc_mov["haber"].fillna(0) - cc_mov["debe"].fillna(0)
# importe > 0 = factura (haber), importe < 0 = pago (debe)
cc_mov["tipo"] = cc_mov["importe"].apply(lambda x: "factura" if x > 0 else ("pago" if x < 0 else "cero"))

# Preparar movimientos del CONTABLE dedup
cb_mov = cb_dedup[["clientid", "fecha", "referenciatexto", "totalprecio", "cuentacontable"]].copy()

# Para comparar importes con cta cte, el signo de totalprecio (que ya trae
# signo propio: positivo=deuda/gasto, negativo=reversa/credito) se mantiene.

def match_movimientos(cc_df, cb_df, tol_dias=5, tol_importe=1.0, fuzz_threshold=70):
    """
    Empareja movimientos de cta cte contra contable dedup por proveedor.
    Criterio: fecha (abs diff <= tol_dias) Y importe casi igual (tol $1)
    Y similitud de texto >= fuzz_threshold como señal de apoyo.
    Devuelve (emparejados_cc, huerfanos_cc, emparejados_cb, huerfanos_cb)
    """
    emparejados_cc, huerfanos_cc = [], []
    emparejados_cb, huerfanos_cb = [], []

    for cid, gcc in cc_df.groupby("clientid"):
        gcb = cb_df[cb_df["clientid"] == cid].copy()
        usados_cb = set()
        for _, rcc in gcc.iterrows():
            mejor_punt = -1
            mejor_idx = None
            for idx, rcb in gcb.iterrows():
                if idx in usados_cb:
                    continue
                # tolerancia de fecha
                if pd.isna(rcc["fecha"]) or pd.isna(rcb["fecha"]):
                    fecha_ok = False
                else:
                    fecha_ok = abs((rcc["fecha"] - rcb["fecha"]).days) <= tol_dias
                if not fecha_ok:
                    continue
                # tolerancia de importe (valor absoluto)
                importe_ok = abs(abs(rcc["importe"]) - abs(rcb["totalprecio"])) <= tol_importe
                if not importe_ok:
                    continue
                # similitud de texto (se�al de apoyo)
                txt_cc = str(rcc["referenciatexto"]) if pd.notna(rcc["referenciatexto"]) else ""
                txt_cb = str(rcb["referenciatexto"]) if pd.notna(rcb["referenciatexto"]) else ""
                punt = fuzz.token_set_ratio(txt_cc, txt_cb) if (txt_cc and txt_cb) else 0
                if punt > mejor_punt:
                    mejor_punt, mejor_idx = punt, idx
            if mejor_idx is not None and mejor_punt >= fuzz_threshold:
                emparejados_cc.append(rcc)
                emparejados_cb.append(gcb.loc[mejor_idx])
                usados_cb.add(mejor_idx)
            else:
                huerfanos_cc.append(rcc)
                origen = "cta_cte"
        # Registrar huérfanos del lado contable (no usados)
        for idx, rcb in gcb.iterrows():
            if idx not in usados_cb:
                rcb["_origen"] = "contable"
                huerfanos_cb.append(rcb)

    def _finalize(lista, origen):
        if not lista:
            return pd.DataFrame()
        df = pd.DataFrame(lista)
        if "_origen" not in df.columns:
            df["_origen"] = origen
        return df

    return (
        _finalize(emparejados_cc, "cta_cte"),
        _finalize(huerfanos_cc, "cta_cte"),
        _finalize(emparejados_cb, "contable"),
        _finalize(huerfanos_cb, "contable"),
    )

emp_cc, huerf_cc, emp_cb, huerf_cb = match_movimientos(cc_mov, cb_mov)

# ---------------------------------------------------------------------------
# PASO 6: Clasificación de proveedores en 3 categorías
# ---------------------------------------------------------------------------
# A) NO CUADRA - Diferencia de saldo: saldo cta cte != saldo contable
# B) MOVIMIENTOS NO COINCIDEN: proveedores con movimientos huérfanos
#    (aunque el saldo final cuadre)
# C) CONCILIADO - Al día: saldo cta cte = saldo contable (tol $1) Y todos
#    los movimientos matchean.

# Huérfanos por proveedor
huerf_cc["clientid"] = huerf_cc["clientid"].astype("Int64")
huerf_cb["clientid"] = huerf_cb["clientid"].astype("Int64")

huerf_cc_count = huerf_cc.groupby("clientid").size().rename("huerfanos_ctacte").reset_index()
huerf_cb_count = huerf_cb.groupby("clientid").size().rename("huerfanos_contable").reset_index()

clasif = saldos.merge(huerf_cc_count, on="clientid", how="left")
clasif = clasif.merge(huerf_cb_count, on="clientid", how="left")
clasif["huerfanos_ctacte"] = clasif["huerfanos_ctacte"].fillna(0)
clasif["huerfanos_contable"] = clasif["huerfanos_contable"].fillna(0)
clasif["total_huerfanos"] = clasif["huerfanos_ctacte"] + clasif["huerfanos_contable"]

# Nota estructural: el criterio de saldo siguiente usa suma de totalprecio,
# que por la advertencia NO es un saldo de pasivo. Por eso los que cuadran
# "por saldo" son aquellos donde ambos conceptos resultan iguales por
# casualidad estructural (facturación igual a saldo corrido). Se mantiene
# como lo pide el prompt, priorizando en el análisis la conciliación por
# movimientos (categoría B es la más relevante).
saldo_concilia = clasif["diferencia"].abs() <= 1
mov_concilia = clasif["total_huerfanos"] == 0

categoria = []
for _, r in clasif.iterrows():
    cid = r["clientid"]
    saldo_ok = abs(r["diferencia"]) <= 1
    mov_ok = r["total_huerfanos"] == 0
    if saldo_ok:
        if mov_ok:
            categoria.append("C) CONCILIADO - Al dia")
        else:
            categoria.append("B) MOVIMIENTOS NO COINCIDEN")
    else:
        categoria.append("A) NO CUADRA - Diferencia de saldo")

clasif["categoria"] = categoria

# ---------------------------------------------------------------------------
# PASO 7: Resumen ejecutivo
# ---------------------------------------------------------------------------
total_proveedores = len(clasif)
n_cat_c = (clasif["categoria"].str.startswith("C")).sum()
n_cat_b = (clasif["categoria"].str.startswith("B")).sum()
n_cat_a = (clasif["categoria"].str.startswith("A")).sum()

# Monto total de diferencias no conciliadas (sum abs de categoría A)
monto_no_concil = clasif.loc[clasif["categoria"].str.startswith("A"), "diferencia"].abs().sum()

# Top 10 proveedores con mayor diferencia en $
top10_mayor_diff = clasif.sort_values("diferencia", key=abs, ascending=False).head(10)

# ---------------------------------------------------------------------------
# PASO 8: Exportación a Excel
# ---------------------------------------------------------------------------
out = os.path.join(BASE, "informe_conciliacion_proveedores.xlsx")

# Hojas requeridas por el prompt:
# Resumen, Duplicados Detectados, No Cuadra - Saldo,
# Movimientos No Coinciden, Conciliado, Clientid Fuera de Alcance

# --- Hoja Resumen ---
resumen_rows = [
    ("Cantidad total de proveedores analizados", total_proveedores),
    ("Proveedores en categoria A (NO CUADRA - Diferencia de saldo)", f"{n_cat_a}  ({n_cat_a/total_proveedores*100:.1f}%)"),
    ("Proveedores en categoria B (MOVIMIENTOS NO COINCIDEN)", f"{n_cat_b}  ({n_cat_b/total_proveedores*100:.1f}%)"),
    ("Proveedores en categoria C (CONCILIADO - Al dia)", f"{n_cat_c}  ({n_cat_c/total_proveedores*100:.1f}%)"),
    ("Cantidad de clientid del contable fuera de alcance (no estan en cta cte)", len(fuera_df)),
    ("Monto total de diferencias no conciliadas (sum abs categoria A)", monto_no_concil),
    ("", ""),
    ("TOP 10 proveedores con mayor diferencia en $", ""),
]
for _, r in top10_mayor_diff.iterrows():
    resumen_rows.append((f"  {r['clientname']} (id {r['clientid']})", f"{r['diferencia']:,.2f}"))

resumen_df = pd.DataFrame(resumen_rows, columns=["Concepto", "Valor"])

# --- Hoja Duplicados Detectados (detallde paso 2) ---
# Re-construir distribución y filas duplicadas
dup_rows = []
for keys, group in contable_prov.groupby(dedup_cols):
    if len(group) > 1:
        dup_rows.append({
            "clientid": keys[0],
            "fecha": keys[1],
            "referenciatexto": keys[2],
            "totalprecio": keys[3],
            "cant_filas": len(group),
        })
dup_df = pd.DataFrame(dup_rows)
dup_df = dup_df.sort_values("cant_filas", ascending=False)
# Distribución de tamaño de grupos
dist_df = dup_df["cant_filas"].value_counts().reset_index().rename(
    columns={"index": "filas_por_grupo", "cant_filas": "n_grupos"})

# --- Hoja No Cuadra - Saldo (A) ---
no_cuadra = clasif[clasif["categoria"].str.startswith("A")].copy()
no_cuadra = no_cuadra.sort_values("diferencia", key=abs, ascending=False)
cols_no_cuadra = [
    "clientid", "clientname", "saldo_cliente", "sum_totalprecio",
    "diferencia", "diferencia_pct",
]
no_cuadra_out = no_cuadra[cols_no_cuadra].rename(columns={
    "saldo_cliente": "Saldo Cta Cte",
    "sum_totalprecio": "Saldo Contable (sum totalprecio)",
    "diferencia": "Diferencia $",
    "diferencia_pct": "Diferencia %",
})

# --- Hoja Movimientos No Coinciden (B) ---
mov_no_coin = clasif[clasif["categoria"].str.startswith("B")].copy()

# Detalle de movimientos huérfanos
detalle_huerfanos = []
if len(huerf_cc):
    for _, r in huerf_cc.iterrows():
        detalle_huerfanos.append({
            "clientid": r["clientid"],
            "clientname": clasif.loc[clasif["clientid"] == r["clientid"], "clientname"].iloc[0] if (clasif["clientid"] == r["clientid"]).any() else "",
            "fecha": r["fecha"],
            "referenciatexto": r["referenciatexto"],
            "importe": r["importe"],
            "origen": "cta_cte",
        })
for _, r in huerf_cb.iterrows():
    nm = clasif.loc[clasif["clientid"] == r["clientid"], "clientname"]
    detalle_huerfanos.append({
        "clientid": r["clientid"],
        "clientname": nm.iloc[0] if len(nm) else "",
        "fecha": r["fecha"],
        "referenciatexto": r["referenciatexto"],
        "importe": r["totalprecio"],
        "origen": "contable",
    })
detalle_huerfanos_df = pd.DataFrame(detalle_huerfanos)

mov_no_coin_resumen = mov_no_coin[["clientid", "clientname", "huerfanos_ctacte", "huerfanos_contable", "total_huerfanos"]].rename(columns={
    "huerfanos_ctacte": "Mov sin matchear (cta cte)",
    "huerfanos_contable": "Mov sin matchear (contable)",
    "total_huerfanos": "Total movimientos sin matchear",
})

# --- Hoja Conciliado (C) ---
conciliado = clasif[clasif["categoria"].str.startswith("C")][
    ["clientid", "clientname", "saldo_cliente"]
].rename(columns={"saldo_cliente": "Saldo actual"})

# --- Hoja Clientid Fuera de Alcance ---
fuera_df_out = fuera_df.copy()

with pd.ExcelWriter(out, engine="openpyxl") as writer:
    resumen_df.to_excel(writer, sheet_name="Resumen", index=False)
    dist_df.to_excel(writer, sheet_name="Duplicados Detectados", index=False, startrow=0)
    # Anotar distribución y luego detalle
    # Debajo de dist_df, escribir el detalle de grupos
    # (usar el mismo dataframe dup_df en columnas aparte)
    start_detail_row = len(dist_df) + 3
    dup_df.to_excel(writer, sheet_name="Duplicados Detectados", index=False, startrow=start_detail_row)

    no_cuadra_out.to_excel(writer, sheet_name="No Cuadra - Saldo", index=False)
    mov_no_coin_resumen.to_excel(writer, sheet_name="Movimientos No Coinciden", index=False, startrow=0)
    detalle_huerfanos_df.to_excel(writer, sheet_name="Movimientos No Coinciden", index=False, startrow=len(mov_no_coin_resumen)+3)
    conciliado.to_excel(writer, sheet_name="Conciliado", index=False)
    fuera_df_out.to_excel(writer, sheet_name="Clientid Fuera de Alcance", index=False)

# Ancho de columnas + headers bold en cada hoja
try:
    from openpyxl import load_workbook
    from openpyxl.styles import Font
    wb = load_workbook(out)
    bold = Font(bold=True)
    for ws in wb.worksheets:
        max_row = ws.max_row
        for cell in ws[1]:
            cell.font = bold
        for col in ws.columns:
            letter = col[0].column_letter
            max_len = 0
            for c in col:
                if c.value is not None:
                    max_len = max(max_len, len(str(c.value)))
            ws.column_dimensions[letter].width = min(max_len + 2, 60)
    wb.save(out)
except Exception as e:
    print(f"(Aviso: no se pudo formatear el excel: {e})")

# ---------------------------------------------------------------------------
# SALIDA EN CONSOLA (resumen)
# ---------------------------------------------------------------------------
print("=" * 80)
print("RESUMEN EJECUTIVO")
print("=" * 80)
print(f"Total proveedores analizados: {total_proveedores}")
print(f"  Categoria A (NO CUADRA - Diferencia de saldo): {n_cat_a} ({n_cat_a/total_proveedores*100:.1f}%)")
print(f"  Categoria B (MOVIMIENTOS NO COINCIDEN):        {n_cat_b} ({n_cat_b/total_proveedores*100:.1f}%)")
print(f"  Categoria C (CONCILIADO - Al dia):             {n_cat_c} ({n_cat_c/total_proveedores*100:.1f}%)")
print(f"Clientid del contable fuera de alcance: {len(fuera_df)}")
print(f"Monto total diferencias no conciliadas (cat A): {monto_no_concil:,.2f}")
print(f"\nTop 10 mayor diferencia en $:")
for _, r in top10_mayor_diff.iterrows():
    print(f"  {r['clientname']} (id {r['clientid']}): {r['diferencia']:,.2f}")

print(f"\nConciliación de movimientos:")
print(f"  Movimientos cta cte totales: {len(cc_mov)}")
print(f"    emparejados: {len(emp_cc)}, huerfanos: {len(huerf_cc)}")
print(f"  Movimientos contable (dedup) totales: {len(cb_mov)}")
print(f"    emparejados: {len(emp_cb)}, huerfanos: {len(huerf_cb)}")

print(f"\nExportado a: {out}")
