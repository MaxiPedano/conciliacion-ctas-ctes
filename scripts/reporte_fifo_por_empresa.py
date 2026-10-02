#!/usr/bin/env python3
"""FIFO por empresa: pagos vs facturas del proveedor + facturas a cargar en flows.

Avanzia: conciliacion_policor_pdf.csv. Condiseño: conciliacion_condiseno.csv.
Solo lectura; incluye apertura y créditos del estado, sin cruces entre empresas.
"""
import csv
import html
from decimal import Decimal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conciliar_condiseno_pdf import STATEMENT  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def parse_money(value):
    s = str(value).strip().replace('$', '').replace(' ', '')
    if not s:
        return 0
    neg = s.startswith('-') or s.startswith('\u2212')
    s = s.lstrip('-\u2212')
    s = s.replace('.', '').replace(',', '.')
    return (-1 if neg else 1) * int(Decimal(s) * 100)


def money(cents):
    s = f"{abs(cents) // 100:,}".replace(",", ".")
    return f"{'-' if cents < 0 else ''}${s},{abs(cents) % 100:02d}"


def dmy(iso):
    y, m, d = str(iso)[:10].split('-')
    return f"{d}/{m}/{y}"


def to_iso_dmy(value):
    return f"{value[6:10]}-{value[3:5]}-{value[0:2]}"


def load_avanzia():
    with (ROOT / 'conciliacion_policor_pdf.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f, delimiter=';'))
    facturas = [dict(fecha=to_iso_dmy(r['Vto PDF']), num=r['Comprobante PDF'],
                     importe=parse_money(r['Debe PDF']), idsys=r['ID sistema'],
                     dif=parse_money(r['Cargo sistema']) - parse_money(r['Debe PDF'])
                     if r['ID sistema'] else 0)
                for r in rows if r['Tipo PDF'] == 'Factura de Ventas']
    pagos = [dict(fecha=to_iso_dmy(r['Vto PDF']), num=r['Comprobante PDF'],
                  importe=parse_money(r['Haber PDF']), idsys=r['ID sistema'],
                  tipo=r['Tipo PDF'])
             for r in rows if parse_money(r['Haber PDF']) > 0]
    # Apertura del estado POLICOR: crédito de Avanzia al 01/01/2026.
    pagos.insert(0, dict(fecha='2026-01-01', num='Saldo inicial a favor de Avanzia',
                         importe=403625132, idsys='', tipo='Saldo inicial'))
    return pagos, facturas


def load_condiseno():
    with (ROOT / 'conciliacion_condiseno.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f, delimiter=';'))
    fact_sys = {r['Comprobante estado']: r for r in rows if r['Tipo'] == 'Factura' and r['ID sistema']}
    facturas = [dict(fecha=l[0], num=l[1], importe=l[3],
                     idsys=(fact_sys[l[1]]['ID sistema'] if l[1] in fact_sys else ''),
                     dif=(parse_money(fact_sys[l[1]]['Importe sistema']) - l[3]
                          if l[1] in fact_sys else 0))
                for l in STATEMENT if l[3] > 0]
    pagos = [dict(fecha=r['Vto estado'], num=r['Comprobante estado'],
                  importe=parse_money(r['Importe estado']), idsys=r['ID sistema'],
                  tipo='Recibo de Venta')
             for r in rows if r['Tipo'] == 'Pago']
    return pagos, facturas


def fifo(pagos, facturas):
    """Cada pago cubre facturas mas viejas pendientes. Devuelve estado por factura
    y detalle por pago (facturas cubiertas + remanente)."""
    eventos = ([('p', p['fecha'], p) for p in pagos] +
               [('f', f['fecha'], f) for f in facturas])
    eventos.sort(key=lambda e: (e[1], 0 if e[0] == 'p' else 1))
    cola = []           # créditos disponibles, en orden de fecha
    pendientes = []     # facturas pendientes, en orden de Vto
    usados = {id(p): 0 for p in pagos}
    for f in facturas:
        f['cubierto'] = 0
        f['por'] = []
    for tipo, _, obj in eventos:
        if tipo == 'p':
            cola.append(obj)
        else:
            pendientes.append(obj)
        # Conciliar al ingresar tanto un crédito como una factura:
        # un pago posterior también cancela deuda ya vencida.
        while cola and pendientes:
            p, factura = cola[0], pendientes[0]
            take = min(p['importe'] - usados[id(p)],
                       factura['importe'] - factura['cubierto'])
            usados[id(p)] += take
            factura['cubierto'] += take
            factura['por'].append((p, take))
            if usados[id(p)] == p['importe']:
                cola.pop(0)
            if factura['cubierto'] == factura['importe']:
                pendientes.pop(0)
    for f in facturas:
        if f['cubierto'] >= f['importe']:
            f['estado'] = 'Cubierta'
        elif f['cubierto'] > 0:
            f['estado'] = 'Parcial'
        else:
            f['estado'] = 'Sin cubrir'
    for p in pagos:
        p['usado'] = usados[id(p)]
        p['remanente'] = p['importe'] - p['usado']
        p['cubiertas'] = [f for f in facturas if any(pp is p for pp, _ in f['por'])]
    aplicado = sum(f['cubierto'] for f in facturas)
    assert aplicado == sum(p['usado'] for p in pagos)
    assert aplicado == min(sum(p['importe'] for p in pagos), sum(f['importe'] for f in facturas))
    return pagos, facturas


def main():
    av_pagos, av_facturas = load_avanzia()
    co_pagos, co_facturas = load_condiseno()
    fifo(av_pagos, av_facturas)
    fifo(co_pagos, co_facturas)

    # controles
    assert len(av_pagos) == 11 and len(av_facturas) == 38
    assert len(co_pagos) == 5 and len(co_facturas) == 13
    assert sum(p['importe'] for p in av_pagos if p['idsys']) == 3265220575
    assert sum(p['importe'] for p in av_pagos if p['tipo'] == 'Nota de Crédito de Venta') == 177680500
    assert sum(p['importe'] for p in co_pagos) == 1194880457
    av_falt = [f for f in av_facturas if not f['idsys']]
    co_falt = [f for f in co_facturas if not f['idsys']]
    assert len(av_falt) == 32 and sum(f['importe'] for f in av_falt) == 2391918352
    assert len(co_falt) == 8 and sum(f['importe'] for f in co_falt) == 664508302
    # Condiseño: pagos > facturas; sobrante = saldo a favor del estado
    co_sobra = sum(p['importe'] for p in co_pagos) - sum(f['importe'] for f in co_facturas)
    assert co_sobra == 267838617, co_sobra
    # Avanzia: facturas > pagos; descubierto
    av_desc = sum(f['importe'] for f in av_facturas) - sum(p['importe'] for p in av_pagos)
    assert av_desc == 84624077, av_desc
    assert sum(f['importe'] - f['cubierto'] for f in av_facturas) == 84624077
    assert sum(p['remanente'] for p in av_pagos) == 0
    assert all(f['cubierto'] == f['importe'] for f in co_facturas)
    assert sum(p['remanente'] for p in co_pagos) == 267838617

    write_html(av_pagos, av_facturas, co_pagos, co_facturas, av_falt, co_falt)
    write_csv(av_pagos, av_facturas, co_pagos, co_facturas, av_falt, co_falt)
    print(dict(
        av_pagos=len(av_pagos), av_fact=len(av_facturas), av_falt=len(av_falt),
        av_descubierto=av_desc, co_pagos=len(co_pagos), co_fact=len(co_facturas),
        co_falt=len(co_falt), co_sobra=co_sobra))


def factura_rows(facturas, faltantes):
    h = html.escape
    falt_ids = {f['num'] for f in faltantes}
    out = []
    for f in facturas:
        en_flows = 'No — falta cargar' if f['num'] in falt_ids else (
            f"Sí (ID {f['idsys']})" + (f" · dif {money(f['dif'])}" if f['dif'] else ''))
        cobro = f"{money(f['cubierto'])}"
        if f['por']:
            cobro += ' · ' + ', '.join(f"{p['num']} ({money(t)})" for p, t in f['por'])
        out.append('<tr>' + ''.join(f'<td>{h(str(x))}</td>' for x in (
            dmy(f['fecha']), f['num'], money(f['importe']), cobro,
            f['estado'], en_flows)) + '</tr>')
    return ''.join(out)


def pago_rows(pagos):
    h = html.escape
    out = []
    for p in pagos:
        cub = ', '.join(f"{f['num']} ({money(sum(t for pp, t in f['por'] if pp is p))})"
                        for f in p['cubiertas']) or '—'
        out.append('<tr>' + ''.join(f'<td>{h(str(x))}</td>' for x in (
            dmy(p['fecha']), p['tipo'] + ' · ' + p['num'],
            p['idsys'] or ('Saldo de apertura' if p['tipo'] == 'Saldo inicial' else 'Sin registro identificado en flows'), money(p['importe']), cub,
            money(p['remanente']))) + '</tr>')
    return ''.join(out)


def faltante_rows(faltantes):
    return ''.join(
        '<tr>' + ''.join(f'<td>{html.escape(str(x))}</td>' for x in (
            dmy(f['fecha']), f['num'], money(f['importe']))) + '</tr>'
        for f in faltantes)


def write_html(av_pagos, av_facturas, co_pagos, co_facturas, av_falt, co_falt):
    h = html.escape

    def bloque(nombre, periodo, pagos, facturas, faltantes, notas):
        pagos_t = money(sum(p['importe'] for p in pagos))
        facts_t = money(sum(f['importe'] for f in facturas))
        falt_t = money(sum(f['importe'] for f in faltantes))
        sobra = sum(p['importe'] for p in pagos) - sum(f['importe'] for f in facturas)
        saldo = ('A favor de ' + nombre + ' ' + money(sobra) if sobra > 0
                 else 'A pagar a POLICOR ' + money(-sobra))
        return f'''<section><h2>{h(nombre)} — {h(periodo)}</h2>
<div class="cards"><div class="card"><b>{pagos_t}</b><br>Pagos y créditos ({len(pagos)} movimientos)</div>
<div class="card"><b>{facts_t}</b><br>Facturas y débitos ({len(facturas)})</div>
<div class="card"><b>{falt_t}</b><br>Facturas sin cargar ({len(faltantes)})</div>
<div class="card"><b>{saldo}</b><br>Cierre FIFO</div></div>
<p class="note">{notas}</p>
<h3>Pagos y créditos → facturas (FIFO)</h3><div class="wrap"><table id="pag-{h(nombre)}"><thead><tr>
<th>Fecha estado</th><th>Tipo / comprobante</th><th>ID / situación en flows</th><th>Importe</th><th>Cubre facturas / importe aplicado</th><th>Remanente</th>
</tr></thead><tbody>{pago_rows(pagos)}</tbody></table></div>
<h3>Facturas → estado FIFO</h3><div class="wrap"><table id="fac-{h(nombre)}"><thead><tr>
<th>Vto</th><th>Número</th><th>Importe</th><th>Cubierto por</th><th>Estado</th><th>En flows</th>
</tr></thead><tbody>{factura_rows(facturas, faltantes)}</tbody></table></div>
<h3>Facturas a cargar en flows ({len(faltantes)})</h3><div class="wrap"><table id="fal-{h(nombre)}"><thead><tr>
<th>Vto</th><th>Número</th><th>Importe</th></tr></thead><tbody>{faltante_rows(faltantes)}</tbody></table></div></section>'''

    content = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FIFO por empresa — pagos vs facturas</title>
<style>body{{font:15px/1.5 'Segoe UI',sans-serif;background:#f3f6f8;color:#263238;margin:0}}main{{max-width:1500px;margin:auto;padding:24px}}header,section{{background:white;padding:24px;border-radius:12px;margin-bottom:18px}}header{{background:#39265e;color:white}}h1,h2,h3{{margin-top:0}}.wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:8px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}}th{{background:#72509a;color:white}}tr:nth-child(even){{background:#faf8fc}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:14px 0}}.card{{background:#eee8f5;border-radius:10px;padding:14px}}.card b{{font-size:17px}}.note{{background:#fff5e5;padding:12px}}a{{color:#72509a}}@media(max-width:600px){{main{{padding:10px}}section,header{{padding:15px}}}}</style></head><body><main>
<header><h1>POLICOR — FIFO por empresa</h1>
<p>Imputación FIFO teórica: cada pago o crédito cubre las facturas más viejas pendientes de su empresa; los anticipos se aplican a las siguientes. Incluye el saldo inicial y las notas de crédito del estado, sin cruces entre empresas. Fechas según Vto del proveedor. No representa una imputación confirmada por POLICOR. Solo lectura.</p>
<p><a href="fifo_por_empresa.csv">Descargar CSV</a> · <a href="conciliacion_proveedores.html">Volver a proveedores</a> · <a href="index.html">Inicio</a></p></header>
{bloque('Avanzia', '01/01/2026–01/10/2026', av_pagos, av_facturas, av_falt,
        'Apertura a favor: $4.036.251,32 + recibos: $32.652.206,75 + 2 NC: $1.776.805,00. Contra facturas por $39.311.503,84, queda $846.240,77 a pagar a POLICOR. El recibo X:0010-00320875 de $1,00 y las dos NC no tienen registro identificado en flows. La cobertura FIFO y la carga en flows son controles distintos.')}
{bloque('Condiseño', '01/01/2026–30/09/2026', co_pagos, co_facturas, co_falt,
        'Apertura $0,00. Los 5 pagos ($11.948.804,57) cubren 12 facturas y 1 nota de débito por $9.270.418,40; quedan $2.678.386,17 a favor de Condiseño. 3 facturas vinculadas con diferencia de importe ≤$0,86.')}
</main></body></html>'''
    (ROOT / 'reporte_fifo_por_empresa.html').write_text(content, encoding='utf-8')
    print('HTML ok')


def write_csv(av_pagos, av_facturas, co_pagos, co_facturas, av_falt, co_falt):
    with (ROOT / 'fifo_por_empresa.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Empresa', 'Tabla', 'Fecha', 'Número', 'Importe',
                    'Detalle', 'Estado', 'En flows'])
        for emp, pagos, facturas, faltantes in (
                ('Avanzia', av_pagos, av_facturas, av_falt),
                ('Condiseño', co_pagos, co_facturas, co_falt)):
            falt_ids = {x['num'] for x in faltantes}
            for p in pagos:
                w.writerow([emp, p['tipo'] + ' FIFO', dmy(p['fecha']), p['num'],
                            money(p['importe']),
                            ', '.join(x['num'] + ' (' + money(sum(t for pp, t in x['por'] if pp is p)) + ')' for x in p['cubiertas']) or '—',
                            f"Remanente {money(p['remanente'])}", p['idsys'] or ('Saldo de apertura' if p['tipo'] == 'Saldo inicial' else 'Sin registro identificado')])
            for x in facturas:
                w.writerow([emp, 'Factura FIFO', dmy(x['fecha']), x['num'],
                            money(x['importe']),
                            ', '.join(p['num'] + ' (' + money(t) + ')' for p, t in x['por']) or '—',
                            x['estado'],
                            ('No — falta cargar' if x['num'] in falt_ids
                             else f"Sí (ID {x['idsys']})")])
            for x in faltantes:
                w.writerow([emp, 'A cargar en flows', dmy(x['fecha']), x['num'],
                            money(x['importe']), '', '', 'No'])
    print('CSV ok')


if __name__ == '__main__':
    main()
