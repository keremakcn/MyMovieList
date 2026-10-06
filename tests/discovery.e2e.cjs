/* Run with an isolated discovery_fixture_server.py, DISCOVERY_SCENARIO=errors. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:5063';

(async () => {
    const browser = await chromium.launch({headless:true, ...(process.env.EDGE_PATH ? {executablePath:process.env.EDGE_PATH} : {})});
    const page = await browser.newPage({viewport:{width:1365,height:950}});
    const errors=[];
    page.on('pageerror', error=>errors.push(error.message));
    const ready = key=>page.waitForFunction(key=>document.querySelector(`#discovery-${key} [data-discovery-feed]`)?.getAttribute('aria-busy')==='false',key);
    const cards = id=>page.locator(`[data-discovery-movie="${id}"]`);
    await page.goto(base+'/search');
    await ready('trending');
    assert.equal(await page.locator('#rail-trending .discovery-card').count(),12);
    await page.locator('#discovery-top-rated').scrollIntoViewIfNeeded();
    await ready('top-rated');
    assert(await page.locator('#discovery-top-rated').getByRole('button',{name:'Try again'}).isVisible());
    assert.equal(await page.locator('#rail-trending .discovery-card').count(),12,'A failed shelf must not replace another shelf');
    await page.locator('#discovery-top-rated').getByRole('button',{name:'Try again'}).click();
    await page.locator('#rail-top-rated').waitFor();
    await ready('top-rated');
    assert(await page.locator('#rail-top-rated').evaluate(rail=>rail===document.activeElement),'Retry must retain keyboard focus');
    await page.locator('#discovery-new-releases').scrollIntoViewIfNeeded();
    await ready('new-releases');

    const heights=await page.locator('#rail-trending .discovery-card').evaluateAll(cards=>cards.map(card=>card.getBoundingClientRect().height));
    assert(Math.max(...heights)-Math.min(...heights)<2,'Long title must retain equal card height');
    const watched=page.locator('#discovery-trending [data-discovery-movie="603"] .in-library');
    assert.match(await watched.getAttribute('aria-label'),/Watched/,'Screen readers must receive library status');

    await page.locator('#discovery-trending').getByRole('button',{name:'Today',exact:true}).click();
    await page.locator('#discovery-trending').getByRole('button',{name:'This week',exact:true}).click();
    await ready('trending');
    assert.equal(await page.locator('#rail-trending h3').first().innerText(),'Fixture film 1','Newest period must win');
    assert.match(await page.locator('#discovery-trending .discovery-view-all').getAttribute('href'),/window=week/);

    await page.locator('#discovery-trending [data-discovery-movie="607"] button').press('Enter');
    await page.getByText('Discovery is temporarily unavailable. Please try again.',{exact:true}).waitFor();
    const retryAdd=page.locator('#discovery-trending [data-discovery-movie="607"] button');
    await page.waitForFunction(()=>!document.querySelector('#discovery-trending [data-discovery-movie="607"] button').disabled);
    await retryAdd.press('Enter');
    await page.locator('#discovery-trending [data-discovery-movie="607"] .in-library').waitFor();
    assert.equal(await cards(607).locator('.in-library').count(),3,'All copies must reflect one addition');

    let addCalls=0;
    await page.route('**/add_from_catalog',async route=>{addCalls++;await route.continue();});
    // Both forms submit synchronously while the first request is pending.
    await page.locator('[data-discovery-movie="608"] form').evaluateAll(forms=>forms.forEach(form=>form.requestSubmit()));
    await page.locator('#discovery-trending [data-discovery-movie="608"] .in-library').waitFor();
    assert.equal(addCalls,1,'Cross-shelf double-add must issue one request');
    assert.equal(await cards(608).locator('.in-library').count(),3);
    await page.unroute('**/add_from_catalog');

    await page.goto(base+'/discover/trending?window=day&hide_library=1');
    assert.equal(await page.locator('.discovery-grid .in-library').count(),0);
    const before=await page.locator('.discovery-grid .discovery-card').count();
    await page.locator('[data-discovery-movie="609"] button').press('Enter');
    await cards(609).waitFor({state:'detached'});
    assert.equal(await page.locator('.discovery-grid .discovery-card').count(),before-1);
    assert(await page.evaluate(()=>document.activeElement.matches('.discovery-card h3 a')),'Removing a hidden library card must retain focus');
    await page.getByRole('link',{name:'Next →'}).click();
    assert.match(page.url(),/window=day/); assert.match(page.url(),/hide_library=1/);assert.match(page.url(),/page=2/);
    const titleLink=page.locator('.discovery-card h3 a').first();
    const detailHref=await titleLink.getAttribute('href');
    assert.match(detailHref,/back=.*page%3D2/);
    await titleLink.click();
    await page.goBack();
    assert.match(page.url(),/page=2/);

    for (const width of [320,390,768,1024,1365]) {
        await page.setViewportSize({width,height:900});
        for (const route of ['/search','/discover/trending','/discover/top-rated','/discover/new-releases','/discover/genres','/discover/genres?genre=878']) {
            const response=await page.goto(base+route);
            assert.equal(response.status(),200);
            assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Page overflow ${width}: ${route}`);
        }
        if (width<600) assert(await page.getByRole('combobox',{name:'Genre',exact:true}).isVisible());
    }
    await page.setViewportSize({width:390,height:844});
    await page.goto(base+'/discover/genres?genre=878');
    await page.getByRole('combobox',{name:'Genre',exact:true}).selectOption('35');
    await page.waitForURL('**/discover/genres?genre=35');
    assert.equal(await page.locator('#collection-heading').innerText(),'Comedy');
    const screenshots=process.env.QA_SCREEN_DIR || '.qa/discovery-screens';
    fs.mkdirSync(screenshots,{recursive:true});
    await page.screenshot({path:path.join(screenshots,'genre-mobile-fixture.png'),fullPage:false});
    assert.deepEqual(errors,[],'No uncaught client errors');
    console.log('Discovery UI passed: independent error/retry, period race, quick-add error/retry, cross-shelf duplicate guard, membership, keyboard focus, filters/pagination/back, 6 views at 5 widths and mobile genre selection.');
    await browser.close();
})().catch(error=>{console.error(error);process.exit(1);});
