"""Prueba real en Edge con Playwright (dependencia de verificación opcional)."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

def main():
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(accept_downloads=True)
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.goto((ROOT/'reporte_estado_resultados.html').as_uri())
        page.wait_for_function('included.length > 0')
        assert page.locator('#company-table tbody tr').count()==3
        assert page.evaluate('current.length === DATA.controles.registros')
        assert page.evaluate('included.every(r=>r.estado_id!==1114)')
        assert page.evaluate('DATA.registros.length === new Set(DATA.registros.map(r=>r.id)).size')
        expected=page.evaluate('included.reduce((s,r)=>s+r.signo*r.importe_resultado,0)')
        assert page.locator('#kpis .kpi').nth(2).locator('b').inner_text()==page.evaluate('money('+str(expected)+')')

        page.locator('#desde').fill('2026-01-01');page.locator('#desde').dispatch_event('change')
        page.locator('#hasta').fill('2026-01-31');page.locator('#hasta').dispatch_event('change')
        page.locator('#empresa').select_option(label='Avanzia')
        assert page.evaluate("current.every(r=>r.fecha>='2026-01-01' && r.fecha<='2026-01-31' && r.empresa==='Avanzia')")
        assert page.evaluate('current.length>0 && current.length<DATA.registros.length')
        month_amount=page.evaluate('included.reduce((s,r)=>s+r.signo*r.importe_resultado,0)')
        assert page.locator('#monthly tbody tr').count()==1
        assert page.locator('#monthly tbody tr td').last.inner_text()==page.evaluate('money('+str(month_amount)+')')
        # Desplegar concepto -> cuenta -> registros reales (no DOM simulado).
        page.locator('#company-detail > details > details > summary').first.click()
        page.locator('#company-detail > details > details[open] > details > summary').first.click()
        page.wait_for_selector('#company-detail tbody tr')
        assert page.locator('#company-detail tbody tr').count()>0
        assert all('2026-01-' in x for x in page.locator('#company-detail tbody tr td:nth-child(2)').all_text_contents())
        page.locator('#article-table details > summary').first.click()
        assert page.locator('#article-table details[open] tbody tr').count()>0
        with page.expect_download() as download:
            page.locator('#exportar').click()
        content=Path(download.value.path()).read_text(encoding='utf-8-sig')
        import csv,io
        rows=list(csv.DictReader(io.StringIO(content),delimiter=';'))
        assert rows and all(r['Empresa']=='Avanzia' and '2026-01-01'<=r['Fecha']<='2026-01-31' for r in rows)
        assert all(r['Tratamiento']!='relacionado' for r in rows)
        page.locator('#articulo').fill('NO EXISTE ESTE ARTICULO 98765')
        assert page.locator('#article-table details').count()==0
        page.locator('#desde').fill('2026-02-01');page.locator('#desde').dispatch_event('change')
        assert page.locator('#error').is_visible()
        assert page.evaluate('current.length===0 && included.length===0')
        page.locator('#limpiar').click()
        assert not page.locator('#error').is_visible()
        assert page.evaluate('current.length===DATA.registros.length')
        # Un día: ambos límites inclusivos.
        day=page.evaluate("included.find(r=>r.fecha).fecha")
        page.locator('#desde').fill(day);page.locator('#desde').dispatch_event('change')
        page.locator('#hasta').fill(day);page.locator('#hasta').dispatch_event('change')
        assert page.evaluate('current.length>0 && current.every(r=>r.fecha==='+repr(day)+')')
        page.locator('#limpiar').click()
        page.locator('#empresa').select_option(label='Sin empresa identificada')
        assert page.evaluate('included.length===0')
        assert 'Sin importes reconocidos' in page.locator('#company-detail').inner_text()
        page.set_viewport_size({'width':390,'height':844})
        assert page.locator('#desde').is_visible()
        assert not errors,errors
        browser.close()
        print('OK Edge: carga real, totales, fechas inclusivas, empresas, desplegables, CSV, rango inválido y móvil.')

if __name__=='__main__':
    main()
