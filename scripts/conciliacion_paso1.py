import pandas as pd
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- PASO 1: Carga de CSVs ---
print("=" * 80)
print("PASO 1: CARGA DE CSVs")
print("=" * 80)

# Cuenta corriente proveedores
path_ctacte = os.path.join(BASE, "cta cte - Proveedores.csv")
ctacte = pd.read_csv(path_ctacte, encoding="utf-8")
print(f"\n--- Cuenta Corriente Proveedores ---")
print(f"Filas: {ctacte.shape[0]}, Columnas: {ctacte.shape[1]}")
print(f"\nColumnas: {list(ctacte.columns)}")
print(f"\nDtypes:\n{ctacte.dtypes}")
print(f"\nPrimeras 5 filas:")
print(ctacte.head().to_string())

# Mayor contable proveedores
path_contable = os.path.join(BASE, "registro cta ctble - Proveedores - registro cta ctble - Proveedores.csv")
contable = pd.read_csv(path_contable, encoding="utf-8")
print(f"\n\n--- Mayor Contable Proveedores ---")
print(f"Filas: {contable.shape[0]}, Columnas: {contable.shape[1]}")
print(f"\nColumnas: {list(contable.columns)}")
print(f"\nDtypes:\n{contable.dtypes}")
print(f"\nPrimeras 5 filas:")
print(contable.head().to_string())

# Guardar para uso posterior
ctacte.to_pickle(os.path.join(BASE, "_ctacte.pkl"))
contable.to_pickle(os.path.join(BASE, "_contable.pkl"))
print("\n\nArchivos guardados para pasos posteriores.")
