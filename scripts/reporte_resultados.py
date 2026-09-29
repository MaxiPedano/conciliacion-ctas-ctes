"""Estado de resultados de productos terminados. Origen de solo lectura; no modifica asignaciones."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json
from resultado_origen import Origen, ROOT

SNAPSHOT = ROOT / 'outputs/estado_resultados_origen.json'
EMPRESAS = {10986: 'Avanzia', 11369: 'Condiseño', 11477: 'Bistro'}
VENTAS = {10781, 11547}
# Estados que esta vista considera venta: factura emitida y OV ya notificada a producción.
ESTADOS_VENTA = {1319: 'FACTURA DE VENTA', 1291: 'Notificación a Producción'}
ESTADO_TEXTO = ' / '.join('%s %s' % (k, v) for k, v in sorted(ESTADOS_VENTA.items()))
# Raíces de categoría que definen el producto terminado vendible y su empresa.
RAICES = {10626: 'Fabricados', 11428: 'Importados'}
EMPRESA_RAIZ = {10626: 'Avanzia', 11428: 'Condiseño'}
FLUJOS_PT = {11441: 'Remito de recepción', 11444: 'Remito de salida',
             10386: 'Comprobante interno', 10303: 'Comprobantes de proveedores'}

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
   c.id categoria_id,c.name categoria,c.valor categoria_valor
  FROM test9000.registrocuerpo b
  LEFT JOIN test9000.depositosarticulos d ON d.id=b.articulodepositoid
  LEFT JOIN test9000.articulos a ON a.id=d.articuloid
  LEFT JOIN test9000.categorias c ON c.id=a.categid ORDER BY b.id
 ) q) lineas,
 (SELECT json_agg(q) FROM (SELECT id,name,parentid,grupo FROM test9000.categorias) q) cuentas,
 (SELECT json_agg(q) FROM (SELECT registrocabid a,relatedregistrocabid b FROM test9000.registrocabrel) q) relaciones
"""

def cents(v):
    return None if v is None else int((Decimal(str(v)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def nid(v):
    return None if v is None else int(v)

def build(data):
    accounts = {nid(c['id']): c for c in data['cuentas']}
    records = {nid(r['id']): dict(r) for r in data['registros']}
    bodies = defaultdict(list)
    for b in data['lineas'] or []:
        bodies[nid(b['registro_id'])].append(b)

    def chain(cid):
        result, seen = [], set()
        cid = nid(cid)
        while cid in accounts:
            if cid in seen:
                raise ValueError('Ciclo en plan de cuentas')
            seen.add(cid)
            result.append(accounts[cid])
            cid = nid(accounts[cid]['parentid'])
        return result

    def empresa_de_cuenta(cid):
        return next((EMPRESAS[c['id']] for c in chain(cid) if c['id'] in EMPRESAS), None)

    def raiz_de_categoria(cid):
        return next((c['id'] for c in chain(cid) if c['id'] in RAICES), None)

    # Renglones de producto terminado por comprobante, y conteo de lo que queda fuera.
    pt_por_registro = defaultdict(list)
    fuera_alcance = Counter()
    fuera_alcance_registros = set()
    for b in data['lineas'] or []:
        rid = nid(b['registro_id'])
        raiz = raiz_de_categoria(b.get('categoria_id'))
        if not raiz:
            continue
        src = records.get(rid)
        if src is None or src['flowid'] not in VENTAS:
            fuera_alcance[FLUJOS_PT.get(src['flowid'] if src else None, 'Otro flujo')] += 1
            fuera_alcance_registros.add(rid)
            continue
        pt_por_registro[rid].append((b, raiz))

    result, items, excluidos = [], [], []
    for rid in sorted(records):
        src = records[rid]
        flow, status = src['flowid'], nid(src['estado_id'])
        if flow not in VENTAS:
            continue
        propios = pt_por_registro.get(rid, [])
        if status not in ESTADOS_VENTA:
            excluidos.append(dict(id=rid, fecha=src['fecha'] or '', referencia=src['referencia'] or '',
                                  cliente=src['cliente'] or '', flujo=src['flujo'] or '',
                                  estado=src['estado'] or '', estado_id=status,
                                  empresa=empresa_de_cuenta(src['cuenta_id']) or 'Sin empresa identificada',
                                  neto=cents(src['neto']),
                                  motivo='Estado «%s» no es de venta (admitidos: %s)'
                                         % (src['estado'] or status, ESTADO_TEXTO)))
            continue
        if not propios:
            excluidos.append(dict(id=rid, fecha=src['fecha'] or '', referencia=src['referencia'] or '',
                                  cliente=src['cliente'] or '', flujo=src['flujo'] or '',
                                  estado=src['estado'] or '', estado_id=status,
                                  empresa=empresa_de_cuenta(src['cuenta_id']) or 'Sin empresa identificada',
                                  neto=cents(src['neto']),
                                  motivo='Sin renglón bajo P.T. FABRICADOS / P.T. IMPORTADOS'))
            continue

        cuenta_id = nid(src['cuenta_id'])
        empresa_cuenta = empresa_de_cuenta(cuenta_id)
        path = chain(cuenta_id)
        r = {k: (src.get(k) or '') for k in ['fecha', 'referencia', 'cliente', 'flujo', 'estado']}
        r.update(id=rid, flowid=flow, estado_id=status, estado_cab=nid(src['estado_cab']),
                 cuenta_id=cuenta_id, cuenta=accounts.get(cuenta_id, {}).get('name', 'Sin cuenta'),
                 ruta=' > '.join(c['name'] for c in reversed(path)),
                 neto=cents(src['neto']), total=cents(src['total']))
        r['impuestos'] = None if r['neto'] is None or r['total'] is None else r['total'] - r['neto']

        neto_pt, cuentas_empresas = 0, set()
        for b, raiz in propios:
            # Depósito de la empresa: la raíz del producto manda; una cuenta de Bistro
            # se respeta por encima de la raíz (cada empresa factura su depósito).
            empresa = 'Bistro' if empresa_cuenta == 'Bistro' else EMPRESA_RAIZ[raiz]
            cuentas_empresas.add(empresa)
            amount = cents(b['neto']) or 0
            quantity = b['cantidad'] or 0
            # Un ajuste monetario negativo con cantidad positiva puede ser una bonificación,
            # no una devolución física: no se suma a las unidades vendidas.
            sales_quantity = None if amount < 0 and quantity >= 0 else quantity
            neto_pt += amount
            items.append(dict(registro_id=rid, linea_id=nid(b['id']), articulo_id=nid(b['articulo_id']),
                              articulo=b['articulo'] or 'Artículo no identificado',
                              categoria=b['categoria'] or '', categoria_id=nid(b['categoria_id']),
                              raiz=RAICES[raiz], raiz_id=raiz, empresa=empresa,
                              unidad=b['unidad'] or '', cantidad=quantity, cantidad_venta=sales_quantity,
                              neto=amount, total=cents(b['total']), alicuota=b['alicuota']))
        r['empresas'] = sorted(cuentas_empresas)
        r['empresa'] = r['empresas'][0] if len(r['empresas']) == 1 else 'Varias empresas'
        r['neto_pt'] = neto_pt
        r['neto_fuera_pt'] = (r['neto'] or 0) - neto_pt
        r['lineas'] = len(propios)
        line_sum = sum(cents(b['neto']) or 0 for b in bodies[rid])
        r['diferencia_cabecera'] = (r['neto'] or 0) - line_sum
        r['estado_analisis'] = 'incluido'
        result.append(r)

    # Una cabecera aparece una sola vez; el total de la tabla cierra con la suma de renglones.
    assert len(result) == len({r['id'] for r in result})
    assert len(items) == len({b['linea_id'] for b in items})
    assert all(b['raiz_id'] in RAICES for b in items)
    assert all(r['flowid'] in VENTAS for r in result)
    assert sum(b['neto'] for b in items) == sum(r['neto_pt'] for r in result)
    assert all(r['estado_id'] in ESTADOS_VENTA for r in result)
    return dict(generado=datetime.now().isoformat(timespec='seconds'), registros=result, lineas=items,
                excluidos=excluidos,
                controles={'registros': len(records), 'lineas': len(data['lineas'] or []),
                           'incluidos': len(result), 'excluidos_ventas': len(excluidos),
                           'lineas_producto': len(items),
                           'lineas_producto_fuera_de_alcance': sum(fuera_alcance.values()),
                           'registros_producto_fuera_de_alcance': len(fuera_alcance_registros),
                           'fuera_de_alcance_por_flujo': dict(fuera_alcance),
                           'sin_cuenta_propia': sum(1 for r in result if r['cuenta_id'] is None),
                           'diferencias_cabecera_renglon': sum(1 for r in result if r['diferencia_cabecera']),
                           'unidades_a_revisar': sum(1 for b in items if b['cantidad_venta'] is None),
                           'duplicados_cabecera': 0})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', action='store_true', help='Reutilizar instantánea local, sin consultar origen')
    args = parser.parse_args()
    if args.cache:
        source = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        lineas = source.get('lineas') or []
        if lineas and 'categoria_id' not in lineas[0]:
            raise SystemExit('La instantánea es anterior al alcance de producto terminado: '
                             'corré sin --cache para refrescarla desde el origen.')
    else:
        with Origen() as origin:
            source = origin.query(QUERY)[0]  # Una sola sentencia: snapshot consistente.
        SNAPSHOT.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
    data = build(source)
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('&', '\\u0026')
    template = (ROOT / 'scripts/estado_resultados.html').read_text(encoding='utf-8')
    (ROOT / 'reporte_estado_resultados.html').write_text(template.replace('__DATOS_RESULTADOS__', payload), encoding='utf-8')
    print(json.dumps(data['controles'], ensure_ascii=True))
    for company in tuple(EMPRESA_RAIZ.values()) + ('Bistro',):
        rows = [b for b in data['lineas'] if b['empresa'] == company]
        print(company, len(rows), 'renglones | registros',
              len({b['registro_id'] for b in rows}),
              '| neto', sum(b['neto'] for b in rows) / 100,
              '| unidades', sum(b['cantidad_venta'] or 0 for b in rows))
    print('TOTAL', len(data['lineas']), '| neto', sum(b['neto'] for b in data['lineas']) / 100,
          '| unidades', sum(b['cantidad_venta'] or 0 for b in data['lineas']))

if __name__ == '__main__':
    main()
