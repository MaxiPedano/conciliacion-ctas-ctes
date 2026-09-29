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
        page.wait_for_function('currentLines.length > 0')
        assert page.locator('#sales-table').count()==1
        assert page.locator('#sales-table tbody tr.grp').count()>0
        assert page.locator('#sales-table tbody tr.art').count()>0
        assert page.locator('#sales-table tbody tr.total').count()==1
        # Total de la tabla plana = suma de los renglones visibles.
        assert page.evaluate("""(()=>{
          const art=[...document.querySelectorAll('#sales-table tr.art td:nth-child(3)')].map(t=>t.textContent);
          const n=articleRows.reduce((s,e)=>s+e.ventas,0);
          const tot=document.querySelector('#sales-table tr.total td:nth-child(3)').textContent;
          return art.length===articleRows.length && tot===money(n);
        })()""")
        assert page.locator('#kpis .kpi').count()==6
        # KPI cierra con los renglones de producto terminado del filtro activo.
        assert page.evaluate("""(()=>{
          const neto=currentLines.reduce((s,b)=>s+b.neto,0);
          const un=currentLines.reduce((s,b)=>s+(b.cantidad_venta||0),0);
          const k=document.querySelectorAll('#kpis .kpi b');
          return k[0].textContent===money(neto) && k[2].textContent===String(new Set(currentLines.map(b=>b.articulo_id)).size);
        })()""")
        # Alcance: solo estados de venta y producto terminado bajo las dos raíces.
        assert page.evaluate('currentRecords.every(r=>r.flowid===10781||r.flowid===11547)')
        assert page.evaluate('currentRecords.every(r=>r.estado_id===1319||r.estado_id===1291)')
        assert page.evaluate('DATA.registros.some(r=>r.estado_id===1291)')
        assert page.evaluate("DATA.lineas.every(b=>b.raiz_id===10626||b.raiz_id===11428)")
        # Empresa por depósito del producto.
        assert page.evaluate("DATA.lineas.filter(b=>b.empresa==='Avanzia').every(b=>b.raiz_id===10626)")
        assert page.evaluate("DATA.lineas.filter(b=>b.empresa==='Condiseño').every(b=>b.raiz_id===11428)")
        # Resumen por empresa: 3 empresas + total.
        assert page.locator('#company-table tbody tr').count()==4
        # Orden compacto: primero la evolución, después la tabla de ventas.
        assert page.evaluate("!!(document.querySelector('#timeline').compareDocumentPosition(document.querySelector('#ventas'))&Node.DOCUMENT_POSITION_FOLLOWING)")
        # Promedios de ventas totales y columnas de promedio por artículo.
        assert page.locator('#promedios .chip').count()>=4
        assert page.evaluate("""(()=>{
          const h=document.querySelector('#sales-table thead').textContent;
          return h.includes('Ticket prom.') && h.includes('Prom. mensual') &&
                 [...document.querySelectorAll('#sales-table tr.art')].every(tr=>tr.children.length===5);
        })()""")
        # Línea de tiempo: solo gráficos SVG, sin el listado mes / artículo debajo.
        assert page.locator('.chart svg').count()==3
        assert page.locator('#timeline-table').count()==0
        assert page.locator('#timeline-table-flat').count()==0
        assert page.evaluate("""(()=>{
          const rows=timelineVisible;
          const suma=rows.reduce((s,r)=>s+r.neto,0);
          const meses=timelineMonths.reduce((s,m)=>s+m.neto,0);
          return rows.length>0 && Math.abs(suma-meses)<1;
        })()""")
        # El total de la tabla de ventas cierra con la suma de los meses del gráfico.
        assert page.evaluate("""(()=>{const a=document.querySelector('#sales-table tr.total td:nth-child(3)');
          return a.textContent===money(timelineMonths.reduce((s,m)=>s+m.neto,0));})()""")
        # Contraer hasta los encabezados de empresa y categoría, y volver a abrir.
        page.locator('#contraer').click()
        assert page.evaluate("document.querySelectorAll('#sales-table tr.art').length===0")
        assert page.evaluate("document.querySelectorAll('#sales-table tr.empresa').length>0 && document.querySelectorAll('#sales-table tr.grp').length>0")
        assert page.evaluate("document.querySelectorAll('#sales-table tr.total').length===1")
        page.locator('#contraer').click()
        assert page.evaluate("document.querySelectorAll('#sales-table tr.art').length>0")
        # Control de integridad: comprobantes de venta fuera de alcance, con motivo.
        assert page.locator('#controls tbody tr').count()>5
        assert page.locator('#audit details').count()>0
        assert page.evaluate('currentExcluded.every(r=>r.motivo && r.motivo.length>10)')
        # Desplegar los renglones de una fila de artículo y plegarlos de nuevo.
        page.locator('#sales-table tr.art button.ghost').first.click()
        assert page.locator('#sales-table tr.detalle').count()==1
        assert page.locator('#sales-table tr.detalle tbody tr').count()>0
        assert page.locator('#sales-table tr.art button.ghost').first.inner_text()=='Ocultar renglones'
        page.locator('#sales-table tr.art button.ghost').first.click()
        assert page.locator('#sales-table tr.detalle').count()==0
        # Agrupación por mes: encabezados de mes y total conservado.
        total_all=page.evaluate('money(articleRows.reduce((s,e)=>s+e.ventas,0))')
        page.locator('#agrupar').select_option('mes')
        assert page.evaluate("[...document.querySelectorAll('#sales-table tr.grp td:first-child')].every(t=>t.textContent.startsWith('MES: '))")
        assert page.locator('#sales-table tr.total td:nth-child(3)').inner_text()==total_all
        page.locator('#agrupar').select_option('cat')
        assert page.locator('#sales-table tr.total td:nth-child(3)').inner_text()==total_all
        # Métrica y top del gráfico por artículo.
        page.locator('#metrica').select_option('cantidad')
        assert page.locator('#chart-articulos polyline').count()>0
        page.locator('#topn').select_option('6')
        assert page.locator('#chart-articulos polyline').count()<=6
        # Filtro de fechas y empresa.
        page.locator('#desde').fill('2026-01-01');page.locator('#desde').dispatch_event('change')
        page.locator('#hasta').fill('2026-01-31');page.locator('#hasta').dispatch_event('change')
        page.locator('#empresa').select_option(label='Avanzia')
        assert page.evaluate("currentLines.every(b=>b.empresa==='Avanzia')")
        assert page.evaluate("""currentLines.every(b=>{const r=records.get(b.registro_id);return r.fecha>='2026-01-01'&&r.fecha<='2026-01-31'})""")
        assert page.evaluate('currentLines.length>0 && currentLines.length<DATA.lineas.length')
        assert page.evaluate('timelineMonths.every(m=>m.mes.startsWith("2026-01"))')
        # CSV filtrados.
        with page.expect_download() as download:
            page.locator('#exportar').click()
        import csv,io
        rows=list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig')),delimiter=';'))
        assert rows and all('2026-01-01'<=r['Fecha']<='2026-01-31' for r in rows)
        with page.expect_download() as download:
            page.locator('#exportar-articulos').click()
        art=list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig')),delimiter=';'))
        assert art and all(r['Empresa']=='Avanzia' for r in art)
        assert abs(sum(float(r['Ventas netas sin IVA']) for r in art)-page.evaluate('articleRows.reduce((s,e)=>s+e.ventas,0)/100'))<0.01
        with page.expect_download() as download:
            page.locator('#exportar-timeline').click()
        lineas=list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig')),delimiter=';'))
        assert lineas and all(r['Mes'].startswith('2026-01') for r in lineas)
        assert abs(sum(float(r['Importe sin IVA']) for r in lineas)-page.evaluate('timelineMonths.reduce((s,m)=>s+m.neto,0)/100'))<0.01
        # Búsqueda de producto: filtra ventas y línea de tiempo a la vez.
        page.locator('#articulo').fill('NO EXISTE ESTE ARTICULO 98765')
        assert page.locator('#sales-table').count()==0
        assert 'Sin productos' in page.locator('#article-table').inner_text()
        page.locator('#articulo').fill('')
        assert page.locator('#sales-table').count()==1
        # Rango inválido y limpieza.
        page.locator('#desde').fill('2026-02-01');page.locator('#desde').dispatch_event('change')
        assert page.locator('#error').is_visible()
        assert page.evaluate('currentLines.length===0')
        page.locator('#limpiar').click()
        assert not page.locator('#error').is_visible()
        assert page.evaluate('currentLines.length===DATA.lineas.length')
        # Un día: ambos límites inclusivos.
        day=page.evaluate('records.get(currentRecords[0].id).fecha')
        page.locator('#desde').fill(day);page.locator('#desde').dispatch_event('change')
        page.locator('#hasta').fill(day);page.locator('#hasta').dispatch_event('change')
        assert page.evaluate('currentLines.length>0 && currentLines.every(b=>records.get(b.registro_id).fecha==='+repr(day)+')')
        page.locator('#limpiar').click()
        page.set_viewport_size({'width':390,'height':844})
        assert page.locator('#desde').is_visible()
        assert not errors,errors
        browser.close()
        print('OK Edge: alcance de producto, empresa por deposito, totales, timeline, filtros, CSV, rango invalido y movil.')

if __name__=='__main__':
    main()
