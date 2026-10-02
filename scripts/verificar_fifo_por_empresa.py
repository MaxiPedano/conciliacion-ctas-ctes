"""Controles de asignación FIFO y cierre de los estados de POLICOR."""
import unittest
from reporte_fifo_por_empresa import fifo, load_avanzia, load_condiseno


def movimiento(fecha, importe, num):
    return dict(fecha=fecha, importe=importe, num=num)


class FIFOTests(unittest.TestCase):
    def test_pago_posterior_cancela_primero_factura_antigua(self):
        facturas = [movimiento('2026-01-02', 100, 'F1'),
                    movimiento('2026-01-03', 100, 'F2')]
        pagos = [movimiento('2026-01-04', 150, 'P1')]
        fifo(pagos, facturas)
        self.assertEqual([f['cubierto'] for f in facturas], [100, 50])
        self.assertEqual(pagos[0]['remanente'], 0)

    def test_anticipo_y_pago_posterior(self):
        pagos = [movimiento('2026-01-01', 70, 'P1'),
                 movimiento('2026-01-04', 150, 'P2')]
        facturas = [movimiento('2026-01-02', 100, 'F1'),
                    movimiento('2026-01-03', 100, 'F2')]
        fifo(pagos, facturas)
        self.assertEqual([(p['num'], t) for p, t in facturas[0]['por']],
                         [('P1', 70), ('P2', 30)])
        self.assertEqual([p['remanente'] for p in pagos], [0, 20])
        fifo(pagos, facturas)
        self.assertEqual([p['remanente'] for p in pagos], [0, 20])

    def test_avanzia_cierra_en_ultima_factura(self):
        pagos, facturas = load_avanzia()
        fifo(pagos, facturas)
        pendientes = [(f['num'], f['importe'] - f['cubierto'])
                      for f in facturas if f['importe'] != f['cubierto']]
        self.assertEqual(pendientes, [('A:0013-00034237', 84624077)])
        self.assertEqual(sum(p['remanente'] for p in pagos), 0)
        apertura = next(p for p in pagos if p['tipo'] == 'Saldo inicial')
        self.assertEqual(apertura['cubiertas'][0]['num'], 'A:0011-00005637')
        self.assertEqual(apertura['usado'], 403625132)
        self.assertEqual(sum(not f['idsys'] for f in facturas), 32)

    def test_condiseno_sin_deuda_y_credito_disponible(self):
        pagos, facturas = load_condiseno()
        fifo(pagos, facturas)
        self.assertTrue(all(f['estado'] == 'Cubierta' for f in facturas))
        self.assertEqual(sum(p['remanente'] for p in pagos), 267838617)
        self.assertEqual(sum(not f['idsys'] for f in facturas), 8)


if __name__ == '__main__':
    unittest.main()
