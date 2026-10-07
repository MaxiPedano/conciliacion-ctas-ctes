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
        self.assertEqual([p['num'] for p in self.payments if not p['idsys']], [])
        payment = next(p for p in self.payments if p['num'] == '00004305')
        self.assertEqual(payment['local']['payments'] - payment['importe'], -178)

    def test_recibos_identificados_en_11332_sin_duplicacion(self):
        transfers = {p['num']: p['local'] for p in self.payments
                     if p.get('local') and p['local'].get('flowid') == 11332}
        self.assertEqual({n: r['id'] for n, r in transfers.items()},
                         {'00003882': '11487', '00004079': '13840', '00004119': '14748'})
        self.assertEqual(sum(r['payments'] for r in transfers.values()), 355496790)
        self.assertEqual(sum(p['importe'] for p in self.payments
                             if p['num'] in transfers), 355494790)
        forced = next(p for p in self.payments if p['num'] == '00004079')
        self.assertEqual(forced['local']['payments'] - forced['importe'], 2000)
        self.assertTrue(all(r['provider'] == '698' for r in transfers.values()))

    def test_cuenta_corriente_cierra_sin_11332(self):
        rows = load_source()['rows']
        ctacte = sum(r['charges'] - r['payments'] for r in rows if r['flowid'] in (10303, 10150))
        self.assertEqual(ctacte, 0)
        fuera = sum(r['charges'] - r['payments'] for r in rows if r['flowid'] == 11332)
        self.assertEqual(fuera, -355496790)
        canceladas = [f['num'].split('-')[-1] for f in self.invoices
                      if not f['idsys'] and f['por'] and all(p['idsys'] for p, _ in f['por'])]
        self.assertEqual(sorted(canceladas), ['00007732', '00007765', '00007904',
                                              '00008086', '00008154'])
        impagas = [f['num'].split('-')[-1] for f in self.invoices if not f['por']]
        self.assertEqual(sorted(impagas), ['00008625', '00008627'])


if __name__ == '__main__':
    unittest.main()
