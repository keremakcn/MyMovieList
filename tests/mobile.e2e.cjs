/* Touch-focused checks against the isolated frontend fixture server. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:5057';
(async () => {
    const browser = await chromium.launch({headless:true, ...(process.env.EDGE_PATH ? {executablePath:process.env.EDGE_PATH} : {})});
    const context = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:2});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    fs.mkdirSync('.qa/mobile-screens', {recursive:true});
    for (const width of [320,360,390,412]) {
        await page.setViewportSize({width,height:844});
        await page.goto(base);
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1), `Overflow at ${width}`);
        const actions = await page.locator('.movie-card').first().locator('button,a.edit-link').evaluateAll(nodes => nodes.map(n=>({width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height})));
        assert(actions.every(a=>a.width>=43.9 && a.height>=43.9), `Small touch action at ${width}: ${JSON.stringify(actions)}`);
        const heights = await page.locator('.movie-card').evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().height));
        assert(Math.max(...heights)-Math.min(...heights)<2, `Unequal card heights at ${width}`);
        await page.screenshot({path:`.qa/mobile-screens/library-${width}.png`,fullPage:true});
    }
    await page.setViewportSize({width:390,height:844});
    await page.locator('.app-nav a[href="/search"]').tap();
    await page.locator('#discover-input').fill('film');
    await page.locator('#suggestions [role=option]').first().tap();
    await page.waitForURL('**/catalog_movie/**');
    await page.goto(base+'/edit/1');
    assert.equal(await page.locator('#note').evaluate(n=>getComputedStyle(n).fontSize),'16px');
    await page.locator('#note').tap();
    await page.locator('#note').fill('A personal note, written on a phone.');
    // A short viewport approximates available space above an open keyboard.
    // Actual Android IME/insets still need emulator/device testing.
    await page.setViewportSize({width:390,height:420});
    await Promise.all([page.waitForNavigation(), page.getByRole('button',{name:'Save changes',exact:true}).tap()]);
    await page.goto(base+'/edit/1');
    assert.equal(await page.locator('#note').inputValue(),'A personal note, written on a phone.');
    await page.getByRole('button',{name:'Remove The Green Mile',exact:true}).tap();
    await page.getByRole('button',{name:'Undo',exact:true}).tap();
    await page.locator('form.movie-form').waitFor({state:'visible'});
    assert.deepEqual(errors,[]);
    console.log('Mobile touch targets, card alignment, four widths, suggestions, note saving, small viewport and Undo passed.');
    await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
