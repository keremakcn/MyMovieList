/* Run against tests/frontend_fixture_server.py with Playwright installed. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:5057';

(async () => {
    const browser = await chromium.launch({headless: true, ...(process.env.EDGE_PATH ? {executablePath: process.env.EDGE_PATH} : {})});
    const page = await browser.newPage({viewport: {width: 1440, height: 1040}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    fs.mkdirSync('.qa/frontend-screens', {recursive: true});
    const ready = async () => {
        if (await page.locator('#refresh-recommendations').count()) await page.waitForFunction(() => !document.querySelector('#refresh-recommendations').disabled);
        if (await page.locator('#taste-grid').count()) await page.waitForFunction(() => document.querySelector('#taste-grid').getAttribute('aria-busy') === 'false');
        await page.locator('img').evaluateAll(images => Promise.all(images.map(image => { image.loading = 'eager'; return image.decode().catch(() => {}); })));
    };
    for (const [name, url] of [['library','/'],['explore','/search'],['results','/search?q=film'],['recommendations','/recommendations'],['taste','/taste'],['detail','/movie/1'],['edit','/edit/1'],['settings','/settings'],['actor','/explore/person/6384'],['company','/explore/company/174']]) {
        const response = await page.goto(base + url); assert.equal(response.status(),200,url);
        await ready(); await page.screenshot({path:`.qa/frontend-screens/${name}.png`,fullPage:true});
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Desktop overflow: ${name}`);
    }
    for (const width of [320,390,768,1024]) {
        await page.setViewportSize({width,height:900});
        for (const url of ['/','/search','/search?q=film','/recommendations','/taste','/movie/1','/edit/1']) {
            await page.goto(base+url); await ready();
            assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1), `Overflow ${width}: ${url}`);
        }
        await page.goto(base+'/');
        await page.screenshot({path:`.qa/frontend-screens/library-${width}.png`,fullPage:true});
    }
    await page.setViewportSize({width:1440,height:1040});
    await page.goto(base+'/');
    const heights=await page.locator('.movie-card').evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().height));
    assert(Math.max(...heights)-Math.min(...heights)<2,'Closed cards must align');
    const first = page.locator('.movie-card[data-movie-id="1"]');
    await first.getByRole('button',{name:'Remove The Green Mile',exact:true}).focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(()=>!document.querySelector('[data-movie-id="1"]'));
    await page.waitForFunction(()=>document.activeElement?.matches('.movie-card h2 a, #library-results .section-heading h2'));
    await page.getByRole('button',{name:'Undo',exact:true}).click();
    await page.locator('.movie-card[data-movie-id="1"]').waitFor();
    await page.goto(base+'/edit/1');
    await page.getByRole('button',{name:'Remove The Green Mile',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('form.movie-form').closest('[data-detail-id]').hidden);
    await page.getByRole('button',{name:'Undo',exact:true}).click();
    await page.locator('form.movie-form').waitFor({state:'visible'});
    await page.goto(base+'/taste'); await ready();
    await page.locator('.taste-card input').first().check();
    await page.locator('#taste-selected button').first().focus(); await page.keyboard.press('Enter');
    assert.equal(await page.locator('#taste-selected button').count(),0);
    assert.equal(await page.evaluate(()=>document.activeElement.id),'taste-query');
    await page.goto(base+'/search');
    await page.locator('#discover-input').fill('film');
    await page.locator('#suggestions li[role=option]').first().waitFor();
    await page.keyboard.press('ArrowDown');
    assert(await page.locator('#discover-input').getAttribute('aria-activedescendant'));
    await page.keyboard.press('Escape'); assert(await page.locator('#suggestions').isHidden());
    assert.deepEqual(errors,[]);
    console.log('10 desktop pages, 4 responsive widths, aligned cards, remove/Undo, edit removal, survey focus and search keyboard checks passed.');
    await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
