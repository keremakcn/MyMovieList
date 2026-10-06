/* UI language regressions against discovery_fixture_server.py; no user data. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:5059';

(async () => {
    const browser = await chromium.launch({headless:true, ...(process.env.EDGE_PATH ? {executablePath:process.env.EDGE_PATH} : {})});
    try {
        const page = await browser.newPage({viewport:{width:1365,height:950}});
        const errors=[];
        page.on('pageerror', error=>errors.push(error.message));
        const go = route=>page.goto(base+route);
        const changeLanguage = async language=>{
            await go('/settings');
            await page.locator('#ui-language').selectOption(language);
            await page.locator('.language-settings button').press('Enter');
            await page.waitForFunction(language=>document.documentElement.lang===language,language);
            assert.equal(await page.locator('#ui-language').inputValue(),language);
        };
        const card = id=>page.locator(`.movie-card[data-movie-id="${id}"]`);
        await changeLanguage('tr');
        assert.equal(await page.locator('h1').innerText(),'Ayarlar');
        await page.reload();
        assert.equal(await page.locator('#ui-language').inputValue(),'tr');
        assert.equal((await page.request.get(base+'/api/ui-language')).headers()['content-language'],'tr');

        await go('/search');
        const add = page.locator('#discovery-trending [data-discovery-movie="606"] button');
        await add.waitFor();
        let failOnce=true;
        await page.route('**/add_from_catalog',async route=>{
            if (failOnce) {
                failOnce=false;
                await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Keşif servisi geçici olarak kullanılamıyor. Lütfen tekrar dene.'})});
            } else await route.continue();
        });
        await add.press('Enter');
        await page.getByText('Keşif servisi geçici olarak kullanılamıyor. Lütfen tekrar dene.',{exact:true}).waitFor();
        assert.equal(await add.isEnabled(),true);
        const addedRequest = page.waitForRequest(request=>request.url().endsWith('/add_from_catalog'));
        await add.press('Enter');
        assert.match((await addedRequest).postData(),/name="movie_id"\r\n\r\n606/);
        await page.locator('#discovery-trending [data-discovery-movie="606"] .in-library').waitFor();
        assert.equal(await page.locator('#discovery-trending [data-discovery-movie="606"] .library-action').getAttribute('data-movie-title'),'Fixture film 4');

        await go('/');
        assert.match(await card(1).innerText(),/Fixture film 1/);
        assert.match(await card(1).innerText(),/Keep this private note\./);
        assert.match(await card(1).innerText(),/9\/10/);
        const removal = page.waitForResponse(response=>response.url().endsWith('/delete/1'));
        await card(1).locator('[data-delete] button').press('Enter');
        assert.equal((await removal).status(),200);
        await page.getByRole('button',{name:'Geri al',exact:true}).waitFor();
        await page.keyboard.press('Control+z');
        await card(1).waitFor();
        assert.match(await card(1).innerText(),/Keep this private note\./);
        assert.match(await card(1).innerText(),/9\/10/);
        assert.equal(await card(1).locator('button[aria-label="Favorilerden çıkar"]').getAttribute('aria-pressed'),'true');

        const statusResponse=page.waitForResponse(response=>response.url().endsWith('/status/2'));
        await card(2).locator('form[action^="/status/"] button').press('Enter');
        const statusResult=await (await statusResponse).json();
        assert.equal(statusResult.status,'Watched');
        await page.waitForFunction(()=>document.querySelector('[data-movie-id="2"] .status-badge')?.textContent==='İzlendi');
        assert.match(await card(2).innerText(),/Fixture film 2/);
        await page.locator('[data-library-filter] select').selectOption('added_asc');
        await page.waitForURL(/sort=added_asc/);

        await go('/search');
        const input=page.locator('#discover-input');
        await input.fill('Fixture');
        await page.locator('#suggestions [role="option"]').first().waitFor();
        assert.match(await page.locator('#suggestions').innerText(),/Film/);
        await input.press('ArrowDown');
        await input.press('Enter');
        await page.waitForURL(/catalog_movie\/603/);
        assert.equal(await page.locator('h1').innerText(),'Fixture film 1');
        assert.match(await page.locator('.info-badges').innerText(),/Drama/);

        await go('/discover/genres?genre=878');
        assert.equal(await page.locator('select[name="genre"]').inputValue(),'878');
        assert.match(await page.locator('#collection-heading').innerText(),/Bilim kurgu/);
        await go('/taste');
        await page.locator('.taste-card').first().waitFor();
        assert.match(await page.locator('.taste-card strong').first().innerText(),/Fixture film/);
        await page.locator('.taste-card input').first().check();
        assert.match(await page.locator('#taste-selected').innerText(),/Fixture film/);
        await page.locator('#taste-mode').selectOption('explore');
        assert.equal(await page.locator('#taste-mode').inputValue(),'explore');
        await go('/recommendations');
        await page.waitForFunction(()=>document.getElementById('recommendation-results').getAttribute('aria-busy')==='false');
        assert.equal(await page.locator('#refresh-recommendations').innerText(),'Yeni öneriler');

        const output=process.env.UI_OUTPUT || path.join('.qa','localization-ui');
        fs.mkdirSync(output,{recursive:true});
        let views=0;
        const titlesBefore = await (await page.request.get(base+'/')).text();
        for (const language of ['tr','en']) {
            await changeLanguage(language);
            await go('/');
            assert.match(await page.locator('.movie-list').innerText(),/Fixture film 1/);
            assert.match(await page.locator('.movie-list').innerText(),/Keep this private note\./);
            for (const width of [320,390,768,1024,1365]) {
                await page.setViewportSize({width,height:950});
                for (const route of ['/','/settings','/search','/search?q=Fixture&type=movie','/catalog_movie/603','/discover/trending','/taste','/recommendations']) {
                    await go(route);
                    assert.equal(await page.locator('html').getAttribute('lang'),language);
                    const overflow=await page.evaluate(()=>({width:innerWidth,content:document.documentElement.scrollWidth}));
                    assert.ok(overflow.content<=overflow.width+1,`${language} ${route} ${width}: ${JSON.stringify(overflow)}`);
                    if (route==='/settings' && [390,1365].includes(width)) await page.screenshot({path:path.join(output,`settings-${language}-${width}.png`),fullPage:true});
                    views++;
                }
            }
        }
        assert.match(titlesBefore,/Fixture film 4/);
        assert.deepEqual(errors,[]);
        console.log(JSON.stringify({result:'passed',responsiveViews:views,checks:['saved language','keyboard save','TR/EN','add error and retry','canonical movie ID and status','Ctrl+Z Undo metadata','search suggestions and Enter navigation','genre ID','taste picks','recommendation labels','library remains unchanged'],javascriptErrors:errors.length}));
    } finally { await browser.close(); }
})().catch(error=>{ console.error(error); process.exitCode=1; });
