"""Conciliación mixta POLICOR vs vtacpaestadosaldo.pdf. Solo lectura, sin separar por empresa.

Reglas confirmadas: tolerancia importe <= $0,02, ventana Vto +-30 días,
desempate determinístico sin dejar ambiguos. Simula las 35 contrapartidas
faltantes en capa de conciliación, sin escribir en la DB. Corte saldo
inicial: fecha < 01/01/2026.
"""
from collections import Counter, defaultdict
from datetime import date as date_cls
from decimal import Decimal
import csv
import html
import json
from pathlib import Path
import re

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
MONEY = r'-?\d[\d.]*,\d{2}'
TOLERANCE = 2  # centavos = $0,02
WINDOW_DAYS = 30
COMPANY_RANK = {'Avanzia': 0, 'Sin empresa': 1, 'Condiseño': 2}


def cents(value):
    return int(Decimal(value.replace('.', '').replace(',', '.')) * 100)


def money(value):
    return '$ ' + f'{value / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def fmt_date(value):
    return '/'.join(reversed(value.split('-')))


def days_between(a, b):
    ya, ma, da = map(int, a.split('-'))
    yb, mb, db = map(int, b.split('-'))
    return abs((date_cls(ya, ma, da) - date_cls(yb, mb, db)).days)


def pdf_suffix(number):
    return int(number.split('-')[1])


def ref_numbers(reference):
    return [int(n) for n in re.findall(r'\d+', reference)]


def parse_pdf():
    pages = [p.extract_text(extraction_mode='layout') for p in PdfReader(ROOT / 'vtacpaestadosaldo.pdf').pages]
    text = '\n'.join(pages)
    opening = cents(re.search(r'Saldo al:\s+01/01/2026\s+(' + MONEY + ')', text)[1])
    closing = cents(re.search(r'Saldo al:\s+01/10/2026\s+(' + MONEY + ')', text)[1])
    totals = re.search(r'Total\s+(' + MONEY + r')\s+(' + MONEY + ')', text)
    rows = []
    for line in text.splitlines():
        match = re.match(r'\s*(\d{2}/\d{2}/\d{4})\s+([AX]:\d{4}-\d{8})\s+(Factura de Ventas|Recibo de Venta|Nota de Crédito de Venta)\s+(.*)', line)
        if not match:
            continue
        d, number, kind, rest = match.groups()
        amounts = re.findall(MONEY, rest)
        # En este PDF el extractor entrega Debe, Atraso(d), Haber, Saldo.
        if len(amounts) != 4:
            raise ValueError(f'Fila no reconocida: {line}')
        debit, _, credit, running = map(cents, amounts)
        rows.append(dict(date='-'.join(reversed(d.split('/'))), number=number,
                         kind=kind, debit=debit, credit=credit, balance=running))
    assert len(rows) == 48, len(rows)
    running = opening
    for r in rows:
        running += r['debit'] - r['credit']
        assert running == r['balance'], r
    assert running == closing
    assert sum(r['debit'] for r in rows) == cents(totals[1])
    assert sum(r['credit'] for r in rows) == cents(totals[2])
    return rows, opening, closing


def reconcile(external, internal):
    """Mixto: sin excluir por empresa; desempate determinístico."""
    used = set()
    for r in external:
        r['local'] = None
        r['note'] = ''
        r['match'] = 'Sin coincidencia identificada'
        pdf_net = r['debit'] - r['credit']
        suffix = pdf_suffix(r['number'])
        scored = []
        for v in internal:
            if v['id'] in used:
                continue
            if r['kind'] != 'Recibo de Venta':
                if v['flowid'] != 10303:
                    continue
                if (v['charges'] < 0) != (r['kind'] == 'Nota de Crédito de Venta'):
                    continue
                if suffix not in ref_numbers(v['reference']):
                    continue
                local_net = v['charges'] - v['payments']
            else:
                if v['flowid'] != 10150:
                    continue
                local_net = v['charges'] - v['payments']
            delta = abs(local_net - pdf_net)
            if delta > TOLERANCE:
                continue
            gap = days_between(v['date'], r['date'])
            if gap > WINDOW_DAYS:
                continue
            scored.append((COMPANY_RANK.get(v.get('company'), 1), delta, gap, int(v['id']), v))
        if not scored:
            continue
        scored.sort(key=lambda s: (s[0], s[1], s[2], s[3]))
        v = scored[0][4]
        r['local'] = v
        used.add(v['id'])
        delta = (v['charges'] - v['payments']) - pdf_net
        gap = days_between(v['date'], r['date'])
        if delta == 0 and gap == 0:
            r['match'] = 'Coincidencia'
        elif delta != 0 and gap == 0:
            r['match'] = 'Diferencia de importe tolerada'
        elif delta == 0 and gap != 0:
            r['match'] = 'Diferencia de fecha en ventana'
        else:
            r['match'] = 'Diferencia de importe y fecha en ventana'
        bits = []
        if delta:
            bits.append(f'Diferencia sistema − PDF: {money(delta)} (tolerada hasta $ 0,02).')
        if gap:
            bits.append(f'Fecha sistema {fmt_date(v["date"])} vs Vto PDF {fmt_date(r["date"])}: {gap} días (ventana ±30).')
        if len(scored) > 1:
            bits.append(f'Desempate entre {len(scored)} candidatos: {", ".join(s[4]["id"] for s in scored)}; orden Avanzia > Sin empresa > Condiseño, luego menor delta, fecha e ID.')
        bits.append('Factura/NC por número normalizado e importe; recibo por fecha/ventana e importe.')
        r['note'] = ' '.join(bits)
    assert len(used) == sum(r['local'] is not None for r in external)
    return [v for v in internal if v['id'] not in used]


def prior_breakdown(prior):
    by_year = defaultdict(lambda: [0, 0, 0])
    by_flow = defaultdict(lambda: [0, 0, 0])
    for v in prior:
        net = v['charges'] - v['payments']
        year = v['date'][:4]
        by_year[year][0] += v['charges']
        by_year[year][1] += v['payments']
        by_year[year][2] += net
        key = f"{v['flow']} · {v['status']}"
        by_flow[key][0] += v['charges']
        by_flow[key][1] += v['payments']
        by_flow[key][2] += net
    top_charges = sorted(prior, key=lambda v: v['charges'], reverse=True)[:10]
    top_payments = sorted(prior, key=lambda v: v['payments'], reverse=True)[:10]
    return by_year, by_flow, top_charges, top_payments


def main():
    external, opening, closing = parse_pdf()
    source = (ROOT / 'reporte_analisis_proveedores.html').read_text(encoding='utf-8')
    payload = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', source, re.S)[1])
    all_local = [v for v in payload['rows'] if v['provider'] == '986' and v['date'] <= '2026-10-01']
    internal = [v for v in all_local if v['date'] >= '2026-01-01']
    prior = [v for v in all_local if v['date'] < '2026-01-01']
    assert len(prior) == 70, len(prior)
    extras = reconcile(external, internal)
    matched = [r for r in external if r['local']]
    unmatched = [r for r in external if not r['local']]
    assert not any(r['match'] == 'Coincidencia ambigua' for r in external)
    local_open = sum(v['charges'] - v['payments'] for v in prior)
    local_close = sum(v['charges'] - v['payments'] for v in all_local)
    missing_net = sum((r['debit'] - r['credit']) for r in unmatched)
    simulated = local_close + missing_net
    bridge = [
        ('Saldo sistema mixto actual', local_close),
        ('Diferencia saldo inicial: PDF Avanzia − sistema mixto', opening - local_open),
        ('Facturas PDF sin coincidencia', sum(r['debit'] for r in unmatched)),
        ('Notas de crédito PDF sin coincidencia', -sum(r['credit'] for r in unmatched if r['kind'] == 'Nota de Crédito de Venta')),
        ('Recibos PDF sin coincidencia', -sum(r['credit'] for r in unmatched if r['kind'] == 'Recibo de Venta')),
        ('Cargos locales sin contraparte en este PDF (se retiran)', -sum(v['charges'] for v in extras)),
        ('Egresos locales sin contraparte en este PDF (se retiran)', sum(v['payments'] for v in extras)),
        ('Diferencias vinculadas PDF − sistema (toleradas)', sum((r['debit'] - r['credit']) - (r['local']['charges'] - r['local']['payments']) for r in matched)),
    ]
    assert sum(value for _, value in bridge) == closing
    assert len(internal) == len(matched) + len(extras)
    by_year, by_flow, top_charges, top_payments = prior_breakdown(prior)
    assert sum(v[2] for v in by_year.values()) == local_open
    summary = dict(pdf_rows=len(external), local_rows=len(internal), prior_rows=len(prior),
                   matches=len(matched), match_statuses=dict(Counter(r['match'] for r in external)),
                   missing_kinds=dict(Counter(r['kind'] for r in unmatched)),
                   pdf_open=opening, pdf_close=closing, local_open=local_open,
                   local_close=local_close, missing_net=missing_net, simulated=simulated,
                   pdf_debit=sum(r['debit'] for r in external), pdf_credit=sum(r['credit'] for r in external),
                   local_charges=sum(v['charges'] for v in internal),
                   local_payments=sum(v['payments'] for v in internal), bridge=bridge)
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    write_report(summary, external, extras, prior, by_year, by_flow,
                 top_charges, top_payments, payload['generated'])


def write_report(summary, external, extras, prior, by_year, by_flow,
                 top_charges, top_payments, generated):
    h = html.escape
    rows = []
    for r in external:
        v = r['local']
        rows.append('<tr>' + ''.join(f'<td>{h(str(value))}</td>' for value in (
            fmt_date(r['date']), r['number'], r['kind'], money(r['debit'] - r['credit']),
            v['id'] if v else '—', fmt_date(v['date']) if v else '—',
            money(v['charges'] - v['payments']) if v else '—',
            r['match'], r['note'])) + '</tr>')
    extra_rows = []
    for v in extras:
        extra_rows.append('<tr>' + ''.join(f'<td>{h(str(value))}</td>' for value in (
            fmt_date(v['date']), v['id'], v['reference'], v['status'],
            money(v['charges']), money(v['payments']))) + '</tr>')
    year_rows = ''.join(
        f'<tr><td>{y}</td><td class="num">{money(c)}</td><td class="num">{money(p)}</td><td class="num">{money(n)}</td></tr>'
        for y, (c, p, n) in sorted(by_year.items()))
    flow_rows = ''.join(
        f'<tr><td>{h(k)}</td><td class="num">{money(c)}</td><td class="num">{money(p)}</td><td class="num">{money(n)}</td></tr>'
        for k, (c, p, n) in sorted(by_flow.items()))
    top_c = ''.join(
        f'<tr><td>{fmt_date(v["date"])}</td><td>{v["id"]}</td><td>{h(v["reference"])}</td><td>{h(v["status"])}</td><td class="num">{money(v["charges"])}</td></tr>'
        for v in top_charges)
    top_p = ''.join(
        f'<tr><td>{fmt_date(v["date"])}</td><td>{v["id"]}</td><td>{h(v["reference"])}</td><td>{h(v["status"])}</td><td class="num">{money(v["payments"])}</td></tr>'
        for v in top_payments)
    bridge = ''.join(f'<tr><td>{h(label)}</td><td class="num">{money(value)}</td></tr>' for label, value in summary['bridge'])
    bridge += f'<tr><th>Saldo PDF Avanzia a pagar</th><th class="num">{money(summary["pdf_close"])}</th></tr>'
    sim_rows = ''.join(
        f'<tr><td>{fmt_date(r["date"])}</td><td>{h(r["number"])}</td><td>{h(r["kind"])}</td><td class="num">{money(r["debit"] - r["credit"])}</td></tr>'
        for r in external if not r['local'])
    content = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Conciliación POLICOR mixta</title>
<style>body{{font:15px/1.5 'Segoe UI',sans-serif;background:#f3f6f8;color:#263238;margin:0}}main{{max-width:1600px;margin:auto;padding:24px}}header,section{{background:white;padding:24px;border-radius:12px;margin-bottom:22px}}header{{background:#39265e;color:white}}h1,h2{{margin-top:0}}.wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:10px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}}th{{background:#72509a;color:white}}tr:nth-child(even){{background:#faf8fc}}.num{{text-align:right;white-space:nowrap}}a{{color:#72509a}}.note{{background:#fff5e5;padding:16px}}.total{{font-size:20px;font-weight:700;color:#39265e}}@media(max-width:600px){{main{{padding:10px}}section,header{{padding:15px}}}}</style></head><body><main>
<header><h1>Conciliación POLICOR — mixta, sin separar por empresa</h1><p>PDF del 01/10/2026 · Período 01/01/2026–01/10/2026 · Cuenta 13927 AVANZIA S.A.S.</p><p>Sistema mixto: proveedor POLICOR (986), corte 01/10/2026 · Fuente consultada {h(generated)}</p><p>Reglas: tolerancia $0,02, ventana Vto ±30 días, desempate determinístico, corte inicial &lt; 01/01/2026. Simulación sin escribir en DB.</p></header>
<section><h2>Resultado mixto</h2><p class="total">Sistema mixto actual: {money(summary['local_close'])} · Simulado con 35 contrapartidas: {money(summary['simulated'])} a pagar · PDF: {money(summary['pdf_close'])} a pagar</p>
<p>{summary['pdf_rows']} movimientos en el PDF; {summary['matches']} vinculados. Sin coincidencia: {summary['missing_kinds'].get('Factura de Ventas',0)} facturas, {summary['missing_kinds'].get('Nota de Crédito de Venta',0)} notas de crédito y {summary['missing_kinds'].get('Recibo de Venta',0)} recibo. Locales del período sin contraparte en este PDF: {len(extras)}.</p>
<p class="note">Mixto incluye todo POLICOR sin separar empresa; el PDF es solo Avanzia. Por eso el simulado ({money(summary['simulated'])}) no iguala al PDF ({money(summary['pdf_close'])}): resta {money(summary['pdf_close']-summary['simulated'])} explicada por saldo inicial mixto y extras. “Sin coincidencia” = sin contraparte por número/importe/fecha-ventana en esta fuente, no prueba ausencia en otro registro.</p>
<p>Filtro sistema: 10303 estado 1368 FACTURA DE COMPRA + 10150 CAJA Egresos. NC con importes negativos conservadas. Fecha PDF = Vto.</p>
<a href="vtacpaestadosaldo.pdf">Ver PDF original</a> · <a href="reporte_analisis_proveedores.html">Ver análisis de proveedores</a> · <a href="conciliacion_policor_pdf.csv">Descargar comparación CSV</a></section>
<section><h2>Saldo inicial mixto al 01/01/2026: {money(summary['local_open'])} a pagar</h2><p>{summary['prior_rows']} movimientos con fecha &lt; 01/01/2026. PDF abre con {money(summary['pdf_open'])} a favor Avanzia; distinto alcance.</p>
<h3>Por año</h3><div class="wrap"><table><thead><tr><th>Año</th><th>Cargos</th><th>Pagos</th><th>Neto</th></tr></thead><tbody>{year_rows}</tbody></table></div>
<h3>Por flujo y estado</h3><div class="wrap"><table><thead><tr><th>Flujo · Estado</th><th>Cargos</th><th>Pagos</th><th>Neto</th></tr></thead><tbody>{flow_rows}</tbody></table></div>
<h3>Top 10 cargos del saldo inicial</h3><div class="wrap"><table><thead><tr><th>Fecha</th><th>ID</th><th>Referencia</th><th>Estado</th><th>Cargos</th></tr></thead><tbody>{top_c}</tbody></table></div>
<h3>Top 10 pagos del saldo inicial</h3><div class="wrap"><table><thead><tr><th>Fecha</th><th>ID</th><th>Referencia</th><th>Estado</th><th>Pagos</th></tr></thead><tbody>{top_p}</tbody></table></div></section>
<section><h2>Simulación mixta: 35 contrapartidas por {money(summary['missing_net'])}</h2><p>Sistema mixto {money(summary['local_close'])} + contrapartidas {money(summary['missing_net'])} = <strong>{money(summary['simulated'])}</strong>. Solo capa de conciliación, sin asientos.</p><div class="wrap"><table><thead><tr><th>Vto PDF</th><th>Número</th><th>Tipo</th><th>Importe simulado</th></tr></thead><tbody>{sim_rows}</tbody></table></div></section>
<section><h2>Puente hasta el PDF</h2><div class="wrap"><table><thead><tr><th>Concepto</th><th>Importe con signo</th></tr></thead><tbody>{bridge}</tbody></table></div></section>
<section><h2>Comparación de los 48 movimientos del PDF</h2><p>Importe positivo: cargo; negativo: recibo o nota de crédito.</p><label>Buscar <input id="search" type="search" placeholder="Número, fecha, diferencia..."></label><div class="wrap"><table id="comparison"><thead><tr><th>Vto PDF</th><th>Número PDF</th><th>Tipo PDF</th><th>Importe PDF</th><th>ID sistema</th><th>Fecha sistema</th><th>Importe sistema</th><th>Resultado</th><th>Observación</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
<section><h2>Locales del período sin contraparte en este PDF</h2><div class="wrap"><table><thead><tr><th>Fecha</th><th>ID</th><th>Referencia</th><th>Estado</th><th>Cargos</th><th>Pagos</th></tr></thead><tbody>{''.join(extra_rows)}</tbody></table></div></section>
<footer>Control: saldos acumulados del PDF y totales verificados; puente cierra al centavo. No se modificaron datos del sistema.</footer>
<script>document.getElementById('search').addEventListener('input',e=>{{const q=e.target.value.toLocaleLowerCase('es');for(const r of document.querySelectorAll('#comparison tbody tr'))r.hidden=!r.textContent.toLocaleLowerCase('es').includes(q);}});</script></main></body></html>'''
    (ROOT / 'reporte_conciliacion_policor_pdf.html').write_text(content, encoding='utf-8')
    with (ROOT / 'conciliacion_policor_pdf.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['Vto PDF','Comprobante PDF','Tipo PDF','Debe PDF','Haber PDF','Saldo PDF','ID sistema','Fecha sistema','Referencia sistema','Cargo sistema','Pago sistema','Resultado','Observación'])
        for r in external:
            v = r['local'] or {}
            writer.writerow([fmt_date(r['date']),r['number'],r['kind'],money(r['debit']),money(r['credit']),money(r['balance']),
                             v.get('id',''),fmt_date(v['date']) if v else '',v.get('reference',''),
                             money(v['charges']) if v else '',money(v['payments']) if v else '',r['match'],r['note']])


if __name__ == '__main__':
    main()
