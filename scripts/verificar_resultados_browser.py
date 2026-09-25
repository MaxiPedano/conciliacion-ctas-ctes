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
        assert page.locator('#sales-table').count()==1
        assert page.locator('#sales-table tbody tr.grp').count()>0
        assert page.locator('#sales-table tbody tr.art').count()>0
        assert page.locator('#sales-table tbody tr.total').count()==1
        # Total de la tabla plana = suma de artículos visibles, y subtotales por categoría cuadran con el total.
        assert page.evaluate("""(()=>{
          const art=[...document.querySelectorAll('#sales-table tr.art td:nth-child(3)')].map(t=>t.textContent);
          const grp=[...document.querySelectorAll('#sales-table tr.grp td:nth-child(3)')].map(t=>t.textContent);
          const tot=document.querySelector('#sales-table tr.total td:nth-child(3)').textContent;
          const n=articleRows.reduce((s,e)=>s+e.ventas,0);
          return art.length===articleRows.length && tot===money(n) && grp.length>0
            && grp.every(v=>v!=='No disponible');
        })()""")
        assert page.locator('#kpis .kpi').count()==6
        assert 'artículos' in page.locator('#article-note').inner_text()
        # Ventas por artículo: solo productos. Servicios/fletes quedan fuera y el total cierra.
        assert page.evaluate('otherSalesRows.length>0 && otherSales>0')
        assert page.evaluate("""(()=>{
          const rec=amount(included.filter(r=>r.concepto==='Ventas netas facturadas'));
          const prod=articleRows.reduce((s,e)=>s+e.ventas,0);
          return Math.abs(prod+otherSales-rec)<1;
        })()""")
        assert page.locator('#article-other details').count()==1
        assert page.evaluate("otherSalesRows.every(o=>/FLETE|SERVICIO|TRASLADO|BORDADO/i.test(o.art))")
        # Costos y gastos por artículo: tabla propia y total que cierra con lo reconocido.
        assert page.locator('#expense-sales-table').count()==1
        assert page.locator('#expense-sales-table tr.grp').count()>0
        assert page.locator('#expense-sales-table tr.total').count()==1
        assert page.evaluate("""(()=>{
          const rec=amount(included.filter(r=>!isIncome(r)));
          const tot=document.querySelector('#expense-sales-table tr.total td:nth-child(3)').textContent;
          return rec>0 && tot===money(rec);
        })()""")
        assert page.evaluate('expenseRows.length>0 && expenseRows.every(e=>e.importe!==0)')
        assert page.locator('#company-table tbody tr').count()==3
        # Desplegar los renglones de una fila de artículo y plegarlos de nuevo.
        page.locator('#sales-table tr.art button.ghost').first.click()
        assert page.locator('#sales-table tr.detalle').count()==1
        assert page.locator('#sales-table tr.detalle tbody tr').count()>0
        assert page.locator('#sales-table tr.art button.ghost').first.inner_text()=='Ocultar renglones'
        page.locator('#sales-table tr.art button.ghost').first.click()
        assert page.locator('#sales-table tr.detalle').count()==0
        # Agrupación por mes: los encabezados pasan a ser meses y el total se conserva.
        total_all=page.evaluate('money(articleRows.reduce((s,e)=>s+e.ventas,0))')
        page.locator('#agrupar').select_option('mes')
        assert page.locator('#sales-table tr.grp').count()>0
        assert page.evaluate("""[...document.querySelectorAll('#sales-table tr.grp td:first-child')].every(t=>t.textContent.startsWith('MES: '))""")
        assert page.locator('#sales-table tr.total td:nth-child(3)').inner_text()==total_all
        page.locator('#agrupar').select_option('cat')
        assert page.locator('#sales-table tr.total td:nth-child(3)').inner_text()==total_all

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
        # Con filtro de fechas/empresa la tabla de gastos también se recalcula y cierra.
        assert page.evaluate("""(()=>{
          const rec=amount(included.filter(r=>!isIncome(r)));
          const tot=document.querySelector('#expense-sales-table tr.total td:nth-child(3)').textContent;
          return tot===money(rec);
        })()""")
        # Desplegar concepto -> cuenta -> registros reales (no DOM simulado).
        page.locator('#company-detail > details > details > summary').first.click()
        page.locator('#company-detail > details > details[open] > details > summary').first.click()
        page.wait_for_selector('#company-detail tbody tr')
        assert page.locator('#company-detail tbody tr').count()>0
        assert all('2026-01-' in x for x in page.locator('#company-detail tbody tr td:nth-child(2)').all_text_contents())
        with page.expect_download() as download:
            page.locator('#exportar').click()
        content=Path(download.value.path()).read_text(encoding='utf-8-sig')
        import csv,io
        rows=list(csv.DictReader(io.StringIO(content),delimiter=';'))
        assert rows and all(r['Empresa']=='Avanzia' and '2026-01-01'<=r['Fecha']<='2026-01-31' for r in rows)
        assert all(r['Tratamiento']!='relacionado' for r in rows)
        # La tabla de artículos respeta fechas y empresa: los renglones abiertos son del mes filtrado.
        assert page.evaluate("included.filter(r=>r.concepto==='Ventas netas facturadas').every(r=>r.fecha>='2026-01-01'&&r.fecha<='2026-01-31'&&r.empresa==='Avanzia')")
        with page.expect_download() as download:
            page.locator('#exportar-articulos').click()
        art=list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig')),delimiter=';'))
        assert art and all(r['Empresa']=='Avanzia' for r in art)
        assert abs(sum(float(r['Ventas netas sin IVA']) for r in art)-page.evaluate('articleRows.reduce((s,e)=>s+e.ventas,0)/100'))<0.01
        with page.expect_download() as download:
            page.locator('#exportar-gastos').click()
        gas=list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig')),delimiter=';'))
        assert gas and all(r['Empresa']=='Avanzia' for r in gas)
        assert abs(sum(float(r['Importe sin IVA']) for r in gas)-page.evaluate('expenseRows.reduce((s,e)=>s+e.importe,0)/100'))<0.01
        page.locator('#articulo').fill('NO EXISTE ESTE ARTICULO 98765')
        assert page.locator('#sales-table').count()==0
        assert 'Sin artículos' in page.locator('#article-table').inner_text()
        page.locator('#articulo').fill('')
        assert page.locator('#sales-table').count()==1
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
        assert page.locator('#sales-table').count()==0
        assert 'Sin artículos' in page.locator('#article-table').inner_text()
        assert page.locator('#expense-sales-table').count()==0
        assert 'Sin costos ni gastos' in page.locator('#expense-table').inner_text()
        page.set_viewport_size({'width':390,'height':844})
        assert page.locator('#desde').is_visible()
        assert not errors,errors
        browser.close()
        print('OK Edge: carga real, totales, fechas inclusivas, empresas, desplegables, CSV, rango inválido y móvil.')

if __name__=='__main__':
    main()
