"""Regresiones contables: no duplicar pagos, remitos, IVA ni compras de stock."""
import unittest
from reporte_resultados import build

def account(i, name, parent=None):
    return dict(id=i, name=name, parentid=parent, grupo='cuentacontable')

def record(i, flow, status, account_id, amount='100'):
    return dict(id=i,fecha='2026-01-15',referencia='Factura',cliente='Prueba',flowid=flow,
                flujo='Flujo',cuenta_id=account_id,neto=amount,total=amount,
                estado_cab=status,estado_id=status,estado='REMITO' if status==1114 else 'Confirmado')

def line(i, rid, amount='100', name='Silla'):
    return dict(id=i,registro_id=rid,cantidad=1,neto=amount,total=amount,alicuota='0',
                articulo_id=50,articulo=name,servicio=False,cheque=False,unidad='UN',categoria='Sillas')

class AccountingTests(unittest.TestCase):
    def data(self, rs, bs=None, rels=None):
        return dict(registros=rs,lineas=bs or [],relaciones=rels or [],cuentas=[
            account(10986,'RESULTADOS AVANZIA'),account(11106,'INGRESOS',10986),
            account(10,'Ventas',11106),account(10991,'COSTO DE VENTAS',10986),
            account(11,'Costo de Ventas Mercaderías',10991),
            account(11355,'COSTOS DE FABRICACION',10986),account(12,'Materias Primas',11355),
            account(10983,'ACTIVO'),account(13,'Maquinaria',10983),
            account(14,'IVA no computable',10986)])

    def test_payment_multiple_invoices_and_duplicate_edges(self):
        d=self.data([record(1,10781,1319,10),record(2,10781,1319,10),record(3,10150,1147,11,'200')],
                    rels=[dict(a=1,b=3),dict(a=3,b=1),dict(a=2,b=3)])
        rs=build(d)['registros']
        self.assertEqual([r['estado_analisis'] for r in rs],['incluido','incluido','cubierto'])
        self.assertEqual(sum(r['importe_resultado'] for r in rs),20000)
        self.assertEqual(rs[2]['relacionados'],[1,2])

    def test_remito_draft_and_assets_not_results(self):
        rs=build(self.data([record(1,11444,1114,10),record(2,10781,1291,10),record(3,10303,1368,13)]))['registros']
        self.assertEqual([r['estado_analisis'] for r in rs],['despacho','pendiente','excluido'])
        self.assertEqual(sum(r['importe_resultado'] for r in rs),0)

    def test_cash_without_invoice_and_materials(self):
        rs=build(self.data([record(1,10150,1147,11),record(2,10303,1368,12)]))['registros']
        self.assertEqual(rs[0]['estado_analisis'],'incluido')
        self.assertEqual(rs[1]['estado_analisis'],'pendiente')

    def test_missing_own_account_not_inherited(self):
        rs=build(self.data([record(1,10303,1368,None),record(2,10150,1147,11)],rels=[dict(a=1,b=2)]))['registros']
        self.assertEqual(rs[0]['estado_analisis'],'relacionado')
        self.assertEqual(rs[0]['empresa'],'Sin empresa identificada')
        self.assertEqual(rs[0]['importe_resultado'],0)

    def test_fiscal_lines_and_iva_nonrecoverable(self):
        rs=build(self.data([record(1,10303,1368,11,'121'),record(2,10303,1368,14,'21')],
                          [line(1,1),line(2,1,'21','IVA 21%'),line(3,2,'21','IVA 21%')]))['registros']
        self.assertEqual(rs[0]['importe_resultado'],10000)
        self.assertEqual(rs[1]['importe_resultado'],2100)

    def test_negative_invoice_and_reconciliation(self):
        data=build(self.data([record(1,10781,1319,10,'-100'),record(2,10781,1319,10)],
                          [line(1,1,'-100'),line(2,2,'80')]))
        rs=data['registros']
        self.assertEqual(rs[0]['importe_resultado'],-10000)
        self.assertEqual(rs[1]['estado_analisis'],'pendiente')
        self.assertIsNone(data['lineas'][0]['cantidad_venta'])

if __name__=='__main__':
    unittest.main()
