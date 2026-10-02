"""Verifica el reporte generado en Edge: saldos, composición y filtros."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto((ROOT / 'reporte_analisis_proveedores.html').as_uri())
        assert page.locator('#provider option:checked').inner_text() == 'POLICOR'
        assert page.locator('header input, header select').count() == 3
        assert page.evaluate('period.length') == 94
        assert page.evaluate('DATA.rows.every(r=>(r.flowid===10303 && r.statusid===1368)||r.flowid===10150)')
        assert page.evaluate('selected.filter(r=>r.flowid===10303).length') == 67
        assert page.evaluate('selected.filter(r=>r.flowid===10150).length') == 27
        assert page.evaluate("selected.every(r=>!['19404','19406','20283'].includes(r.id))")
        # Referencia libre no sustituye al estado real: este remito está en FACTURA DE COMPRA.
        assert page.evaluate("selected.find(r=>r.id==='12536').statusid") == 1368
        assert 'FACTURA DE COMPRA' in page.locator('#ledger tr[data-id="12536"]').inner_text()
        assert page.evaluate('balance(through)') == -2144374896
        assert page.evaluate("companies.map(c=>balance(through.filter(r=>r.company===c)))") == [-370613190, -859500789, -914260917]
        assert page.evaluate("companies.map(c=>sum(through.filter(r=>r.company===c),'charges'))") == [1072693702, 185379668, 6462226539]
        assert page.evaluate("companies.map(c=>sum(through.filter(r=>r.company===c),'payments'))") == [1443306892, 1044880457, 7376487456]
        for company in ['Avanzia', 'Condiseño', 'Sin empresa']:
            for kind in ['charges', 'payments', 'balance']:
                page.locator(f'#summary button[data-company="{company}"][data-kind="{kind}"]').click()
                assert page.locator('#detail').is_visible()
                assert page.locator('#composition tbody tr').count() > 0
                assert company in page.locator('#detail-title').inner_text()
                page.keyboard.press('Escape')
        page.locator('#from').fill('2026-09-01')
        page.locator('#from').dispatch_event('change')
        page.locator('#to').fill('2026-09-28')
        page.locator('#to').dispatch_event('change')
        assert page.evaluate('balance(before)') == -2511015089
        assert page.evaluate("sum(period,'charges')") == 661520650
        assert page.evaluate("sum(period,'payments')") == 294880457
        assert page.evaluate('balance(before)+balance(period)===balance(through)')
        page.locator('#ledger button[data-kind="opening"]').click()
        assert page.locator('#composition tbody tr').count() == page.evaluate('before.length')
        page.locator('#close').click()
        page.locator('#to').fill('2026-08-01')
        page.locator('#to').dispatch_event('change')
        assert page.locator('#error').is_visible()
        assert page.locator('#report').is_hidden()
        page.locator('#from').fill('2000-01-01')
        page.locator('#from').dispatch_event('change')
        page.locator('#to').fill('2000-01-02')
        page.locator('#to').dispatch_event('change')
        assert page.evaluate('period.length===0 && balance(through)===0')
        page.locator('#from').fill('')
        page.locator('#from').dispatch_event('change')
        page.locator('#to').fill('')
        page.locator('#to').dispatch_event('change')
        other = page.evaluate("providers.find(p=>p[1]!=='POLICOR')[0]")
        page.locator('#provider').select_option(other)
        assert page.evaluate("selected.every(r=>r.provider===$('provider').value)")
        assert page.evaluate("!$('ledger').textContent.includes('POLICOR')")
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        assert not errors, errors
        browser.close()
    print('OK: saldos POLICOR, 9 desgloses, saldo anterior, fechas, cambio de proveedor y vista móvil.')


if __name__ == '__main__':
    main()
