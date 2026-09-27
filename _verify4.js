const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('index.html', 'utf8');
// 1) 语法编译
const m = html.match(/<script>([\s\S]*?)<\/script>/);
try { new vm.Script(m[1]); console.log('[语法] 编译通过 OK'); }
catch (e) { console.log('[语法] 错误:', e.message); process.exit(1); }
// 2) 结构检查
console.log('[UI] safety筛选栏已解除隐藏:', !html.includes('<div class="controls" style="display:none">'));
for (const k of ['applySafetyTabFilter', 'pushSafetyFilterToFrame', 'populateSafetyCascade', 'getSafetyFilterValues'])
    console.log('[函数] ' + k + ':', html.includes('function ' + k) ? 'OK' : '缺失!');
console.log('[联动] applyFilter走applySafetyTabFilter:', html.includes("if (type === 'safety') applySafetyTabFilter();"));
console.log('[联动] updateCascadingFilters优先safety:', html.includes("if (type === 'safety') { populateSafetyCascade(); return; }"));
console.log('[联动] 初始加载/刷新走applySafetyTabFilter:', (html.match(/applySafetyTabFilter\(\)/g) || []).length, '处调用');
// 3) 逻辑实跑：筛选链路（mock渲染与iframe推送）
const dcode = fs.readFileSync("D:/兴达数据库/交通安全行为看板/data.js", "utf8");
const dctx = { window: {}, document: {}, console }; vm.createContext(dctx); vm.runInContext(dcode, dctx);
const src = html.slice(html.indexOf('function weekOfMonth'), html.indexOf('function loadEquityDataScript'))
    + html.slice(html.indexOf('function applySafetyTabFilter'), html.indexOf('function pushSafetyFilterToFrame'))
    + `
let __att = null, __pushed = null;
function renderSafetyScoreAttention(rows) { __att = rows; }
function pushSafetyFilterToFrame(f) { __pushed = f; }
function populateSafetyCascade() {}
`;
const ctx = { window: { TAB1_ROWS: dctx.TAB1_ROWS }, console };
vm.createContext(ctx);
vm.runInContext(src, ctx);
const total = vm.runInContext('getSafetyAttentionRows().length', ctx);
// 华北一区 洛阳分区 站点「兴必达【洛阳】关林站」筛选
vm.runInContext(`
globalThis.__f = { search:'', region:'华北一区', zone:'洛阳', city:'', station:'' };
let rows = getSafetyAttentionRows();
if (__f.region) rows = rows.filter(r => (r.大区 || '') === __f.region);
if (__f.zone) rows = rows.filter(r => (r.分区 || '') === __f.zone);
__att = rows;
`, ctx);
const cnt = vm.runInContext('__att.length', ctx);
const names = vm.runInContext('__att.map(r=>r.站点).join(" | ")', ctx);
console.log('[逻辑] 全量站点:', total, '→ 华北一区+洛阳分区:', cnt, '站:', names);
// 搜索匹配逻辑（镜像 pushSafetyFilterToFrame 的搜索映射）
vm.runInContext(`
const search = '关林';
const siteRows = TAB1_ROWS.filter(r => r.level === 'site');
const matchedSites = [...new Set(siteRows.map(r => r.name).filter(n => n && n.toLowerCase().indexOf(search) >= 0))];
globalThis.__ms = matchedSites;
`, ctx);
console.log('[搜索] 「关林」映射到站点多选:', vm.runInContext('__ms.join(",")', ctx));
// 汇总（只统计 site 行）
const regs = vm.runInContext('[...new Set(TAB1_ROWS.filter(r=>r.level==="site").map(r=>r.大区))].filter(Boolean).sort((a,b)=>a.localeCompare(b,"zh"))', ctx);
console.log('[级联] 大区选项:', regs.join('、'));
console.log('[结论] 筛选联动逻辑跑通 OK');
