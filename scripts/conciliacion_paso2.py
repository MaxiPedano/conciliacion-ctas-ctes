import pandas as pd
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
contable = pd.read_pickle(os.path.join(BASE, "_contable.pkl"))

print("=" * 80)
print("PASO 2: ANÁLISIS DE DUPLICADOS EN ARCHIVO CONTABLE")
print("=" * 80)

# Normalizar fecha a string para agrupar bien
contable["fecha"] = contable["fecha"].astype(str).str.strip()

# Clave de deduplicación: clientid + fecha + referenciatexto + totalprecio
dup_keys = ["clientid", "fecha", "referenciatexto", "totalprecio"]

# Contar filas por grupo
grp = contable.groupby(dup_keys).size().reset_index(name="cant_filas")

print(f"\nTotal de grupos únicos (clientid + fecha + referenciatexto + totalprecio): {len(grp)}")
print(f"\nDistribución de filas por grupo:")
dist = grp["cant_filas"].value_counts().sort_index()
for n, cant in dist.items():
    print(f"  {n} filas por grupo: {cant} grupos")

# Verificar si totalprecio es siempre idéntico dentro de cada grupo
print("\n--- Verificación de totalprecio dentro de cada grupo ---")
grp_summ = contable.groupby(dup_keys)["totalprecio"].agg(["min", "max", "count"])
diff = grp_summ[grp_summ["min"] != grp_summ["max"]]
if len(diff) == 0:
    print("OK: totalprecio es SIEMPRE idéntico dentro de cada grupo duplicado.")
else:
    print(f"ALERTA: {len(diff)} grupos tienen totalprecio DISTINTO entre filas del mismo grupo:")
    print(diff.head(20).to_string())

# Verificar si totalimpuestos varía dentro de cada grupo
print("\n--- Verificación de totalimpuestos dentro de cada grupo ---")
grp_imp = contable.groupby(dup_keys)["totalimpuestos"].agg(["min", "max"])
diff_imp = grp_imp[grp_imp["min"] != grp_imp["max"]]
if len(diff_imp) == 0:
    print("OK: totalimpuestos es SIEMPRE idéntico dentro de cada grupo duplicado.")
else:
    print(f"ALERTA: {len(diff_imp)} grupos tienen totalimpuestos DISTINTO entre filas del mismo grupo:")
    print(diff_imp.head(20).to_string())

# Verificar si cuentacontable varía dentro de cada grupo
print("\n--- Verificación de cuentacontable dentro de cada grupo ---")
grp_cc = contable.groupby(dup_keys)["cuentacontable"].nunique().reset_index(name="cc_unicas")
diff_cc = grp_cc[grp_cc["cc_unicas"] > 1]
if len(diff_cc) == 0:
    print("OK: cuentacontable es SIEMPRE idéntica dentro de cada grupo duplicado.")
else:
    print(f"INFORMACIÓN: {len(diff_cc)} grupos tienen cuentacontable DISTINTA entre filas del mismo grupo:")
    # Mostrar ejemplos
    ejemplos = contable[contable.set_index(dup_keys).index.isin(
        diff_cc.set_index(dup_keys).index
    )].sort_values(dup_keys)
    print(ejemplos[dup_keys + ["cuentacontable", "categoriaid"]].head(30).to_string())

# Verificar si categoriaid varía (esperado: sí, es lo que genera los duplicados)
print("\n--- Verificación de categoriaid dentro de cada grupo ---")
grp_cat = contable.groupby(dup_keys)["categoriaid"].nunique().reset_index(name="cat_unicas")
diff_cat = grp_cat[grp_cat["cat_unicas"] > 1]
print(f"Grupos con más de 1 categoriaid único: {len(diff_cat)} de {len(grp_cat)}")
print(f"(Esto genera los duplicados: mismos datos, distinto categoriaid)")

# Guardar el análisis de duplicados
dup_info = grp.copy()
dup_info.to_pickle(os.path.join(BASE, "_dup_info.pkl"))
contable.to_pickle(os.path.join(BASE, "_contable.pkl"))
print("\nPaso 2 completado.")
