/* Automatic metadata and bilingual movie content against catalog_fixture_server.py. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:5065';

(async () => {
    const browser = await chromium.launch({headless:true, ...(process.env.EDGE_PATH ? {executablePath:process.env.EDGE_PATH} : {})});
    try {
        const page = await browser.newPage({viewport:{width:1365,height:950}});
        const errors=[];
        page.on('pageerror',error=>errors.push(error.message));
        const go = route=>page.goto(base+route);
        const state = async()=> (await page.request.get(base+'/__qa/state')).json();
        const changeLanguage = async language=>{
            await go('/settings');
            await page.locator('#ui-language').selectOption(language);
            await page.locator('.language-settings button').press('Enter');
            await page.waitForFunction(language=>document.documentElement.lang===language,language);
        };
        await go('/');
        await page.getByRole('link',{name:'Hababam Sınıfı',exact:true}).waitFor();
        await page.waitForFunction(()=>document.querySelector('.movie-card').dataset.metadataPending==='0');
        const before=(await state()).movies[0];
        assert.equal(before.title,'The Chaos Class');
        assert.equal(JSON.parse(before.entities_json).cast.length,15);
        assert.equal((await state()).calls.filter(([p])=>p==='movie/83651').length,1);
        await page.getByRole('link',{name:'Hababam Sınıfı',exact:true}).press('Enter');
        assert.equal(await page.locator('h1').innerText(),'Hababam Sınıfı');
        assert.match(await page.locator('main').innerText(),/okul maceraları/);
        assert.equal(await page.locator('.refresh-form').count(),0);
        assert.equal(await page.getByRole('link',{name:'Actor 14',exact:true}).isVisible(),false);
        await page.locator('.full-cast summary').press('Enter');
        assert.equal(await page.getByRole('link',{name:'Actor 14',exact:true}).isVisible(),true);
        await page.getByRole('link',{name:'Ertem Eğilmez',exact:true}).click();
        assert.match(page.url(),/\/explore\/person\/300/);
        await page.getByRole('link',{name:'Hababam Sınıfı',exact:true}).first().click();
        await page.getByRole('link',{name:'Arzu Film',exact:true}).click();
        assert.match(page.url(),/\/explore\/company\/174/);

        await go('/search?q=matrix&type=movie');
        const matrix=page.locator('.catalog-card').filter({has:page.getByRole('link',{name:'The Matrix',exact:true})});
        await matrix.locator('[data-add-movie] button').press('Enter');
        await matrix.locator('.in-library').waitFor();
        assert.equal((await state()).movies.length,2);
        assert.equal((await state()).calls.filter(([p])=>p==='movie/603').length,1);
        await go('/movie/2');
        assert.equal(await page.locator('h1').innerText(),'The Matrix');
        assert.match(await page.locator('main').innerText(),/Simüle edilmiş bir gerçeklik/);

        await changeLanguage('en');
        await go('/movie/1');
        assert.equal(await page.locator('h1').innerText(),'The Chaos Class');
        assert.match(await page.locator('main').innerText(),/Students challenge school rules/);
        await changeLanguage('tr');
        await go('/');
        await page.locator('#library-search-input').fill('HABABAM SINIFI');
        assert.equal(await page.locator('.movie-card[data-movie-id="1"]').isVisible(),true);
        await page.locator('#library-search-input').press('Enter');
        await page.waitForURL(/q=HABABAM/);
        await page.getByRole('link',{name:'Hababam Sınıfı',exact:true}).waitFor();

        const frozen=(await state()).movies;
        const csrf=await page.locator('meta[name="csrf-token"]').getAttribute('content');
        await page.request.post(base+'/__qa/provider',{form:{offline:'1',csrf_token:csrf}});
        const callsBefore=(await state()).calls.length;
        for (const route of ['/','/movie/1','/movie/2','/edit/1']) {
            await go(route);
            assert.equal(await page.locator('html').getAttribute('lang'),'tr');
            if (route==='/movie/1') assert.match(await page.locator('main').innerText(),/okul maceraları/);
        }
        assert.equal((await state()).calls.length,callsBefore);
        assert.deepEqual((await state()).movies,frozen);
        assert.deepEqual((await state()).movies[0],before);

        const output=process.env.UI_OUTPUT || '.qa/catalog-ui';
        fs.mkdirSync(output,{recursive:true});
        let views=0;
        for (const language of ['tr','en']) {
            await changeLanguage(language);
            for (const width of [320,390,768,1024,1365]) {
                await page.setViewportSize({width,height:950});
                for (const route of ['/','/movie/1','/edit/1']) {
                    await go(route);
                    const overflow=await page.evaluate(()=>({width:innerWidth,content:document.documentElement.scrollWidth}));
                    assert.ok(overflow.content<=overflow.width+1,`${language} ${route} ${width}`);
                    if (route==='/movie/1' && [390,1365].includes(width)) await page.screenshot({path:path.join(output,`movie-${language}-${width}.png`),fullPage:true});
                    views++;
                }
            }
        }
        const token=await page.locator('meta[name="csrf-token"]').getAttribute('content');
        await page.request.post(base+'/__qa/provider',{form:{offline:'0',csrf_token:token}});
        assert.deepEqual(errors,[]);
        console.log(JSON.stringify({result:'passed',responsiveViews:views,checks:['automatic legacy enrichment','full cast saved','keyboard full cast','actor and company navigation','search quick-add','bilingual content with fixed IDs','title aliases','offline details and editing','all movie fields preserved'],javascriptErrors:0}));
    } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
