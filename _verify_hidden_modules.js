// _verify_hidden_modules.js — 验证「安全权益 / 站长评级」两个模块已整体隐藏（2026-10-24）
// 检查：可见 tab 数=4、可见卡片=2、meta 不含两个模块名、默认面板=compliance、
//       两个面板不可见、无 JS 报错、截图留档。
const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({
        executablePath: 'C:\\Users\\牛艳朝\\AppData\\Local\\ms-playwright\\chromium-1228\\chrome-win64\\chrome.exe'
    });
    const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
    const errors = [];
    const notFound = [];
    page.on('pageerror', e => errors.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
    page.on('response', r => { if (r.status() === 404) notFound.push(r.url()); });

    await page.goto('http://127.0.0.1:8421/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    try {
        await page.waitForSelector('#statsGrid .stat-card', { timeout: 30000 });
    } catch (e) {
        console.log('警告：等 #statsGrid .stat-card 超时');
    }
    await page.waitForTimeout(2000);

    const r = await page.evaluate(() => {
        const vis = el => !!(el && el.offsetParent !== null && getComputedStyle(el).display !== 'none');
        const tabs = [...document.querySelectorAll('.tab-btn')];
        const cards = [...document.querySelectorAll('#statsGrid .stat-card')];
        const panels = [...document.querySelectorAll('.tab-panel')];
        return {
            tabTotal: tabs.length,
            tabVisible: tabs.filter(vis).map(t => t.textContent.trim()),
            tabHidden: tabs.filter(t => !vis(t)).map(t => t.textContent.trim()),
            cardTotal: cards.length,
            cardVisible: cards.filter(vis).length,
            metaText: (document.querySelector('.meta') || {}).innerText || '',
            activePanel: panels.filter(p => p.classList.contains('active')).map(p => p.id),
            panelSafetyVisible: vis(document.getElementById('panel-safety')),
            panelRatingVisible: vis(document.getElementById('panel-rating')),
            panelComplianceVisible: vis(document.getElementById('panel-compliance')),
        };
    });

    try {
        await page.screenshot({ path: '_verify_hidden_modules.png', fullPage: false,
                                animations: 'disabled', caret: 'hide', timeout: 15000 });
        console.log('截图已保存 _verify_hidden_modules.png');
    } catch (e) {
        console.log('截图失败（不影响判定）：' + e.message.split('\n')[0]);
    }

    const checks = [
        ['可见 tab 数 = 4', r.tabVisible.length === 4],
        ['隐藏 tab = 安全权益/站长评级', r.tabHidden.length === 2 && r.tabHidden.includes('安全权益') && r.tabHidden.includes('站长评级')],
        ['可见卡片 = 2', r.cardVisible === 2],
        ['meta 不含「安全权益」', !r.metaText.includes('安全权益')],
        ['meta 不含「站长评级」', !r.metaText.includes('站长评级')],
        ['默认面板 = panel-compliance', r.activePanel.length === 1 && r.activePanel[0] === 'panel-compliance'],
        ['安全权益面板不可见', !r.panelSafetyVisible],
        ['站长评级面板不可见', !r.panelRatingVisible],
        ['履约数据面板可见', r.panelComplianceVisible],
        ['无 JS 报错', errors.length === 0],
    ];

    console.log('可见 tab:', r.tabVisible.join(' | '));
    console.log('隐藏 tab:', r.tabHidden.join(' | '));
    console.log('可见卡片数:', r.cardVisible, '/', r.cardTotal);
    console.log('meta:', r.metaText.trim());
    console.log('active 面板:', r.activePanel.join(','));
    console.log('');
    let ok = true;
    for (const [name, pass] of checks) {
        if (!pass) ok = false;
        console.log((pass ? 'PASS ' : 'FAIL ') + name);
    }
    if (errors.length) console.log('\n错误：\n' + errors.slice(0, 5).join('\n'));
    if (notFound.length) console.log('\n404：\n' + [...new Set(notFound)].slice(0, 6).join('\n'));
    console.log('\n=== ' + (ok ? '全部通过' : '有失败项') + ' ===');
    await browser.close();
    process.exit(ok ? 0 : 1);
})();
