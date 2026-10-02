#!/usr/bin/env python3
"""Reporte sintético de pagos extra POLICOR (mixto) para contabilidad.

Solo lectura de datos ya verificados; no consulta ni modifica la base.
"""
from pathlib import Path
import html

ROOT = Path(__file__).resolve().parents[1]

PAGOS = [
    ("17152", "22/05/2026", 300000000,
     "Pago FA 0013-00032601 Echeq GConDis (Condiseño)",
     "e-cheq",
     "La factura FA 0013-00032601 (ID 17151) es por $771.538,18; el excedente de $2.228.461,82 no tiene factura identificada."),
    ("19126", "05/06/2026", 150000000,
     "5-6 PAGO A CUENTA POLICOR",
     "3 cheques de $500.000 (MACRO 61104058 / 61104062 / 6110463)",
     "Cheques de JULIO CASAÑA endosados a POLICOR; sin recibo en el resumen del proveedor. Pago atípico."),
    ("20726", "03/07/2026", 50000000,
     "3/7/26 PAGO A POLICOR ECHEQ 68113314 CONDISEÑO (Condiseño)",
     "e-cheq 68113314",
     "Tiene cargo espejo ID 20725 por el mismo importe (FACTURA DE COMPRA); neto en cuenta corriente $0."),
    ("19405", "20/08/2026", 400000000,
     "20-8-26 PAGO A CUENTA CONDISEÑO (Condiseño)",
     "e-cheq emitido GALICIA",
     "Par espejo ID 19404 (Pago a cuenta, efecto $0). Mismo importe que el pago Avanzia 19407 del mismo día."),
    ("20286", "16/09/2026", 294880457,
     "16-9-26 PAGO A CUENTA CONDISEÑO (Condiseño)",
     "2 e-cheqs GALICIA: 73032178 $2.578.804,57 + 90000085 $370.000,00",
     "Par espejo ID 20283 (Pago a cuenta, efecto $0)."),
]
TOTAL = sum(p[2] for p in PAGOS)


def money(cents):
    s = f"{cents // 100:,}".replace(",", ".")
    return f"${s},{cents % 100:02d}"


def main():
    h = html.escape
    rows = "".join(
        "<tr>" + "".join(f"<td>{h(str(x))}</td>" for x in (rid, fecha, money(imp), ref)) + "</tr>"
        for rid, fecha, imp, ref, medio, obs in PAGOS)
    obs = "".join(
        f"<li><b>ID {h(rid)}</b> ({h(fecha)}, {money(imp)}) — {h(obs)} Medio: {h(medio)}.</li>"
        for rid, fecha, imp, ref, medio, obs in PAGOS)
    content = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>POLICOR — Pagos no identificados en el resumen del proveedor</title>
<style>body{{font:15px/1.5 'Segoe UI',sans-serif;background:#f3f6f8;color:#263238;margin:0}}main{{max-width:1100px;margin:auto;padding:24px}}header,section{{background:white;padding:24px;border-radius:12px;margin-bottom:18px}}header{{background:#39265e;color:white}}h1,h2{{margin-top:0}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:9px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}}th{{background:#72509a;color:white}}tr:nth-child(even){{background:#faf8fc}}.big{{font-size:22px;font-weight:bold}}.note{{background:#fff5e5;padding:16px}}a{{color:#72509a}}.wrap{{overflow:auto}}li{{overflow-wrap:anywhere}}@media(max-width:600px){{main{{padding:10px}}section,header{{padding:15px}}}}</style></head><body><main>
<header><h1>POLICOR — Pagos identificados en el estado de CONDISEÑO</h1><p>Complemento mixto (sin separar empresa) · 01/01/2026–01/10/2026 · Cliente 986 POLICOR · Flujo 10150 CAJA: Egresos.</p></header>
<section><h2>Resolución</h2><p class="big">{money(TOTAL)} en {len(PAGOS)} pagos — 100% identificados</p><p>Estos 5 pagos <b>no tenían recibo en el resumen de Avanzia</b> porque corresponden a <b>CONDISEÑO S.A.S. (16374)</b>: coinciden al centavo con los 6 recibos de su estado (Haber $11.948.804,57).</p>
<p><a href="reporte_conciliacion_condiseno.html">Ver conciliación CONDISEÑO (estado vs sistema)</a></p></section>
<section><h2>Detalle</h2>
<div class="wrap"><table><thead><tr><th>ID</th><th>Fecha</th><th>Importe</th><th>Referencia en sistema</th></tr></thead><tbody>{rows}<tr><th colspan="3">Total</th><th>{money(TOTAL)}</th></tr></tbody></table></div></section>
<section><h2>Observaciones</h2><ul>{obs}</ul></section>
<section><h2>Para verificar</h2><p class="note">1) Deja de estar pendiente el origen de los 5 pagos: son recibos del estado Condiseño. 2) Quedan pendientes las 8 facturas Condiseño por $6.645.083,02 sin cargo en el sistema. Datos solo de lectura; no se modificó la base.</p>
<a href="reporte_conciliacion_condiseno.html">Conciliación CONDISEÑO</a> · <a href="reporte_pagos_vs_facturas_policor.html">Pagos vs facturas (detalle)</a> · <a href="reporte_conciliacion_policor_pdf.html">Conciliación Avanzia</a> · <a href="index.html">Inicio</a></section></main></body></html>'''
    (ROOT / 'reporte_pagos_extra_policor.html').write_text(content, encoding='utf-8')
    print(f"OK {money(TOTAL)} en {len(PAGOS)} pagos -> reporte_pagos_extra_policor.html")


if __name__ == '__main__':
    main()
