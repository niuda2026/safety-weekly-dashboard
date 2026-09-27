// 实跑验证：安全事故面板头部筛选（搜索+大区/区域/城市/站点级联）与 KPI 卡、明细表联动
const fs = require('fs');
const { JSDOM } = require('jsdom');

const DIR = 'C:/Users/牛艳朝/WorkBuddy/2026-09-04-04-42-17/safety-weekly-dashboard/';
const html = fs.readFileSync(DIR + 'index.html', 'utf-8');

const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://127.0.0.1:8421/' });
const win = dom.window;
const doc = win.document;

// fetch 永不 resolve：loadData() 挂起，不会覆盖我们注入的数据
win.fetch = () => new Promise(() => {});
win.XLSX = { read: () => ({}), utils: { sheet_to_json: () => [] } };

const m = html.match(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/);
// 注意：const store 只在「同一段 eval」的词法环境里可见，所以注入函数必须拼在同一段脚本末尾
const inject = `
window.__setup = function(a, o) { store.accident = processAccident(a); ORDERS_SITE = o; ACC_MANUAL = {}; };
`;
win.eval(m[1] + '\n' + inject);

// 注入真实数据
win.__setup(
    JSON.parse(fs.readFileSync(DIR + 'data/accident.json', 'utf-8')),
    JSON.parse(fs.readFileSync(DIR + 'data/orders_site.json', 'utf-8'))
);
win.renderAccidentTab();

const $ = id => doc.getElementById(id);
const opts = id => Array.from($(id).options).map(o => o.value).filter(Boolean);
const rowCount = () => $('accTbody').querySelectorAll('tr').length;
const kpiTitles = () => Array.from($('accidentSummaryCards').querySelectorAll('h4')).map(h => h.textContent);
const info = () => $('accidentInfo').textContent;

function fire(el, type) { el.dispatchEvent(new win.Event(type, { bubbles: true })); }

console.log('=== 0. 基础渲染 ===');
console.log('  行数 =', rowCount(), '|', info());
console.log('  单量源 span 是否存在 =', !!$('accOrdersMeta'));
console.log('  明细表筛选栏“清除筛选”按钮 =', !!doc.querySelector('.acc-filter-bar .acc-clear-btn'));

console.log('=== 1. 头部下拉填充 ===');
console.log('  大区 =', JSON.stringify(opts('accidentRegion')));
console.log('  区域(全部) =', opts('accidentZone').length, '项 前3 =', JSON.stringify(opts('accidentZone').slice(0, 3)));
console.log('  城市(全部) =', opts('accidentCity').length, '项');
console.log('  站点(全部) =', opts('accidentStation').length, '项');

console.log('=== 2. 头部选大区 → 明细表 + KPI 联动 ===');
$('accidentRegion').value = '华北一区';
fire($('accidentRegion'), 'change');
console.log('  accState =', JSON.stringify(win.eval('JSON.stringify(accState)')));
console.log('  行数 =', rowCount(), '|', info());
console.log('  KPI 卡 =', JSON.stringify(kpiTitles()));
console.log('  区域下拉(级联) =', JSON.stringify(opts('accidentZone')));

console.log('=== 3. 头部再选区域 ===');
const z = opts('accidentZone')[0];
$('accidentZone').value = z;
fire($('accidentZone'), 'change');
console.log('  选中区域 =', z);
console.log('  行数 =', rowCount(), '| KPI =', JSON.stringify(kpiTitles()));
console.log('  城市下拉(级联) =', JSON.stringify(opts('accidentCity')));

console.log('=== 4. 头部选城市 ===');
const c = opts('accidentCity')[0];
$('accidentCity').value = c;
fire($('accidentCity'), 'change');
console.log('  选中城市 =', c);
console.log('  行数 =', rowCount(), '| KPI =', JSON.stringify(kpiTitles()));

console.log('=== 5. 头部搜索框 ===');
win.clearFilter('accident');
const kw = '西安';
$('accidentSearch').value = kw;
fire($('accidentSearch'), 'input');
console.log('  搜索 =', kw, '→ 行数 =', rowCount(), '| KPI =', JSON.stringify(kpiTitles()));
console.log('  ACC_SEARCH =', win.eval('ACC_SEARCH'));

console.log('=== 6. 清除筛选（头部按钮 / 明细表按钮） ===');
$('accidentSearch').value = '';
$('accidentRegion').value = '华东大区';
fire($('accidentRegion'), 'change');
console.log('  清除前 行数 =', rowCount());
win.clearFilter('accident');
console.log('  头部清除后 行数 =', rowCount(), '| 头部下拉值 =', ['accidentRegion','accidentZone','accidentCity','accidentStation'].map(i => $(i).value));
$('accidentRegion').value = '中南大区';
fire($('accidentRegion'), 'change');
console.log('  再选中南大区 行数 =', rowCount());
doc.querySelector('.acc-filter-bar .acc-clear-btn').dispatchEvent(new win.MouseEvent('click', { bubbles: true }));
console.log('  明细表“清除筛选”后 行数 =', rowCount(), '| 下拉值 =', ['accidentRegion','accidentZone','accidentCity','accidentStation'].map(i => $(i).value));

console.log('=== 7. 明细表多选筛选仍可用 + 与头部互相同步 ===');
win.accMsCheck('region', '华北一区');
win.accMsCheck('region', '华东大区');
console.log('  多选两个大区 行数 =', rowCount(), '| KPI =', JSON.stringify(kpiTitles()));
win.accMsCheck('region', '华东大区');
console.log('  只留华北一区 行数 =', rowCount(), '| 头部大区下拉 =', $('accidentRegion').value);

console.log('=== 8. 回归：公式列 / 手填 / 边框 ===');
win.clearFilter('accident');
const firstSite = win.eval(`(function(){var r=null;ACC_VIEWROWS.forEach(function(x){if(!r&&x.__level==='site')r=x;});return JSON.stringify({迟报:r.eff['迟报罚款'],工单迟报数:r.eff['工单迟报数'],超时:r.eff['超时罚款'],保险超时数:r.eff['保险超时数'],百万:r.eff['百万单事故数'],上报:r.eff['上报保险数'],单量:r.eff['上周完成单量']});})()`);
console.log('  首个站点行 =', firstSite);
console.log('  表头列数 =', $('accThead').querySelectorAll('th').length);
console.log('  含“小额赔付单均” =', $('accTbody').innerHTML.indexOf('小额赔付单均') >= 0);
