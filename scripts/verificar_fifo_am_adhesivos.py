"""Verifica transcripción, conciliación agrupada y saldos FIFO de AM ADHESIVOS."""
import unittest
from reporte_fifo_am_adhesivos import build, load_source


class AMAdhesivosTests(unittest.TestCase):
    def setUp(self):
        self.payments, self.invoices = build(load_source())
        self.by_number = {f['num'].split('-')[-1]: f for f in self.invoices}

    def test_cierre_y_pendientes_fifo(self):
        pending = {k: f['importe'] - f['cubierto'] for k, f in self.by_number.items()
                   if f['importe'] != f['cubierto']}
        self.assertEqual(pending, {'00008574': 2000, '00008625': 168054480, '00008627': 32942400})
        self.assertEqual(sum(pending.values()), 200998880)

    def test_cargo_agrupado_sin_duplicacion(self):
        group = [self.by_number[n] for n in ('00008541', '00008574')]
        self.assertEqual({f['idsys'] for f in group}, {'18772'})
        self.assertEqual(sum(f['importe'] for f in group), group[0]['local']['charges'])
        self.assertTrue(all(f['delta'] == 0 and f['group'] == 2 for f in group))

    def test_diferencias_y_faltantes(self):
        missing = [f for f in self.invoices if not f['idsys']]
        self.assertEqual(len(missing), 7)
        self.assertEqual(sum(f['importe'] for f in missing), 556493670)
        self.assertEqual(self.by_number['00008438']['delta'], -178)
        self.assertEqual(self.by_number['00008265']['idsys'], '19697')
        self.assertEqual([p['num'] for p in self.payments if not p['idsys']],
                         ['00003882', '00004079', '00004119'])
        payment = next(p for p in self.payments if p['num'] == '00004305')
        self.assertEqual(payment['local']['payments'] - payment['importe'], -178)


if __name__ == '__main__':
    unittest.main()
