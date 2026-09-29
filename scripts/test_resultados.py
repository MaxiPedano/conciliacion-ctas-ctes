"""Regresiones contables: alcance de producto terminado, empresa por depósito y unidades."""
import unittest
from reporte_resultados import build

FAB, MESA = 10626, 10670
IMP, TIFFANY = 11428, 11363
OTRA, ALMOHADON = 9000, 9001

def account(i, name, parent=None):
    return dict(id=i, name=name, parentid=parent, grupo='cuentacontable')

def category(i, name, parent=None):
    return dict(id=i, name=name, parentid=parent, grupo='articulos')

def record(i, flow, status, account_id, amount='100'):
    return dict(id=i, fecha='2026-01-15', referencia='Factura', cliente='Prueba', flowid=flow,
                flujo='VENTA: AVANZIA' if flow in (10781, 11547) else 'Otro', cuenta_id=account_id,
                neto=amount, total=amount, estado_cab=status, estado_id=status,
                estado={1319: 'FACTURA DE VENTA', 1291: 'Notificación a Producción',
                        1292: 'OV AVANZIA', 1400: 'OV Mercadolibre',
                        1172: 'Auditar las ventas'}.get(status, 'Estado %s' % status))

def line(i, rid, amount='100', name='Mesa Redonda', cat=MESA):
    return dict(id=i, registro_id=rid, cantidad=1, neto=amount, total=amount, alicuota='0',
                articulo_id=50, articulo=name, servicio=False, cheque=False, unidad='UN',
                categoria_id=cat, categoria='Mesa')

class ScopeTests(unittest.TestCase):
    def data(self, rs, bs=None):
        return dict(registros=rs, lineas=bs or [], cuentas=[
            account(10986, 'RESULTADOS AVANZIA'), account(11106, 'INGRESOS', 10986),
            account(10, 'Ventas de fabricados', 11106),
            account(11369, 'RESULTADOS CONDISEÑO'), account(11370, 'INGRESOS', 11369),
            account(11, 'Ventas importadas', 11370),
            account(11477, 'RESULTADOS BISTRO'), account(11478, 'INGRESOS', 11477),
            account(12, 'Ventas Bistro', 11478),
            category(FAB, 'P.T. FABRICADOS'), category(MESA, 'Mesa', FAB),
            category(IMP, 'P.T. IMPORTADOS'), category(TIFFANY, 'Sillas Tiffany', IMP),
            category(OTRA, 'ARTÍCULOS'), category(ALMOHADON, 'Almohadones', OTRA)])

    def test_solo_estados_de_venta_y_producto_terminado(self):
        d = self.data([record(1, 10781, 1319, 10), record(2, 10781, 1291, 10),
                       record(3, 11444, 1114, 10), record(4, 10781, 1319, 10),
                       record(5, 10781, 1291, 10)],
                      [line(1, 1), line(2, 2), line(3, 3), line(4, 4, cat=ALMOHADON),
                       line(5, 5, cat=ALMOHADON)])
        out = build(d)
        self.assertEqual([r['id'] for r in out['registros']], [1, 2])
        self.assertEqual([r['id'] for r in out['excluidos']], [4, 5])
        self.assertTrue(all('Sin renglón' in e['motivo'] for e in out['excluidos']))
        self.assertEqual(out['controles']['lineas_producto_fuera_de_alcance'], 1)
        self.assertEqual(out['controles']['registros_producto_fuera_de_alcance'], 1)

    def test_estados_ajenos_a_venta_quedan_fuera_con_motivo(self):
        d = self.data([record(1, 10781, 1292, 10), record(2, 11547, 1400, 10),
                       record(3, 10781, 1172, 10)],
                      [line(1, 1), line(2, 2), line(3, 3)])
        out = build(d)
        self.assertEqual(out['registros'], [])
        self.assertEqual([e['estado_id'] for e in out['excluidos']], [1292, 1400, 1172])
        self.assertTrue(all('1291' in e['motivo'] and '1319' in e['motivo'] for e in out['excluidos']))
        self.assertEqual(out['controles']['excluidos_ventas'], 3)

    def test_empresa_por_raiz_del_producto_y_cuenta_bistro(self):
        d = self.data([record(1, 10781, 1319, 11), record(2, 10781, 1319, 10),
                       record(3, 10781, 1319, 12)],
                      [line(1, 1), line(2, 2, name='Tiffany', cat=TIFFANY), line(3, 3, name='Tiffany', cat=TIFFANY)])
        out = build(d)
        self.assertEqual([b['empresa'] for b in out['lineas']], ['Avanzia', 'Condiseño', 'Bistro'])
        self.assertEqual([r['empresa'] for r in out['registros']], ['Avanzia', 'Condiseño', 'Bistro'])

    def test_renglon_ajeno_a_las_raices_no_suma(self):
        d = self.data([record(1, 10781, 1319, 10, '150')],
                      [line(1, 1, '100'), line(2, 1, '50', 'Almohadones', ALMOHADON)])
        out = build(d)
        self.assertEqual(len(out['registros']), 1)
        self.assertEqual(len(out['lineas']), 1)
        self.assertEqual(out['registros'][0]['neto_pt'], 10000)
        self.assertEqual(out['registros'][0]['neto_fuera_pt'], 5000)
        self.assertEqual(out['registros'][0]['diferencia_cabecera'], 0)

    def test_unidades_negativas_no_se_suman(self):
        d = self.data([record(1, 10781, 1319, 10, '-100'), record(2, 10781, 1319, 10)],
                      [line(1, 1, '-100'), line(2, 2, '80')])
        out = build(d)
        self.assertEqual(out['controles']['unidades_a_revisar'], 1)
        self.assertEqual(sum(b['cantidad_venta'] or 0 for b in out['lineas']), 1)
        self.assertEqual(sum(b['neto'] for b in out['lineas']), -2000)

    def test_factura_con_dos_raices_se_marca_varias_empresas(self):
        d = self.data([record(1, 10781, 1319, 10)],
                      [line(1, 1, '60'), line(2, 1, '40', 'Tiffany', TIFFANY)])
        out = build(d)
        self.assertEqual(out['registros'][0]['empresa'], 'Varias empresas')
        self.assertEqual([b['empresa'] for b in out['lineas']], ['Avanzia', 'Condiseño'])

    def test_una_cabecera_una_decision_y_totales_cierran(self):
        d = self.data([record(1, 10781, 1319, 10, '300'), record(2, 11547, 1319, 11, '120')],
                      [line(1, 1, '100'), line(2, 1, '200'), line(3, 2, '120')])
        out = build(d)
        self.assertEqual(len(out['registros']), 2)
        self.assertEqual(len({r['id'] for r in out['registros']}), 2)
        self.assertEqual(len({b['linea_id'] for b in out['lineas']}), 3)
        self.assertEqual(sum(b['neto'] for b in out['lineas']), sum(r['neto_pt'] for r in out['registros']))
        self.assertTrue(all(r['estado_id'] in (1319, 1291) for r in out['registros']))
        self.assertTrue(all(b['raiz_id'] in (FAB, IMP) for b in out['lineas']))

    def test_cuenta_sin_empresa_no_bloquea_la_venta(self):
        d = self.data([record(1, 10781, 1319, None)], [line(1, 1)])
        out = build(d)
        self.assertEqual(out['registros'][0]['empresa'], 'Avanzia')
        self.assertEqual(out['controles']['sin_cuenta_propia'], 1)

if __name__ == '__main__':
    unittest.main()
