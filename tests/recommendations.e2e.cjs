/* Run against a fresh recommendations_fixture_server.py. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = 'http://127.0.0.1:62941';

(async () => {
    const browser = await chromium.launch({headless:true, ...(process.env.EDGE_PATH ? {executablePath:process.env.EDGE_PATH} : {})});
    const page = await browser.newPage({viewport:{width:1365,height:950}});
    const errors=[];
    page.on('pageerror', error=>errors.push(error.message));
    const ready=()=>page.waitForFunction(()=>document.querySelector('#recommendation-results')?.getAttribute('aria-busy')==='false');
    const ids=()=>page.locator('.recommendation-item [data-add-movie][data-tmdb-id]').evaluateAll(forms=>[...new Set(forms.map(form=>form.dataset.tmdbId))]);
    await page.goto(base+'/recommendations'); await ready();
    const first=await ids(); assert.equal(first.length,10);
    await page.reload(); await ready(); assert.deepEqual(await ids(),first);
    await page.getByRole('button',{name:'New suggestions',exact:true}).press('Enter');
    await ready(); assert.equal((await ids()).filter(id=>first.includes(id)).length,0);
    await Promise.all([page.waitForNavigation(),page.getByLabel('In the mood for').selectOption('familiar')]); await ready();
    await page.getByRole('heading',{name:'Tonight, something good.'}).waitFor();
    const familiar=await ids(); assert.equal(familiar.length,10);
    await Promise.all([page.waitForNavigation(),page.getByLabel('In the mood for').selectOption('explore')]); await ready();
    assert.notDeepEqual(await ids(),familiar);
    const before=await ids();
    await page.locator('.recommendation-item [data-add-movie] button').first().press('Enter'); await ready();
    await page.waitForFunction(id=>!Array.from(document.querySelectorAll('.recommendation-item [data-add-movie]')).some(f=>f.dataset.tmdbId===id), before[0]);
    await ready();
    const after=await ids(); assert.deepEqual(after.slice(0,9),before.slice(1));
    assert.equal(new Set(after).size,10);

    await page.route('**/api/recommendations/refresh', route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Fixture offline'})}));
    const retained=await ids(); await page.getByRole('button',{name:'New suggestions',exact:true}).click();
    await page.getByText('Fixture offline',{exact:true}).waitFor();
    assert.deepEqual(await ids(),retained);
    await page.unroute('**/api/recommendations/refresh');

    // Change language through the normal form in this disposable library.
    await page.goto(base+'/settings');
    await page.locator('select[name="language"]').selectOption('tr');
    await page.locator('form[action="/settings/language"] button[type="submit"]').click();
    await page.goto(base+'/recommendations'); await ready();
    assert.equal(await page.locator('html').getAttribute('lang'),'tr');
    assert.deepEqual(await ids(),retained);
    await page.getByRole('button',{name:'Yeni öneriler',exact:true}).press('Enter'); await ready();
    assert.equal((await ids()).length,10);
    for (const width of [320,390,768,1365]) {
        await page.setViewportSize({width,height:950});
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1), `Overflow at ${width}px`);
    }
    const output=process.env.QA_SCREENSHOT_DIR || path.join(process.cwd(),'.qa','recommendation-screenshots');
    fs.mkdirSync(output,{recursive:true});
    await page.screenshot({path:path.join(output,'recommendations-tr-desktop.png')});
    await page.setViewportSize({width:390,height:950});
    await page.screenshot({path:path.join(output,'recommendations-tr-mobile.png')});
    assert.deepEqual(errors,[]);
    console.log('Recommendation UI passed: stable reload, new picks, modes, keyboard add/refresh, failed refresh, TR/EN identity, four responsive widths.');
    await browser.close();
})().catch(error=>{console.error(error);process.exit(1);});
