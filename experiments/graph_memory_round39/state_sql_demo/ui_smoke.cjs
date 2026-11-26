/* Exercise the local page in a real browser, including a reversible MSS change. */
const { chromium } = require(process.env.PLAYWRIGHT_DIR || 'playwright');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const path = require('node:path');
const assert = require('node:assert/strict');

async function run() {
  const server = spawn(process.env.DEMO_PYTHON || 'python', ['-B', 'demo.py', '--port', '0'], {
    cwd: __dirname, windowsHide: true, stdio: ['ignore','pipe','pipe']
  });
  let browser;
  try {
    const [first] = await once(server.stdout, 'data');
    const address = first.toString().trim();
    assert.match(address, /^http:\/\/127\.0\.0\.1:\d+\/$/);
    browser = await chromium.launch({ headless:true, executablePath:process.env.CHROME_PATH || undefined });
    const page = await browser.newPage({viewport:{width:1180,height:900}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(address);
    const top5 = page.locator('#scores > div').nth(1).locator('.grade').first();
    await page.waitForFunction(() => document.querySelector('#scores > div:nth-child(2) .grade')?.textContent === '@5 · полон');
    assert.equal(await page.locator('#states option').count(), 214);
    assert.equal(await page.locator('#units').inputValue(), '19');
    await page.locator('#flip').click();
    await page.waitForFunction(() => document.querySelector('#scores > div:nth-child(2) .grade')?.textContent === '@5 · неполон');
    assert.equal(await page.locator('#learned tbody tr').nth(1).locator('button').textContent(), 'u19');
    await page.screenshot({path:path.join(__dirname,'preview.png'),fullPage:true});
    await page.locator('#flip').click();
    await page.waitForFunction(() => document.querySelector('#scores > div:nth-child(2) .grade')?.textContent === '@5 · полон');
    await page.locator('#flip').click();
    await page.locator('#reset').click();
    await page.waitForFunction(() => document.getElementById('flip')?.textContent === 'Снять наблюдение');
    assert.equal(await top5.textContent(),'@5 · полон');
    await page.locator('#states').selectOption('s001');
    await page.waitForFunction(() => document.querySelector('#graph .node')?.textContent === 's001');
    assert.equal(await page.locator('#units option').count(),120);
    await page.setViewportSize({width:390,height:845});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
    assert.deepEqual(errors,[]);
    console.log('Verified desktop and mobile page, 214 states, remove/add/reset and independent MSS transition.');
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
}
run().catch(e => { console.error(e); process.exitCode=1; });
