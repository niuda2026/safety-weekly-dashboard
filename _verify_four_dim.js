/* 验证：保险V3 → 交通安全四项维度 → 内嵌四项看板联动 */
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:\\Users\\牛艳朝\\AppData\\Local\\ms-playwright\\chromium-1228\\chrome-win64\\chrome.exe',
    headless: true
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 950 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  const out = [];
  const check = (name, ok) => out.push((ok ? 'PASS' : 'FAIL') + ' | ' + name);

  // 直接打开 v3（模拟 monitor 壳 iframe 的 live 地址）
  await page.goto('http://127.0.0.1:8421/insurance_subsidy_v3.html?t=' + Date.now(), { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(2500);

  const btn = await page.locator('#dimSeg button[data-lvl="traffic4"]').count();
  check('考核维度行出现「交通安全四项」按钮', btn === 1);

  // 点击切换
  await page.locator('#dimSeg button[data-lvl="traffic4"]').click();
  await page.waitForTimeout(1000);
  const fourMode = await page.evaluate(() => document.body.classList.contains('four-mode'));
  check('body 进入 four-mode', fourMode);
  const panelVisible = await page.evaluate(() => {
    const p = document.getElementById('traffic4Panel');
    return p && p.offsetParent !== null;
  });
  check('内嵌面板可见', panelVisible);
  const goalHidden = await page.evaluate(() => {
    const g = document.querySelector('.goalbox');
    return g && getComputedStyle(g).display === 'none';
  });
  check('原保险模块（goalbox 等）已隐藏', goalHidden);

  // iframe 看板加载（18MB data.js，多等一会）
  await page.waitForTimeout(9000);
  const boardState = await page.evaluate(() => {
    const f = document.getElementById('fourFrame');
    if (!f) return { err: 'no frame' };
    try {
      const w = f.contentWindow, d = f.contentDocument;
      return {
        src: f.src,
        hasSfState: !!(w && w.sfState && w.sfState.four),
        rowsNum: w && w.METRIC_CFG && w.METRIC_CFG.four ? w.METRIC_CFG.four.rows.length : -1,
        tableHtmlLen: d ? (d.querySelector('#panel-four table') ? d.querySelector('#panel-four table').outerHTML.length : 0) : 0,
        dateFilter: (w && w.DATES) ? w.DATES.length : -1
      };
    } catch (e) { return { err: e.message }; }
  });
  check('内嵌看板 sfState.four 就绪: ' + JSON.stringify(boardState).slice(0, 200),
        boardState.hasSfState && boardState.rowsNum > 0 && boardState.tableHtmlLen > 1000);

  // 联动：在 v3 顶部选大区=中南大区 → postMessage 后看板 region 筛选生效
  await page.evaluate(() => {
    const bs = document.getElementById('bigFilter');
    bs.value = '中南大区'; bs.dispatchEvent(new Event('change'));
  });
  await page.waitForTimeout(3000);
  const afterBig = await page.evaluate(() => {
    const w = document.getElementById('fourFrame').contentWindow;
    return { region: w.sfState.four.region, cityOptsOnLabel: null };
  });
  check('v3 选大区 → 看板 region 筛选 = ' + JSON.stringify(afterBig.region),
        JSON.stringify(afterBig.region) === '["中南大区"]');

  // 联动：城市（regionFilter 此时是城市下拉）
  await page.evaluate(() => {
    const rs = document.getElementById('regionFilter');
    const opt = [...rs.options].find(o => o.value === '合肥');
    if (opt) { rs.value = '合肥'; rs.dispatchEvent(new Event('change')); }
  });
  await page.waitForTimeout(3000);
  const afterCity = await page.evaluate(() => {
    const w = document.getElementById('fourFrame').contentWindow;
    return { region: w.sfState.four.region, city: w.sfState.four.city };
  });
  check('v3 选城市合肥 → 看板 city 筛选 = ' + JSON.stringify(afterCity.city),
        JSON.stringify(afterCity.city) === '["合肥"]');

  // 取消城市筛选 → 看板恢复
  await page.evaluate(() => {
    const rs = document.getElementById('regionFilter');
    rs.value = ''; rs.dispatchEvent(new Event('change'));
  });
  await page.waitForTimeout(2000);
  const afterClear = await page.evaluate(() => {
    const w = document.getElementById('fourFrame').contentWindow;
    return w.sfState.four.city;
  });
  check('清除城市 → 看板 city 筛选清空', JSON.stringify(afterClear) === '[]');

  // 切回城市维度 → four-mode 退出、保险模块恢复
  await page.locator('#dimSeg button[data-lvl="merchant"]').click();
  await page.waitForTimeout(1500);
  const back = await page.evaluate(() => ({
    mode: document.body.classList.contains('four-mode'),
    goal: getComputedStyle(document.querySelector('.goalbox')).display
  }));
  check('切回城市维度 → four-mode 退出 & 保险模块恢复', !back.mode && back.goal !== 'none');

  await page.screenshot({ path: '_pw_verify/four_dim_v3.png', fullPage: false });
  console.log(out.join('\n'));
  console.log(errors.length ? 'PAGE ERRORS:\n' + errors.join('\n') : 'NO PAGE ERRORS');
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
