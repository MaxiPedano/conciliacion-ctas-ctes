#!/usr/bin/env python3
"""Vista POLICOR mixta: pagos realizados en flows vs facturas del proveedor.

Solo lectura. Reutiliza el match del conciliador mixto (tolerancia $0,02,
ventana Vto +-30 días, desempate determinístico). Sin separar por empresa.
Excluye notas de crédito de esta vista (solo pagos vs facturas).
"""
import csv
import html
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conciliar_policor_pdf import parse_pdf, reconcile, money, fmt_date

ROOT = Path(__file__).resolve().parents[1]


def main():
    external, opening, closing = parse_pdf()
    source = (ROOT / 'reporte_analisis_proveedores.html').read_text(encoding='utf-8')
    payload = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', source, re.S)[1])
    generated = payload['generated']
    all_local = [v for v in payload['rows'] if v['provider'] == '986' and v['date'] <= '2026-10-01']
    internal = [v for v in all_local if v['date'] >= '2026-01-01']
    extras = reconcile(external, internal)

    receipts = [r for r in external if r['kind'] == 'Recibo de Venta']
    invoices_pdf = [r for r in external if r['kind'] == 'Factura de Ventas']
    pay_sys = sorted([v for v in internal if v['flowid'] == 10150], key=lambda v: (v['date'], int(v['id'])))
    inv_sys = sorted([v for v in internal if v['flowid'] == 10303 and v['charges'] >= 0],
                     key=lambda v: (v['date'], int(v['id'])))

    used_pay = {r['local']['id'] for r in receipts if r['local']}
    used_inv = {r['local']['id'] for r in invoices_pdf if r['local']}
    assert used_pay.isdisjoint(used_inv)
    assert len(used_pay | used_inv) == sum(1 for r in external if r['local'] and r['kind'] != 'Nota de Crédito de Venta')

    pay_total = sum(v['payments'] for v in pay_sys)
    rec_total = sum(r['credit'] for r in receipts)
    rec_matched = sum(r['credit'] for r in receipts if r['local'])
    inv_sys_total = sum(v['charges'] for v in inv_sys)
    inv_pdf_total = sum(r['debit'] for r in invoices_pdf)
    inv_pdf_matched = sum(r['debit'] for r in invoices_pdf if r['local'] and abs((r['local']['charges'] - r['local']['payments']) - (r['debit'] - r['credit'])) <= 2)

    print(json.dumps(dict(
        pagos_sistema=len(pay_sys), pagos_total=pay_total,
        recibos_pdf=len(receipts), recibos_total=rec_total, recibos_vinculados=rec_matched,
        facturas_sistema=len(inv_sys), facturas_sistema_total=inv_sys_total,
        facturas_pdf=len(invoices_pdf), facturas_pdf_total=inv_pdf_total,
        facturas_pdf_vinculadas=inv_pdf_matched), ensure_ascii=True, indent=2))
    write_report(generated, receipts, invoices_pdf, pay_sys, inv_sys,
                 pay_total, rec_total, rec_matched, inv_sys_total, inv_pdf_total)


def write_report(generated, receipts, invoices_pdf, pay_sys, inv_sys,
                 pay_total, rec_total, rec_matched, inv_sys_total, inv_pdf_total):
    h = html.escape
    by_id = {}
    for r in receipts + invoices_pdf:
        if r['local']:
            by_id[r['local']['id']] = r
    pay_rows = []
    for v in pay_sys:
        r = by_id.get(v['id'])
        pay_rows.append('<tr>' + ''.join(f'<td>{h(str(x))}</td>' for x in (
            fmt_date(v['date']), v['id'], v['reference'], v['status'],
            money(v['payments']),
            (r['number'] + ' · ' + fmt_date(r['date'])) if r else '—',
            (r['match'] if r else 'Pago sin recibo identificado en el PDF'))) + '</tr>')
    for r in receipts:
        if not r['local']:
            pay_rows.append('<tr>' + ''.join(f'<td>{h(str(x))}</td>' for x in (
                '—', '—', 'Recibo del PDF sin pago identificado en flows',
                r['number'] + ' · ' + r['kind'], money(0),
                r['number'] + ' · ' + fmt_date(r['date']),
                'Recibo sin pago identificado en flows')) + '</tr>')
    inv_rows = []
    for r in invoices_pdf:
        v = r['local']
        inv_rows.append('<tr>' + ''.join(f'<td>{h(str(x))}</td>' for x in (
            fmt_date(r['date']), r['number'], money(r['debit']),
            (v['id'] + ' · ' + fmt_date(v['date'])) if v else '—',
            (h(v['reference']) if v else '—'),
            (r['match'] if v else 'Factura sin carga identificada en el sistema'))) + '</tr>')
    linked_inv_ids = {r['local']['id'] for r in invoices_pdf if r['local']}
    for v in inv_sys:
        if v['id'] not in linked_inv_ids:
            inv_rows.append('<tr>' + ''.join(f'<td>{h(str(x))}</td>' for x in (
                '—', '—', money(0), v['id'] + ' · ' + fmt_date(v['date']),
                h(v['reference']), 'Factura del sistema sin factura identificada en el PDF')) + '</tr>')
    content = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>POLICOR — Pagos en flows vs Facturas del proveedor</title>
<style>body{{font:15px/1.5 'Segoe UI',sans-serif;background:#f3f6f8;color:#263238;margin:0}}main{{max-width:1600px;margin:auto;padding:24px}}header,section{{background:white;padding:24px;border-radius:12px;margin-bottom:22px}}header{{background:#39265e;color:white}}h1,h2{{margin-top:0}}.wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:10px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}}th{{background:#72509a;color:white}}tr:nth-child(even){{background:#faf8fc}}.num{{text-align:right;white-space:nowrap}}a{{color:#72509a}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:16px 0}}.card{{background:#eee8f5;border-radius:10px;padding:16px}}.card b{{font-size:20px}}.note{{background:#fff5e5;padding:16px}}@media(max-width:600px){{main{{padding:10px}}section,header{{padding:15px}}}}</style></head><body><main>
<header><h1>POLICOR — Pagos en flows vs Facturas del proveedor</h1><p>Mixto, sin separar por empresa · Período 01/01/2026–01/10/2026 · Solo pagos (10150 CAJA Egresos) y facturas (PDF + 10303/1368).</p><p>Fuente sistema consultada {h(generated)} · PDF vtacpaestadosaldo.pdf del 01/10/2026. Match con tolerancia $0,02 y ventana Vto ±30 días.</p></header>
<section><h2>Resumen</h2><div class="cards">
<div class="card"><b>{money(pay_total)}</b><br>Pagos en flows ({len(pay_sys)})</div>
<div class="card"><b>{money(rec_total)}</b><br>Recibos del proveedor ({len(receipts)})</div>
<div class="card"><b>{money(rec_matched)}</b><br>Recibos vinculados a pagos</div>
<div class="card"><b>{money(inv_sys_total)}</b><br>Facturas en sistema ({len(inv_sys)})</div>
<div class="card"><b>{money(inv_pdf_total)}</b><br>Facturas del proveedor ({len(invoices_pdf)})</div>
</div>
<p class="note">Vista mixta: incluye todo POLICOR sin separar empresa; el PDF es solo Avanzia. “Sin identificado” = sin contraparte por número/importe/fecha-ventana en esta fuente.</p>
<a href="vtacpaestadosaldo.pdf">Ver PDF original</a> · <a href="reporte_conciliacion_policor_pdf.html">Ver conciliación mixta completa</a> · <a href="pagos_vs_facturas_policor.csv">Descargar CSV</a></section>
<section><h2>Pagos en flows comparados con recibos del proveedor</h2><div class="wrap"><table id="payments"><thead><tr><th>Fecha pago</th><th>ID pago</th><th>Referencia pago</th><th>Estado</th><th>Pago</th><th>Recibo proveedor</th><th>Resultado</th></tr></thead><tbody>{''.join(pay_rows)}</tbody></table></div></section>
<section><h2>Facturas del proveedor comparadas con facturas en sistema</h2><div class="wrap"><table id="invoices"><thead><tr><th>Vto PDF</th><th>Número PDF</th><th>Importe PDF</th><th>ID sistema</th><th>Referencia sistema</th><th>Resultado</th></tr></thead><tbody>{''.join(inv_rows)}</tbody></table></div></section>
<footer>Solo lectura; no se modificaron datos del sistema.</footer>
<script>for(const id of ['payments','invoices']){{const t=document.getElementById(id);const label=document.createElement('label');label.innerHTML='Buscar <input type="search" placeholder="Número, fecha, importe...">';t.before(label);const inp=label.querySelector('input');inp.addEventListener('input',()=>{{const q=inp.value.toLocaleLowerCase('es');for(const r of t.querySelectorAll('tbody tr'))r.hidden=!r.textContent.toLocaleLowerCase('es').includes(q);}});}}</script></main></body></html>'''
    (ROOT / 'reporte_pagos_vs_facturas_policor.html').write_text(content, encoding='utf-8')
    with (ROOT / 'pagos_vs_facturas_policor.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Vista', 'Fecha', 'ID/Número', 'Referencia', 'Estado/Tipo', 'Importe sistema', 'Comprobante proveedor', 'Resultado'])
        for v in pay_sys:
            r = by_id.get(v['id'])
            w.writerow(['Pago', fmt_date(v['date']), v['id'], v['reference'], v['status'],
                        money(v['payments']), (r['number'] if r else ''), (r['match'] if r else 'Pago sin recibo identificado en el PDF')])
        for r in receipts:
            if not r['local']:
                w.writerow(['Pago', '', '', 'Recibo del PDF sin pago en flows', r['number'] + ' ' + r['kind'],
                            money(0), r['number'], 'Recibo sin pago identificado en flows'])
        for r in invoices_pdf:
            v = r['local']
            w.writerow(['Factura', fmt_date(r['date']), r['number'], '', r['kind'],
                        (money(v['charges']) if v else money(0)), (v['id'] if v else ''), (r['match'] if v else 'Factura sin carga identificada en el sistema')])


if __name__ == '__main__':
    main()
