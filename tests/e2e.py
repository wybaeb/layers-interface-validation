import os

from playwright.sync_api import sync_playwright

BASE=os.environ.get('LAYERS_TEST_BASE_URL','http://127.0.0.1:8877').rstrip('/')
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    for width in (390,1440):
        page=browser.new_page(viewport={"width":width,"height":900})
        page.on('console', lambda msg: errors.append(f'console:{msg.type}:{msg.text}') if msg.type=='error' else None)
        page.on('pageerror', lambda exc: errors.append(f'page:{exc}'))
        response=page.goto(BASE+'/', wait_until='networkidle')
        assert response and response.status==200
        assert page.locator('h1').inner_text()=='Проверка структуры и интерфейса'
        assert page.locator('section').count()==10
        assert page.locator('text=Если research_flow.py не найден').count()==1
        assert page.locator('a[href="dist/install_interface_validation.py"]').count()==1
        page.locator('#study-path').fill('studies/example')
        assert 'studies/example/research/tree_test.html' in page.locator('#tree-test-path').inner_text()
        overflow=page.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth')
        assert not overflow, (width, page.evaluate('document.documentElement.scrollWidth'), page.evaluate('document.documentElement.clientWidth'))
        page.close()
    page=browser.new_page(viewport={"width":390,"height":844}, accept_downloads=True)
    page.goto(BASE+'/demo/tree_test.html', wait_until='networkidle')
    page.locator('#participant').fill('R9')
    page.locator('#begin').click()
    page.get_by_role('button', name='Рабочий день').click()
    page.get_by_role('button', name='Расписание').click()
    page.locator('#choose').click()
    page.get_by_role('button', name='Команда').click()
    page.get_by_role('button', name='Приглашения').click()
    page.locator('#choose').click()
    assert page.locator('#done').is_visible()
    with page.expect_download() as download_info:
        page.locator('#download').click()
    assert download_info.value.suggested_filename=='tree-result-R9.json'
    assert not page.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth')
    page.goto(BASE+'/demo/gallery.html', wait_until='networkidle')
    assert page.locator('img').count()==2
    assert page.locator('img').first.get_attribute('src').startswith('data:image/svg+xml;base64,')
    assert not page.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth')
    browser.close()
assert not errors, errors
print('BROWSER PASS: launcher desktop/mobile, dynamic path, tree runner, download, autonomous gallery')
