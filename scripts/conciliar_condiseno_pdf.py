#!/usr/bin/env python3
"""Conciliacion CONDISEÑO S.A.S. (cliente 16374) vs movimientos del sistema.

Estado cargado desde la imagen del proveedor (solo lectura, origen PDF sin archivo).
Mezcla: movimientos POLICOR (clientid 986) con referencia Condiseño, 2026.
Tolerancias: importe $0,02 (pagos exactos), $1,00 (facturas, difs menores),
fecha +-45 dias pagos, +-30 dias facturas. Sin separar empresa.
"""
import csv
import html
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fmt_date(value):
    y, m, d = str(value)[:10].split('-')
    return f"{d}/{m}/{y}"

# Estado del proveedor (imagen): vto, numero, comprobante, debe, haber
STATEMENT = [
    ("2026-04-14", "A:0013-00032096", "Factura de Ventas", 76029871, 0),
    ("2026-04-16", "A:0013-00032132", "Factura de Ventas", 76029871, 0),
    ("2026-04-21", "X:0010-00321132", "Recibo de Venta", 0, 300000000),
    ("2026-05-06", "A:0013-00032370", "Factura de Ventas", 4720800, 0),
    ("2026-05-22", "A:0013-00032601", "Factura de Ventas", 77153817, 0),
    ("2026-05-27", "A:0017-00002449", "Factura de Ventas", 66065641, 0),
    ("2026-06-08", "X:0010-00322340", "Recibo de Venta", 0, 150000000),
    ("2026-06-24", "A:0013-00032991", "Factura de Ventas", 92614913, 0),
    ("2026-07-02", "A:0000-00000403", "Nota de Débito de Venta", 50000000, 0),
    ("2026-07-03", "X:0010-00322913", "Recibo de Venta", 0, 50000000),
    ("2026-07-29", "A:0013-00033437", "Factura de Ventas", 125029700, 0),
    ("2026-08-19", "A:0013-00033708", "Factura de Ventas", 99395300, 0),
    ("2026-08-20", "X:0010-00323798", "Recibo de Venta", 0, 400000000),
    ("2026-08-25", "A:0013-00033799", "Factura de Ventas", 7297721, 0),
    ("2026-08-27", "A:0013-00033840", "Factura de Ventas", 118422000, 0),
    ("2026-08-27", "A:0013-00033842", "Factura de Ventas", 9660000, 0),
    ("2026-09-17", "X:0010-00324300", "Recibo de Venta", 0, 257880457),
    ("2026-09-17", "X:0010-00324301", "Recibo de Venta", 0, 37000000),
    ("2026-09-21", "A:0013-00034152", "Factura de Ventas", 124622206, 0),
]
OPENING = 0
CLOSING = -267838617
STMT_TOL = 100  # $1,00 para facturas (difs menores 0,01 / 0,33 / 0,86)


def days(d1, d2):
    a = date.fromisoformat(d1)
    b = date.fromisoformat(d2)
    return abs((a - b).days)


def money(cents):
    s = f"{abs(cents) // 100:,}".replace(",", ".")
    return f"{'-' if cents < 0 else ''}${s},{abs(cents) % 100:02d}"


def load_system():
    src = (ROOT / 'reporte_analisis_proveedores.html').read_text(encoding='utf-8')
    payload = json.loads(re.search(
        r'<script id="data" type="application/json">(.*?)</script>', src, re.S)[1])
    rows = [r for r in payload['rows']
            if r['provider'] == '986' and '2026-01-01' <= r['date'] <= '2026-10-01']
    return [r for r in rows if 'CONDISE' in r['reference'].upper()
            or 'GCONDIS' in r['reference'].upper()
            or r['id'] in ('19126', '17151')]


def main():
    sys_rows = load_system()
    pagos = sorted([r for r in sys_rows if r['payments'] > 0], key=lambda r: r['date'])
    cargos = sorted([r for r in sys_rows if r['charges'] > 0], key=lambda r: r['date'])
    assert len(pagos) == 5 and len(cargos) == 5, (len(pagos), len(cargos))

    # control del estado: apertura + debe - haber = cierre
    debe = sum(l[3] for l in STATEMENT)
    haber = sum(l[4] for l in STATEMENT)
    assert OPENING + debe - haber == CLOSING, (debe, haber)

    # pagos: match por importe con ventana +-45 dias; dos recibos juntos para 20286
    recs = [l for l in STATEMENT if l[4] > 0]
    fact = [l for l in STATEMENT if l[3] > 0]
    pay_match = {}
    used = set()
    for p in pagos:
        exact = [r for r in recs if r[1] not in used and abs(r[4] - p['payments']) <= 2
                 and days(r[0], p['date']) <= 45]
        if exact:
            r = exact[0]
            pay_match[p['id']] = (r, f"Importe exacto ({days(r[0], p['date'])} días)")
            used.add(r[1])
    # combinacion: 20286 = suma de dos recibos
    rest = [r for r in recs if r[1] not in used]
    p20286 = next(p for p in pagos if p['id'] == '20286')
    combo = abs(sum(r[4] for r in rest) - p20286['payments']) <= 2
    assert combo and len(rest) == 2
    pay_match['20286'] = ((rest[0][0], rest[0][1] + ' + ' + rest[1][1],
                           rest[0][2], 0, sum(r[4] for r in rest)),
                          f"Suma de 2 recibos ({days(rest[0][0], p20286['date'])} días)")
    used.update(r[1] for r in rest)
    assert len(pay_match) == 5 and len(used) == 6

    # facturas: match por importe (tol $1,00) con ventana +-30 dias
    fact_match = {}
    for c in cargos:
        ok = [l for l in fact if l[1] not in fact_match and l[1] not in used
              and abs(l[3] - c['charges']) <= STMT_TOL and days(l[0], c['date']) <= 30]
        assert ok, c['id']
        l = ok[0]
        diff = c['charges'] - l[3]
        note = "Importe exacto" if diff == 0 else f"Diferencia {money(diff)}"
        fact_match[l[1]] = (c, note)
        used.add(l[1])
    assert len(fact_match) == 5

    sys_pagos_total = sum(p['payments'] for p in pagos)
    sys_cargos_total = sum(c['charges'] for c in cargos)
    assert sys_pagos_total == haber  # los 5 pagos = Haber del estado
    faltantes = [l for l in fact if l[1] not in used]
    faltantes_total = sum(l[3] for l in faltantes)
    difs = sum(c['charges'] - l[3] for l, c in
               ((l, fact_match[l[1]][0]) for l in fact if l[1] in fact_match))
    # cierre: saldo sistema + faltantes - difs de importe = cierre del estado
    assert sys_cargos_total - sys_pagos_total + faltantes_total - difs == CLOSING

    print(json.dumps(dict(
        pagos_sistema=len(pagos), pagos_total=sys_pagos_total,
        recibos_estado=len(recs), recibos_total=haber,
        facturas_estado=len(fact), facturas_estado_total=debe,
        facturas_con_sistema=len(fact_match), facturas_sin_sistema=len(faltantes),
        faltantes_total=faltantes_total, difs_importe=difs,
        cierre_sistema=sys_cargos_total - sys_pagos_total,
        cierre_estado=CLOSING), ensure_ascii=True, indent=2))

    write_report(sys_rows, pagos, cargos, recs, fact, pay_match,
                 fact_match, faltantes, faltantes_total, debe, haber, difs)
    write_csv(pay_match, fact_match, recs, fact)


def write_report(sys_rows, pagos, cargos, recs, fact, pay_match,
                 fact_match, faltantes, faltantes_total, debe, haber, difs):
    h = html.escape
    by_id = {r['id']: r for r in sys_rows}
    pay_rows = "".join(
        '<tr>' + ''.join(f'<td>{h(str(x))}</td>' for x in (
            fmt_date(p['date']), p['id'], h(p['reference'][:48]), money(p['payments']),
            pay_match[p['id']][0][1], fmt_date(pay_match[p['id']][0][0]),
            money(pay_match[p['id']][0][4]), pay_match[p['id']][1])) + '</tr>'
        for p in pagos)
    fact_rows = "".join(
        '<tr>' + ''.join(f'<td>{h(str(x))}</td>' for x in (
            fmt_date(l[0]), l[1], money(l[3]),
            fact_match[l[1]][0]['id'], fact_match[l[1]][0]['date'],
            money(fact_match[l[1]][0]['charges']), fact_match[l[1]][1])) + '</tr>'
        for l in fact if l[1] in fact_match)
    falt_rows = "".join(
        '<tr>' + ''.join(f'<td>{h(str(x))}</td>' for x in (
            fmt_date(l[0]), l[1], money(l[3]),
            'Sin cargo identificado en el sistema')) + '</tr>'
        for l in faltantes)
    content = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CONDISEÑO — Estado del proveedor vs sistema</title>
<style>body{{font:15px/1.5 'Segoe UI',sans-serif;background:#f3f6f8;color:#263238;margin:0}}main{{max-width:1300px;margin:auto;padding:24px}}header,section{{background:white;padding:24px;border-radius:12px;margin-bottom:18px}}header{{background:#39265e;color:white}}h1,h2{{margin-top:0}}.wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:9px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}}th{{background:#72509a;color:white}}tr:nth-child(even){{background:#faf8fc}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:16px 0}}.card{{background:#eee8f5;border-radius:10px;padding:16px}}.card b{{font-size:19px}}.ok{{background:#e8f5e9;padding:14px}}.warn{{background:#fff5e5;padding:14px}}a{{color:#72509a}}@media(max-width:600px){{main{{padding:10px}}section,header{{padding:15px}}}}</style></head><body><main>
<header><h1>CONDISEÑO S.A.S. — Estado del proveedor vs sistema</h1><p>Cliente/Proveedor 16374 · Estado POLICOR 01/01/2026–30/09/2026 · Saldo inicial $0,00 · Cierre −$2.678.386,17 (a favor Condiseño).</p><p>Origen: imagen del estado (sin PDF en carpeta) · Sistema: movimientos POLICOR 986 con referencia Condiseño, 2026. Solo lectura.</p></header>
<section><h2>Resumen</h2><div class="cards">
<div class="card"><b>{money(haber)}</b><br>Pagos en el estado (6 recibos)</div>
<div class="card"><b>{money(haber)}</b><br>Pagos en sistema (5 egresos) — <b>100% identificados</b></div>
<div class="card"><b>{money(debe)}</b><br>Facturas en el estado (13)</div>
<div class="card"><b>{money(sum(l[3] for l in fact if l[1] in fact_match))}</b><br>Facturas con cargo en sistema (5)</div>
<div class="card"><b>{money(faltantes_total)}</b><br>Facturas sin cargo en sistema (8)</div>
</div>
<p class="ok"><b>Cierre de pagos:</b> los 5 pagos extra del mixto (17152, 19126, 20726, 19405, 20286) <b>coinciden al centavo</b> con los 6 recibos de este estado. Los "pagos extra" sin recibo de Avanzia son recibos de Condiseño.</p>
<p class="warn"><b>Pendiente:</b> 8 facturas por {money(faltantes_total)} no tienen cargo en el sistema; diferencia total de importes en facturas vinculadas {money(difs)} (≤$0,86 c/u). Saldo sistema (−$9.323.469,71) + faltantes − difs = cierre estado (−$2.678.386,17).</p></section>
<section><h2>Pagos: sistema vs recibos del estado</h2><div class="wrap"><table id="pag"><thead><tr><th>Fecha pago</th><th>ID</th><th>Referencia</th><th>Importe</th><th>Recibo</th><th>Fecha recibo</th><th>Importe recibo</th><th>Resultado</th></tr></thead><tbody>{pay_rows}</tbody></table></div></section>
<section><h2>Facturas del estado con cargo en sistema</h2><div class="wrap"><table id="fac"><thead><tr><th>Vto</th><th>Número</th><th>Importe estado</th><th>ID sistema</th><th>Fecha sistema</th><th>Importe sistema</th><th>Resultado</th></tr></thead><tbody>{fact_rows}</tbody></table></div></section>
<section><h2>Facturas sin cargo en sistema (8)</h2><div class="wrap"><table id="fal"><thead><tr><th>Vto</th><th>Número</th><th>Importe</th><th>Estado</th></tr></thead><tbody>{falt_rows}</tbody></table></div></section>
<section><h2>Enlaces</h2><a href="reporte_pagos_extra_policor.html">Pagos extra (resolución)</a> · <a href="reporte_pagos_vs_facturas_policor.html">Pagos vs facturas</a> · <a href="reporte_conciliacion_policor_pdf.html">Conciliación Avanzia</a> · <a href="conciliacion_condiseno.csv">CSV</a> · <a href="index.html">Inicio</a></section>
</main></body></html>'''
    (ROOT / 'reporte_conciliacion_condiseno.html').write_text(content, encoding='utf-8')
    print('HTML ok')


def write_csv(pay_match, fact_match, recs, fact):
    with (ROOT / 'conciliacion_condiseno.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Tipo', 'Vto estado', 'Comprobante estado', 'Importe estado',
                    'ID sistema', 'Fecha sistema', 'Importe sistema', 'Resultado'])
        for pid, (r, note) in sorted(pay_match.items()):
            w.writerow(['Pago', r[0], r[1], money(r[4]), pid, '', '', note])
        for pid, (c, note) in sorted(fact_match.items(), key=lambda x: x[1][0]['date']):
            w.writerow(['Factura', '', pid, '', c['id'], c['date'],
                        money(c['charges']), note])
        for l in fact:
            if l[1] not in fact_match:
                w.writerow(['Factura', fmt_date(l[0]), l[1], money(l[3]), '', '', '',
                            'Sin cargo identificado en el sistema'])
    print('CSV ok')


if __name__ == '__main__':
    main()
