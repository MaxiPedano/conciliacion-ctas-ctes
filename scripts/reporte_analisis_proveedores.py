#!/usr/bin/env python3
"""Genera análisis por proveedor consultando PostgreSQL exclusivamente en lectura.

Uso: python scripts/reporte_analisis_proveedores.py
Importes en centavos enteros; empresa exclusivamente por referencia explícita.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import unicodedata

from reporte_articulos import live_connection, query

ROOT = Path(__file__).resolve().parents[1]

# IDs verificados en la base. La referencia libre no determina el estado.
INVOICE_STATUS = 1368  # 12.0.06 FACTURA DE COMPRA
INVOICE_FLOW = 10303  # Comprobantes Proveedores
CASH_OUTFLOW = 10150  # CAJA: Egresos
QUERY = """
SELECT rc.id, rc.clientid, rc.clientname, rc.fecha::text AS fecha,
       COALESCE(rc.referenciatexto, '') AS referencia,
       COALESCE(rc.totalimpuestos, 0) AS importe,
       rc.flowid, f.name AS flujo, sf.id AS statusflowid,
       s.id AS statusid, s.descrip AS estado
FROM test9000.registrocab rc
JOIN test9000.statusflows sf ON sf.id = rc.statusflowid AND sf.categid = rc.flowid
JOIN test9000.statuses s ON s.id = sf.statusid
JOIN test9000.categorias f ON f.id = rc.flowid
WHERE ((rc.flowid = 10303 AND s.id = 1368) OR rc.flowid = 10150{extra_flows})
  AND rc.fecha IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM test9000.categoriasperfiles cp
      JOIN test9000.categorias c ON c.id = cp.categoriaid
      WHERE cp.perfilid = rc.clientid AND (c.id = 1081 OR c.parentid = 1081)
  )
ORDER BY rc.fecha, rc.id
"""


def company(reference):
    value = unicodedata.normalize('NFKD', reference).encode('ascii', 'ignore').decode().upper()
    compact = re.sub(r'[^A-Z0-9]', '', value)
    avanzia = 'AVANZIA' in compact
    condiseno = 'CONDISENO' in compact or 'GCONDIS' in compact
    if avanzia == condiseno:
        return 'Sin empresa'
    return 'Avanzia' if avanzia else 'Condiseño'


def fetch_data(extra_flows=()):
    flows = {int(f) for f in extra_flows}
    sql = QUERY.format(extra_flows=''.join(f' OR rc.flowid = {f}' for f in sorted(flows)))
    with live_connection() as conn:
        records = query(conn, sql)
        generated = query(conn, "SELECT to_char(CURRENT_TIMESTAMP, 'DD/MM/YYYY HH24:MI TZ') AS fecha")[0]['fecha']
    rows = []
    for r in records:
        invoice = r['flowid'] == INVOICE_FLOW and r['statusid'] == INVOICE_STATUS
        if not invoice and r['flowid'] not in {CASH_OUTFLOW} | flows:
            raise ValueError(f"Movimiento fuera del alcance: {r['id']}")
        amount = int((Decimal(r['importe']) * 100).quantize(Decimal('1')))
        rows.append(dict(
            id=str(r['id']), provider=str(r['clientid']), name=r['clientname'] or str(r['clientid']),
            date=r['fecha'], reference=r['referencia'], company=company(r['referencia']),
            flow=r['flujo'], flowid=r['flowid'], status=r['estado'],
            statusid=r['statusid'], statusflowid=r['statusflowid'],
            charges=amount if invoice else 0, payments=0 if invoice else amount,
        ))
    return dict(rows=rows, generated=generated, source='PostgreSQL · consulta directa de solo lectura')


def generate(destination):
    payload = fetch_data()
    rows = payload['rows']
    if not rows:
        raise ValueError('La fuente no contiene movimientos de proveedores.')
    keys = [(r['provider'], r['id']) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('La fuente contiene comprobantes duplicados.')
    data = json.dumps(payload, ensure_ascii=False)
    data = data.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (ROOT / 'assets' / 'analisis_proveedores.html').read_text(encoding='utf-8')
    destination.write_text(template.replace('__DATA__', data), encoding='utf-8')
    print(f'Generado: {destination.name} ({len(rows)} movimientos)')
    policor = [r for r in rows if r['provider'] == '986']
    print(f"POLICOR: {len(policor)} movimientos; "
          f"{sum(r['flowid'] == INVOICE_FLOW for r in policor)} FACTURA DE COMPRA; "
          f"{sum(r['flowid'] == CASH_OUTFLOW for r in policor)} CAJA: Egresos")
    for c in ('Avanzia', 'Condiseño', 'Sin empresa'):
        group = [r for r in policor if r['company'] == c]
        print(c, 'cargos:', sum(r['charges'] for r in group) / 100,
              'pagos:', sum(r['payments'] for r in group) / 100,
              'saldo:', sum(r['charges'] - r['payments'] for r in group) / 100)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, default=ROOT / 'reporte_analisis_proveedores.html')
    args = cli.parse_args()
    generate(args.output)
