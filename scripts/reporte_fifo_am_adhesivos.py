#!/usr/bin/env python3
"""FIFO AM ADHESIVOS. --live actualiza la fuente exclusivamente en lectura."""
import argparse
import csv
import html
import json
import re
from datetime import date
from pathlib import Path
from reporte_fifo_por_empresa import fifo, money, dmy

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'am_adhesivos_flows.json'
# Transcripción del estado adjunto, emitido 06/10/2026 para AVANZIA S.A.S.
# Fecha, tipo, número, centavos, saldo acumulado del documento.
STATEMENT = [
    ('2025-01-14', 'Factura', 'A-0004-00007563', 80295600, 80295600),
    ('2025-01-22', 'Recibo', '00003769', 80295600, 0),
    ('2025-04-10', 'Factura', 'A-0004-00007732', 119436075, 119436075),
    ('2025-04-28', 'Factura', 'A-0004-00007765', 23887215, 143323290),
    ('2025-04-30', 'Recibo', '00003882', 143323290, 0),
    ('2025-07-14', 'Factura', 'A-0004-00007904', 51183000, 51183000),
    ('2025-10-16', 'Factura', 'A-0004-00008086', 55539000, 106722000),
    ('2025-11-06', 'Recibo', '00004079', 106720000, 2000),
    ('2025-11-25', 'Factura', 'A-0004-00008154', 105451500, 105453500),
    ('2025-12-23', 'Recibo', '00004119', 105451500, 2000),
    ('2026-02-03', 'Factura', 'A-0004-00008265', 120516000, 120518000),
    ('2026-03-06', 'Recibo', '00004213', 120516000, 2000),
    ('2026-05-08', 'Factura', 'A-0004-00008438', 107073928, 107075928),
    ('2026-05-29', 'Factura', 'A-0004-00008466', 107073750, 214149678),
    ('2026-06-15', 'Recibo', '00004305', 214147678, 2000),
    ('2026-07-14', 'Factura', 'A-0004-00008541', 160985055, 160987055),
    ('2026-07-31', 'Factura', 'A-0004-00008574', 162587700, 323574755),
    ('2026-08-11', 'Recibo', '00004332', 323572755, 2000),
    ('2026-09-03', 'Factura', 'A-0004-00008625', 168054480, 168056480),
    ('2026-09-03', 'Factura', 'A-0004-00008627', 32942400, 200998880),
]


def load_source(live=False):
    if live:
        from reporte_analisis_proveedores import fetch_data
        data = fetch_data()
        data['rows'] = [r for r in data['rows'] if r['provider'] in ('698', '393')
                        and '2025-01-01' <= r['date'] <= '2026-10-06']
        SOURCE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return json.loads(SOURCE.read_text(encoding='utf-8'))


def build(data):
    balance = 0
    invoices, payments = [], []
    for fecha, tipo, num, amount, expected in STATEMENT:
        balance += amount if tipo == 'Factura' else -amount
        assert balance == expected, num
        row = dict(fecha=fecha, tipo=tipo, num=num, importe=amount, idsys='', local=None)
        (invoices if tipo == 'Factura' else payments).append(row)
    assert sum(f['importe'] for f in invoices) == 1295025703
    assert sum(p['importe'] for p in payments) == 1094026823
    assert balance == 200998880
    charges = [r for r in data['rows'] if r['charges'] > 0]
    groups = {}
    for f in invoices:
        suffix = int(f['num'].split('-')[-1])
        candidates = [r for r in charges if suffix in
                      {int(n) for n in re.findall(r'\d+', r['reference'])}]
        if len(candidates) == 1:
            f['local'] = candidates[0]
            f['idsys'] = candidates[0]['id']
            groups.setdefault(f['idsys'], []).append(f)
        elif candidates:
            raise ValueError('Factura ambigua: ' + f['num'])
    # Control de cargos agrupados: comparar contra la suma, nunca duplicarlos.
    for group in groups.values():
        delta = group[0]['local']['charges'] - sum(f['importe'] for f in group)
        for f in group:
            f['group'] = len(group)
            f['delta'] = delta
    used = set()
    for p in payments:
        candidates = [r for r in data['rows'] if r['payments'] > 0 and r['id'] not in used
                      and abs(r['payments'] - p['importe']) <= 200
                      and abs((date.fromisoformat(r['date']) - date.fromisoformat(p['fecha'])).days) <= 30]
        if len(candidates) == 1:
            p['local'] = candidates[0]
            p['idsys'] = candidates[0]['id']
            used.add(p['idsys'])
        elif candidates:
            raise ValueError('Recibo ambiguo: ' + p['num'])
    fifo(payments, invoices)
    assert sum(f['importe'] - f['cubierto'] for f in invoices) == balance
    assert sum(p['remanente'] for p in payments) == 0
    return payments, invoices


def situation(row):
    r = row['local']
    if not r:
        return 'Sin registro identificado en flows'
    text = f"ID {r['id']} · perfil {r['provider']} · {r['name']} · {dmy(r['date'])}"
    if row['tipo'] == 'Factura':
        if row.get('group', 1) > 1:
            text += f" · Cargo agrupado de {row['group']} facturas: {money(r['charges'])} (no sumar dos veces)"
        if row['delta']:
            text += f" · Diferencia flows − proveedor: {money(row['delta'])}"
    else:
        delta = r['payments'] - row['importe']
        text += ' · Pago flows ' + money(r['payments'])
        if delta:
            text += ' · Diferencia flows − proveedor: ' + money(delta)
    if row['fecha'] != r['date']:
        text += ' · Fecha distinta del estado'
    return text


def render(data, payments, invoices):
    h = html.escape
    missing = [f for f in invoices if not f['idsys']]
    payment_rows = []
    for p in payments:
        allocation = '; '.join(f"{f['num']}: {money(sum(t for pp, t in f['por'] if pp is p))}"
                               for f in p['cubiertas'])
        payment_rows.append([dmy(p['fecha']), p['num'], money(p['importe']),
                             allocation, money(p['remanente']), situation(p)])
    invoice_rows = [[dmy(f['fecha']), f['num'], money(f['importe']),
                     '; '.join(p['num'] + ': ' + money(t) for p, t in f['por']),
                     money(f['importe'] - f['cubierto']), situation(f)] for f in invoices]
    missing_rows = [[dmy(f['fecha']), f['num'], money(f['importe'])] for f in missing]
    def table(name, headers, rows):
        return f'<div class="wrap"><table id="{name}"><thead><tr>' + ''.join(
            '<th>' + h(x) + '</th>' for x in headers) + '</tr></thead><tbody>' + ''.join(
            '<tr>' + ''.join('<td>' + h(str(x)) + '</td>' for x in row) + '</tr>'
            for row in rows) + '</tbody></table></div>'
    matched_ids = {x['idsys'] for x in payments + invoices if x['idsys']}
    extras = [r for r in data['rows'] if r['id'] not in matched_ids]
    extra_section = ''
    if extras:
        extra_section = '<section><h2>Movimientos de flows sin vinculación en el estado</h2>' + table(
            'extras', ['Fecha', 'ID', 'Perfil', 'Referencia', 'Cargo', 'Pago'],
            [[r['date'], r['id'], r['provider'], r['reference'], money(r['charges']), money(r['payments'])]
             for r in extras]) + '</section>'
    content = f'''<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AM ADHESIVOS — FIFO Avanzia</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#f3f6f8;color:#263238;font:15px/1.5 'Segoe UI',sans-serif}}main{{max-width:1500px;margin:auto;padding:24px}}header,section{{padding:24px;background:white;border-radius:12px;margin-bottom:20px}}header{{border-top:6px solid #61418a}}a{{color:#61418a}}.wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}}th{{background:#61418a;color:white}}.note{{background:#fff5e5;padding:14px}}.cards{{display:flex;flex-wrap:wrap;gap:16px}}.cards p{{background:#eee8f5;padding:16px;border-radius:8px}}@media(max-width:600px){{main{{padding:10px}}section,header{{padding:14px}}}}@media print{{a{{color:inherit}}.wrap{{overflow:visible}}main{{padding:0}}}}</style></head><body><main>
<header><h1>AM ADHESIVOS — FIFO Avanzia</h1><a href="conciliacion_proveedores.html">← Volver a proveedores</a> · <a href="fifo_am_adhesivos.csv">Descargar CSV</a>
<p>Estado de cuenta emitido el 06/10/2026 para AVANZIA S.A.S. Período indicado: 01/01/2025–31/10/2026; último movimiento: 03/09/2026. Saldo inicial: $0,00. Fuente: transcripción del PDF adjunto.</p>
<p>Flows consultado: {h(data['generated'])}. Perfiles 698 — AM ADHESIVOS MONTERO y 393 — HORACIO MONTERO. Facturas: 10303/1368; pagos: 10150 CAJA: Egresos.</p>
<div class="cards"><p>13 facturas<br><b>$12.950.257,03</b></p><p>7 recibos del proveedor<br><b>$10.940.268,23</b></p><p>Saldo a pagar a AM ADHESIVOS<br><b>$2.009.988,80</b></p><p>{len(missing)} facturas sin carga identificada<br><b>{money(sum(f['importe'] for f in missing))}</b></p></div>
<p>FIFO teórico por fecha del estado: cada recibo cubre las facturas más antiguas. Se usan los importes del proveedor; los registros de flows y sus diferencias se muestran por separado. Una factura cubierta puede seguir faltando en flows.</p></header>
<section><h2>Recibos → facturas (FIFO)</h2>{table('pagos', ['Fecha estado', 'Recibo', 'Importe proveedor', 'Facturas / importe aplicado', 'Remanente', 'Verificación en flows'], payment_rows)}</section>
<section><h2>Facturas → cobertura y carga en flows</h2>{table('facturas', ['Fecha estado', 'Factura', 'Importe proveedor', 'Recibos / importe aplicado', 'Pendiente FIFO', 'Verificación en flows'], invoice_rows)}
<p class="note">El proveedor conserva $20,00 pendientes en la factura 8086. El FIFO estricto aplica los recibos siguientes a esa deuda y traslada los $20,00 hasta la factura 8574. El cierre es idéntico: $20,00 + $1.680.544,80 (8625) + $329.424,00 (8627) = $2.009.988,80.</p></section>
<section><h2>Facturas a cargar en flows ({len(missing)})</h2><p>Sin registro identificado en los dos perfiles y flujos consultados.</p>{table('faltantes', ['Fecha', 'Factura', 'Importe'], missing_rows)}</section>
<section><h2>Diferencias a revisar</h2><ul><li>FA 8438: proveedor $1.070.739,28; flows $1.070.737,50. Diferencia: $1,78.</li><li>Recibo 4305: proveedor $2.141.476,78; pago flows $2.141.475,00. Diferencia: $1,78. No se consideran diferencias toleradas de $0,02.</li><li>FA 8265: fecha del estado 03/02/2026; fecha en flows 06/03/2026 (31 días). Vinculada por número e importe.</li><li>FA 8541 y 8574: cargo agrupado ID 18772 y pago ID 18773 en el perfil HORACIO MONTERO. El cargo se cuenta una sola vez.</li></ul><p>Recibos sin pago identificado en flows: {h(', '.join(p['num'] for p in payments if not p['idsys']) or 'Ninguno')}.</p></section>{extra_section}
</main></body></html>'''
    (ROOT / 'reporte_fifo_am_adhesivos.html').write_text(content, encoding='utf-8')
    with (ROOT / 'fifo_am_adhesivos.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(['Tabla', 'Fecha estado', 'Comprobante', 'Importe proveedor', 'Aplicaciones FIFO', 'Pendiente o remanente', 'Verificación flows'])
        for label, rows in [('Recibo FIFO', payment_rows), ('Factura FIFO', invoice_rows)]:
            for row in rows:
                writer.writerow([label] + row)
        for row in missing_rows:
            writer.writerow(['A cargar en flows'] + row + ['', '', 'Sin registro identificado'])
    print(json.dumps(dict(facturas=len(invoices), recibos=len(payments), faltantes=len(missing),
                          importe_faltante=sum(f['importe'] for f in missing),
                          recibos_sin_flows=[p['num'] for p in payments if not p['idsys']],
                          extras=[r['id'] for r in extras], saldo=200998880)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    source = load_source(args.live)
    render(source, *build(source))
