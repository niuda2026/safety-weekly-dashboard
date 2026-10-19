// _verify_region_card_click.js — 验证「重点关注」大区汇总卡点击联动筛选（2026-10-19）
// 用例：安全权益 tab 点卡 → safetyRegion 选中 + 卡片高亮 + 模块站点过滤 + iframe 明细表联动；
//       再点同卡 → 取消；站长评级 tab 点卡 → ratingRegion 选中。
const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({
        executablePath: 'C:\\Users\\牛艳朝\\AppData\\Local\\ms-playwright\\chromium-1228\\chrome-win64\\chrome.exe'
    });
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    const errors = [];
    const notFound = [];
    page.on('pageerror', e => errors.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
    page.on('response', r => { if (r.status() === 404) notFound.push(r.url()); });

    await page.goto('http://127.0.0.1:8421/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    // 等重点关注模块渲染出大区卡
    await page.waitForSelector('.attention-stat-card.region-clickable', { timeout: 20000 });
    await page.waitForTimeout(1500);

    const out = [];
    const check = (desc, cond) => out.push((cond ? '[OK] ' : '[FAIL] ') + desc);

    // ---- 安全权益 tab ----
    // 只数「当前激活分类」里的卡：每个分类 5 张（模块内 2 个分类的 DOM 都存在）
    const ACTIVE = '.attention-category-content.active';
    const cnt = await page.locator('#safetyAttention ' + ACTIVE + ' .attention-stat-card.region-clickable').count();
    check('安全权益 tab 激活分类大区可点卡数量 = 5（实际 ' + cnt + '）', cnt === 5);

    const activeBefore = await page.locator('.attention-stat-card.region-active').count();
    check('初始无高亮卡（实际 ' + activeBefore + '）', activeBefore === 0);

    // 点击「华北一区」（激活分类里的那张）
    await page.locator('#safetyAttention ' + ACTIVE + ' .attention-stat-card.region-clickable', { hasText: '华北一区' }).first().click();
    await page.waitForTimeout(800);
    let selVal = await page.evaluate(() => document.getElementById('safetyRegion').value);
    check('点击华北一区 → safetyRegion 下拉 = ' + selVal, selVal === '华北一区');
    let activeCnt = await page.locator('#safetyAttention ' + ACTIVE + ' .attention-stat-card.region-active').count();
    check('华北一区卡高亮（激活分类 region-active 实际 ' + activeCnt + '）', activeCnt === 1);

    // 模块内站点按大区过滤：所有可见站点卡片区只出现华北一区分组
    let regionsShown = await page.evaluate(() => {
        return [...document.querySelectorAll('#safetyAttention .attention-region-header')]
            .map(e => e.textContent.trim()).filter(t => t);
    });
    check('模块问题数据只显示华北一区分组（实际：' + regionsShown.join(' | ').slice(0, 120) + '）',
        regionsShown.length >= 1 && regionsShown.every(t => t.includes('华北一区')));

    // iframe 明细表联动
    const frameRegion = await page.evaluate(() => {
        const w = document.getElementById('equityFrame') && document.getElementById('equityFrame').contentWindow;
        return w && w.sfState && w.sfState.equity ? JSON.stringify(w.sfState.equity.region) : 'N/A';
    });
    check('iframe 明细表 sfState.equity.region = ' + frameRegion, frameRegion === '["华北一区"]');

    // 再点同一个卡 → 取消筛选
    await page.locator('#safetyAttention ' + ACTIVE + ' .attention-stat-card.region-clickable', { hasText: '华北一区' }).first().click();
    await page.waitForTimeout(800);
    selVal = await page.evaluate(() => document.getElementById('safetyRegion').value);
    check('再点华北一区 → 取消（safetyRegion = ""，实际 "' + selVal + '"）', selVal === '');
    activeCnt = await page.locator('.attention-stat-card.region-active').count();
    check('高亮清除（实际 ' + activeCnt + '）', activeCnt === 0);

    // ---- 站长评级 tab ----
    await page.click('.tab-btn[data-tab="rating"]');
    await page.waitForTimeout(2500);
    const ratingCards = await page.locator('#ratingAttention ' + ACTIVE + ' .attention-stat-card.region-clickable').count();
    check('站长评级 tab 激活分类大区可点卡数量 = 5（实际 ' + ratingCards + '）', ratingCards === 5);
    if (ratingCards > 0) {
        await page.locator('#ratingAttention ' + ACTIVE + ' .attention-stat-card.region-clickable', { hasText: '中南大区' }).first().click();
        await page.waitForTimeout(800);
        selVal = await page.evaluate(() => document.getElementById('ratingRegion').value);
        check('站长评级点中南大区 → ratingRegion = ' + selVal, selVal === '中南大区');
        const frameRating = await page.evaluate(() => {
            const w = document.getElementById('ratingFrame') && document.getElementById('ratingFrame').contentWindow;
            return w && w.sfState && w.sfState.rating ? JSON.stringify(w.sfState.rating.region) : 'N/A';
        });
        check('评级 iframe sfState.rating.region = ' + frameRating, frameRating === '["中南大区"]');
        // 取消
        await page.locator('#ratingAttention ' + ACTIVE + ' .attention-stat-card.region-clickable', { hasText: '中南大区' }).first().click();
        await page.waitForTimeout(500);
        selVal = await page.evaluate(() => document.getElementById('ratingRegion').value);
        check('再点取消（ratingRegion = ""，实际 "' + selVal + '"）', selVal === '');
    }

    // 截图留档
    await page.screenshot({ path: '_pw_verify/region_card_click.png', fullPage: false });

    console.log(out.join('\n'));
    if (notFound.length) console.log('404 URLS（判断是否与本次改动相关）:\n' + [...new Set(notFound)].join('\n'));
    console.log(errors.length ? 'PAGE ERRORS:\n' + errors.join('\n') : 'NO PAGE ERRORS');
    await browser.close();
    process.exit(out.some(l => l.startsWith('[FAIL]')) || errors.length ? 1 : 0);
})().catch(e => { console.error('HARNESS FAIL:', e.message); process.exit(2); });
