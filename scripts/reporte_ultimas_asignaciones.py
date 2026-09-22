"""Reporte del bloque de 21 lotes informado por el usuario; no ejecuta SQL."""
from pathlib import Path
from html.parser import HTMLParser
import html
from datetime import datetime
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOTES = [
 (11060, '8842 9289 17670 18410 19226 20292'),
 (11240, '8809 9923 16844 18089 18304 18518'),
 (11240, '9397 10130 10131 10135 10194 10380 10805 11100 11483 11485 11489 11756 12625 12637 12757 12758 12759 12884 13469 13939 14892 15405 15558 15587 15835 16851 16852 16987 17002 17576 17577 17583 17715 17929 18510 18512 18732 18841 18874 19124 19750'),
 (11240, '8817 8822 9032 9112 16652 17359 17361 18133 19094 19216'),
 (11240, '9416 9612 9613 11774 11826 12144 12642 13090 13236 13237 13395 13398 13762 14314 14694 15158 17006 17008 17010 17019 17020 17167 17169 17282 17828 17830 17928 18726'),
 (11240, '9034 9102 9344 10040 11097 11317 11844 12067 12525 12527 12896 13226 13464 13492 13521 14439 14506 16571 16572 16573 17142 17143 17918 18441 18509 18640 18725 20394'),
 (11240, '8823 8828 9035 9037 9128 9614 9878 10065 10464 10523 10690 10700 11054 11198 11314 11315 11440 11488 11555 11606 11734 12145 12512 13077 13396 13639 13839 13973 13978 13992 14356 14677 14695 15539 15946 15955 17023 17098 17385 17459 17493 17817 18361 18868 19154 19155 19193 19358 19853 19854 20191'),
 (11240, '9041 9110 9350 9412 9458 9954 10041 10042 10043 10171 10172 13688 14044 14303 15082 15114 17530 18303 18517 18734 19126 19406 19407 20428 20429'),
 (11354, '8948 9072 9330 9337 9355 9374 9393 9404 9419 9427 9440 9463 9471 9488 9862 9869 9909 10116 10468 12643'),
 (11354, '8942 9070 9326 9334 9354 9375 9391 9403 9417 9426 9437 9462 9470 9485 9498 9861 9868 10117 10467'),
 (11354, '8944 9071 9325 9335 9353 9376 9392 9405 9418 9425 9430 9436 9461 9469 9486 9864 9870 9888 10118 10469'),
 (11076, '8946 9069 9331 9338 9357 9373 9394 9402 9410 9439 9464 9489 9865 9871 10119 18145'),
 (11076, '8940 9068 9324 9336 9356 9372 9390 9401 9438 9465 9490 9866 9873 9898 9915 10120'),
 (10999, '9542 9543 9593 9594'), (10999, '9540'), (10999, '9539'),
 (11052, '9428 9446 9595 9694 10006 10133 10295'),
 (11020, '8787 8870 8967 8972 9060 9157 9218 9297 9304 9351 9386 9389 9431 9433 9443 9480 9482 9608 9701 9742 9746 9748 9750 9752 9836 9929 9933 9943 9945 10025 10029 10070 10156 10158 10198 10238 10341 10389 10392 10395 10409 10411 10416 10447 10454 10456 16268 16270 16271 16606 16933 17049 17140 17290 17293 17450 17455 18059 18157 18206 18208 18331 18396 18417 18652 18660 18995 19031 19077 19079 19103 19183 19263 19486 19488 19526 19604 19768 19894 20022 20113'),
 (11446, '17501 17838'),
 (11505, '18520 18565 18711 18853 19522 19612 19802 19814 19871 20115'),
 (11449, '18552 18800 18933 18936 18997 19185 19259 19401 19600 19602 19649 19747 19801 19951 20066 20276 20278 20407 20409'),
]


class DetailParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = {}
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr' and dict(attrs).get('class') == 'detail-row':
            self.row = []
        if tag == 'td' and self.row is not None:
            self.cell = ''

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.rows[int(self.row[0])] = self.row
            self.row = None


def main():
    source = ROOT / 'reporte_cuentas_contables.html'
    parser = DetailParser()
    parser.feed(source.read_text(encoding='utf-8'))
    records = []
    for lote, (account, ids) in enumerate(LOTES, 1):
        for record_id in map(int, ids.split()):
            row = parser.rows.get(record_id)
            records.append({
                'Lote': lote, 'Registro ID': record_id,
                'Fecha comprobante': row[1] if row else '',
                'Proveedor / perfil': row[2] if row else '',
                'Referencia texto': row[3] if row else '',
                'Flujo': row[4] if row else '',
                'Cuenta esperada ID': account,
                'Cuenta asignada ID': row[5] if row else '',
                'Cuenta contable asignada': row[6] if row else '',
                'Importe totalprecio': float(row[8].replace('$', '').replace(',', '')) if row else None,
                'Verificacion': ('Coincide' if row[5] == str(account) else 'Difiere') if row else 'No figura en reporte fuente',
            })
    df = pd.DataFrame(records)
    assert df['Registro ID'].is_unique
    summary = df.groupby(['Cuenta esperada ID', 'Cuenta contable asignada', 'Verificacion'], dropna=False).agg(
        Registros=('Registro ID', 'count'), Importe=('Importe totalprecio', 'sum')).reset_index()
    note = ('Ultimo bloque informado: 21 lotes. Estado verificado contra el reporte contable actualizado el '
            + datetime.fromtimestamp(source.stat().st_mtime).strftime('%d/%m/%Y %H:%M')
            + '. No es un historial de auditoria: no determina la hora ni el valor anterior de la asignacion. '
            + 'La fecha corresponde al comprobante. Importes: totalprecio, no impuestos.')
    xlsx = ROOT / 'reporte_ultimas_asignaciones.xlsx'
    with pd.ExcelWriter(xlsx, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Detalle', index=False)
        summary.to_excel(writer, sheet_name='Resumen', index=False)
        pd.DataFrame({'Fuente y alcance': [note]}).to_excel(writer, sheet_name='Alcance', index=False)
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = 'A2'
            sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                sheet.column_dimensions[column[0].column_letter].width = min(70, max(16, max(len(str(c.value or '')) for c in column) + 2))
            for cells in sheet.iter_rows():
                for cell in cells:
                    if cell.data_type == 'f':
                        cell.data_type = 's'
    page = '''<!doctype html><html lang="es"><meta charset="utf-8"><title>Ultimas asignaciones contables</title>
    <style>body{font:15px Segoe UI;margin:28px;color:#17324d}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px;border:1px solid #ddd;text-align:left}th{background:#e7f1f4;position:sticky;top:0}tr:nth-child(even){background:#f7fafb}input{padding:12px;width:65%;margin:18px 0}.wrap{overflow:auto;max-height:75vh}</style>
    <h1>Ultimas asignaciones de cuentas contables</h1>'''
    page += '<p>' + html.escape(note) + '</p><p><b>' + str(len(df)) + ' registros</b></p>'
    page += '<p><a href="reporte_ultimas_asignaciones.xlsx">Descargar Excel con detalle y resumen</a></p>'
    page += '<h2>Resumen por cuenta</h2>' + summary.to_html(index=False, border=0)
    page += '<h2>Detalle por registro</h2><input id="buscar" placeholder="Buscar referencia, proveedor, registro o cuenta"><div class="wrap">'
    page += df.to_html(index=False, border=0, table_id='detalle') + '</div>'
    page += '''<script>document.getElementById('buscar').addEventListener('input',function(){const q=this.value.toLocaleLowerCase();document.querySelectorAll('#detalle tbody tr').forEach(r=>r.hidden=!r.textContent.toLocaleLowerCase().includes(q));});</script></html>'''
    (ROOT / 'reporte_ultimas_asignaciones.html').write_text(page, encoding='utf-8')
    print(df['Verificacion'].value_counts().to_string())
    print(summary.to_string(index=False))
    print('Archivos:', xlsx, 'y reporte_ultimas_asignaciones.html')


if __name__ == '__main__':
    main()
