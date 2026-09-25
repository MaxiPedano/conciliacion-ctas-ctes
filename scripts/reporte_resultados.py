"""Estado gerencial trazable. Origen de solo lectura; no modifica asignaciones."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json
import re
import unicodedata
from resultado_origen import Origen, ROOT

SNAPSHOT = ROOT / 'outputs/estado_resultados_origen.json'
EMPRESAS = {10986: 'Avanzia', 11369: 'Condiseño', 11477: 'Bistro'}
VENTAS = {10781, 11547}
COMPROBANTES = VENTAS | {10303, 10290, 11366, 11470, 11330, 11544}
CAJA = {10150, 11332, 11344, 11433, 10815, 10223, 11347, 11328,
        11541, 11556, 11349, 11346}
ESTADOS = {
    10781: {1319}, 11547: {1319}, 10303: {1368, 1372, 1311},
    10290: {1311}, 11366: {1140}, 11330: {1370}, 11544: {1399},
    10150: {1147}, 11332: {1167}, 11344: {1167}, 11433: {1167},
    10815: {1281}, 10223: {1281},
}

QUERY = """
SELECT
 (SELECT json_agg(q) FROM (
  SELECT r.id,r.fecha::text fecha,r.referenciatexto referencia,r.clientname cliente,
   r.flowid,f.name flujo,r.cuentacontableid cuenta_id,r.totalprecio::text neto,
   r.totalimpuestos::text total,r.statusid estado_cab,sf.statusid estado_id,s.descrip estado
  FROM test9000.registrocab r
  LEFT JOIN test9000.categorias f ON f.id=r.flowid
  LEFT JOIN test9000.statusflows sf ON sf.id=r.statusflowid
  LEFT JOIN test9000.statuses s ON s.id=sf.statusid ORDER BY r.id
 ) q) registros,
 (SELECT json_agg(q) FROM (
  SELECT b.id,b.presupcabid registro_id,b.cantidad,b.preciototal::text neto,
   b.preciototalimpu::text total,b.impuestoalic::text alicuota,
   a.id articulo_id,a.nombre articulo,a.isservice servicio,a.ischeque cheque,a.um unidad,
   c.name categoria,c.valor categoria_valor
  FROM test9000.registrocuerpo b
  LEFT JOIN test9000.depositosarticulos d ON d.id=b.articulodepositoid
  LEFT JOIN test9000.articulos a ON a.id=d.articuloid
  LEFT JOIN test9000.categorias c ON c.id=a.categid ORDER BY b.id
 ) q) lineas,
 (SELECT json_agg(q) FROM (SELECT id,name,parentid,grupo FROM test9000.categorias) q) cuentas,
 (SELECT json_agg(q) FROM (SELECT registrocabid a,relatedregistrocabid b FROM test9000.registrocabrel) q) relaciones
"""

def normal(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s or '') if not unicodedata.combining(c)).upper()

def cents(v):
    return None if v is None else int((Decimal(str(v)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def build(data):
    accounts = {c['id']: c for c in data['cuentas']}
    records = {r['id']: dict(r) for r in data['registros']}
    bodies = defaultdict(list)
    for b in data['lineas'] or []:
        bodies[b['registro_id']].append(b)
    adjacent = defaultdict(set)
    dangling = 0
    for edge in data['relaciones'] or []:
        a, b = edge['a'], edge['b']
        if a not in records or b not in records:
            dangling += 1
            continue
        if a != b:
            adjacent[a].add(b)
            adjacent[b].add(a)

    def chain(cid):
        result, seen = [], set()
        while cid in accounts:
            if cid in seen:
                raise ValueError('Ciclo en plan de cuentas')
            seen.add(cid)
            result.append(accounts[cid])
            cid = accounts[cid]['parentid']
        return result

    def classify(cid):
        path = chain(cid)
        company = next((EMPRESAS[c['id']] for c in path if c['id'] in EMPRESAS), 'Sin empresa identificada')
        text = normal(' > '.join(c['name'] for c in reversed(path)))
        leaf = normal(path[0]['name']) if path else ''
        if any(c['id'] in {10983,10984,10985} for c in path):
            return company, 'Patrimonial', text
        if company == 'Sin empresa identificada':
            return company, 'Sin clasificación', text
        if any(c['id'] in {11106,11370,11478} for c in path):
            cat = 'Ingresos financieros' if ('INTERESES' in text or 'FIMA' in text) else 'Otros ingresos'
        elif 'COSTO DE VENTAS' in leaf:
            cat = 'Costo de ventas registrado'
        elif any(c['id'] == 11355 for c in path):
            cat = 'Compras de producción por devengar'
        elif 'INTERESES' in leaf or 'GASTOS BANCARIOS' in leaf or 'GASTOS FINANCIEROS' in text:
            cat = 'Gastos financieros'
        elif 'ADMINISTRACION' in text:
            cat = 'Gastos administrativos'
        elif 'COMERCIALIZACION' in text:
            cat = 'Gastos comerciales'
        elif 'DIRECTORIO' in text:
            cat = 'Gastos de directorio'
        elif 'FABRICACION' in text:
            cat = 'Gastos de fabricación registrados'
        elif 'IMPUESTOS' in text:
            cat = 'Impuestos registrados'
        else:
            cat = 'Otros gastos'
        return company, cat, text

    result, items = [], []
    for rid, src in records.items():
        r = {k: (src.get(k) or '') for k in ['fecha','referencia','cliente','flujo','estado']}
        r.update(id=rid, flowid=src['flowid'], estado_id=src['estado_id'], estado_cab=src['estado_cab'], cuenta_id=src['cuenta_id'])
        company, concept, path = classify(src['cuenta_id'])
        related = sorted(adjacent[rid])
        linked_docs = [x for x in related if records[x]['flowid'] in COMPROBANTES]
        r.update(empresa=company, concepto=concept,
                 cuenta=accounts.get(src['cuenta_id'], {}).get('name', 'Sin cuenta'),
                 ruta=path, relacionados=related,
                 cuentas_relacionadas=[{'id': x, 'cuenta': records[x]['cuenta_id']} for x in related if records[x]['cuenta_id'] is not None],
                 neto=cents(src['neto']), total=cents(src['total']), estado_analisis='pendiente', motivo='')
        r['impuestos'] = None if r['neto'] is None or r['total'] is None else r['total'] - r['neto']
        flow, status = src['flowid'], src['estado_id']
        state_text = normal(src['estado'])
        if flow in CAJA and linked_docs:
            state, reason = 'cubierto', 'Pago/cobro vinculado a comprobante; no se suma de nuevo'
        elif 'REMITO' in state_text:
            state, reason = 'despacho', 'Movimiento de stock; no es venta facturada'
        elif flow in {11321,11322,11331,11324,11349,11541,11556,11346,11476,10386,10707}:
            state, reason = 'excluido', 'Transferencia, capital, cheque o reversión; no constituye resultado por sí mismo'
        elif concept == 'Patrimonial':
            state, reason = 'excluido', 'Cuenta de activo, pasivo o patrimonio; no es gasto ni ingreso'
        elif re.search(r'ANUL|CANCELAD|BORRADOR', state_text):
            state, reason = 'excluido', 'Documento anulado o borrador'
        elif src['cuenta_id'] is None and r['cuentas_relacionadas']:
            state, reason = 'relacionado', 'Sin cuenta propia; relacionado con cuenta (no se hereda)'
        elif status not in ESTADOS.get(flow, set()):
            state, reason = 'pendiente', 'Estado/flujo no reconocido como devengado; revisar'
        elif r['neto'] is None:
            state, reason = 'pendiente', 'Sin importe neto'
        elif src['cuenta_id'] is None:
            state = 'relacionado' if r['cuentas_relacionadas'] else 'pendiente'
            reason = 'Sin cuenta propia; relacionado con cuenta (no se hereda)' if state == 'relacionado' else 'Sin cuenta propia ni cuenta en relacionados'
        elif company == 'Sin empresa identificada':
            state, reason = 'pendiente', 'Cuenta fuera de las ramas de resultados por empresa'
        elif concept == 'Compras de producción por devengar':
            state, reason = 'pendiente', 'Materias primas: falta consumo/variación de inventario; no convertir compra en costo vendido'
        elif flow in VENTAS and concept not in {'Otros ingresos','Ingresos financieros'}:
            state, reason = 'pendiente', 'Venta con cuenta que no es de ingresos'
        elif flow in {10150,11332,11344,11433,10303,10290,11366,11544} and concept in {'Otros ingresos','Ingresos financieros'}:
            state, reason = 'pendiente', 'Comprobante de egreso con cuenta de ingresos: verificar naturaleza'
        elif flow in {10815,10223,11330} and concept not in {'Otros ingresos','Ingresos financieros'}:
            state, reason = 'pendiente', 'Comprobante de ingreso con cuenta de gastos: verificar naturaleza'
        elif flow in VENTAS and re.search(r'NOTA\s+DE\s+CREDITO|\bN\.?\s*C\.?\b', normal(src['referencia'])) and r['neto'] > 0:
            state, reason = 'pendiente', 'Posible nota de crédito con signo positivo; verificar naturaleza y signo'
        else:
            state, reason = 'incluido', 'Cuenta propia, estado reconocido e importe neto'
            if flow in VENTAS:
                r['concepto'] = 'Ventas netas facturadas'
            elif flow in CAJA:
                reason = 'Caja independiente con cuenta de resultados; sin comprobante vinculado'
        r.update(estado_analisis=state, motivo=reason)
        own_bodies = bodies[rid]
        line_sum = sum(cents(b['neto']) or 0 for b in own_bodies)
        delta = (r['neto'] or 0) - line_sum
        tolerance = max(5, len(own_bodies))
        r['diferencia_cabecera'] = delta
        if state == 'incluido' and own_bodies and (abs(delta) > tolerance or any(b['neto'] is None for b in own_bodies)):
            r.update(estado_analisis='pendiente', motivo='Diferencia cabecera/renglones o neto de línea ausente; requiere conciliación')
        fiscal = 0
        for b in own_bodies:
            name = normal(b['articulo'])
            # IVA/percepciones explícitas dentro del neto no son automáticamente gasto.
            tax_line = bool(re.search(r'^(IVA\b|PERCEP|RETENC)', name)) and 'IVA NO COMPUTABLE' not in normal(r['cuenta'])
            amount = cents(b['neto']) or 0
            if tax_line:
                fiscal += amount
            generic = (b['cheque'] or 'FINANCIERO' in normal(b['categoria']) or
                       name in {'COMPRAS VARIAS','SERVICIO GENERICO','DINERO - PESOS','DINERO - DOLAR'} or not b['articulo_id'])
            quantity = b['cantidad'] or 0
            # Un ajuste monetario negativo con cantidad positiva puede ser una bonificación,
            # no una devolución física. No convertirlo en unidades vendidas ni devueltas.
            sales_quantity = None if amount < 0 and quantity >= 0 else quantity
            items.append(dict(registro_id=rid, linea_id=b['id'], articulo_id=b['articulo_id'],
                              articulo=b['articulo'] or 'Artículo no identificado', categoria=b['categoria'] or '',
                              unidad=b['unidad'] or '', cantidad=quantity, cantidad_venta=sales_quantity,
                              neto=amount, total=cents(b['total']), alicuota=b['alicuota'],
                              fiscal=tax_line, generico=bool(generic), servicio=bool(b['servicio'])))
        r['fiscal_separado'] = fiscal
        r['importe_resultado'] = (r['neto'] or 0) - fiscal if r['estado_analisis'] == 'incluido' else 0
        r['signo'] = 1 if r['concepto'] in {'Ventas netas facturadas','Otros ingresos','Ingresos financieros'} else -1
        r['lineas'] = len(own_bodies)
        result.append(r)

    # Todas las cabeceras tienen una única decisión y ninguna relación duplica importes.
    assert len(result) == len(records) == len({r['id'] for r in result})
    assert len(items) == len({b['linea_id'] for b in items})
    assert not any(r['estado_analisis'] == 'incluido' and r['flowid'] in CAJA and
                   any(records[x]['flowid'] in COMPROBANTES for x in r['relacionados']) for r in result)
    assert not any(r['estado_analisis'] == 'incluido' and 'REMITO' in normal(r['estado']) for r in result)
    return dict(generado=datetime.now().isoformat(timespec='seconds'), registros=result, lineas=items,
                controles={'registros': len(result), 'lineas': len(items), 'relaciones_huerfanas': dangling,
                           'estados': dict(Counter(r['estado_analisis'] for r in result))})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', action='store_true', help='Reutilizar instantánea local, sin consultar origen')
    args = parser.parse_args()
    if args.cache:
        source = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    else:
        with Origen() as origin:
            source = origin.query(QUERY)[0]  # Una sola sentencia: snapshot consistente.
        SNAPSHOT.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
    data = build(source)
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('&', '\\u0026')
    template = (ROOT / 'scripts/estado_resultados.html').read_text(encoding='utf-8')
    (ROOT / 'reporte_estado_resultados.html').write_text(template.replace('__DATOS_RESULTADOS__', payload), encoding='utf-8')
    print(json.dumps(data['controles'], ensure_ascii=True))
    for company in EMPRESAS.values():
        rows = [r for r in data['registros'] if r['empresa'] == company and r['estado_analisis'] == 'incluido']
        print(company, len(rows), 'resultado parcial:', sum(r['importe_resultado'] * r['signo'] for r in rows) / 100)

if __name__ == '__main__':
    main()
