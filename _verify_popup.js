// Node harness: 实跑 showDetail 弹窗过滤逻辑（修复后验证）
const fs = require('fs');
const html = fs.readFileSync('index.html', 'utf8');

function extract(src, name) {
    const start = src.indexOf('function ' + name + '(');
    if (start === -1) throw new Error('extract fail: ' + name);
    let i = src.indexOf('{', start), depth = 0;
    for (; i < src.length; i++) {
        if (src[i] === '{') depth++;
        else if (src[i] === '}') { depth--; if (depth === 0) break; }
    }
    return src.slice(start, i + 1);
}
const fnShowDetail = extract(html, 'showDetail');
const fnEsc = extract(html, 'esc');
const fnMoney = extract(html, 'money');
const fnNum = extract(html, 'num');
const fnPct = extract(html, 'pct');

// DOM mock
const els = {};
global.document = {
    getElementById: function (id) {
        if (!els[id]) els[id] = { style: {}, textContent: '', innerHTML: '', addEventListener: function () {}, classList: { add() {}, remove() {} } };
        return els[id];
    }
};

// 真实明细数据
const store = { detailData: {} };
const files = { meeting: 'meeting_reject', inspection: 'inspection_detail', disinfect: 'disinfect_data', equipmentDetail: 'equipment_detail', health: 'health_violation' };
for (const [k, f] of Object.entries(files)) store.detailData[k] = JSON.parse(fs.readFileSync('data/' + f + '.json', 'utf8'));

// 层级判定 + fillHierarchy（与页面一致）用于构造 rowLevel 场景
function fillHierarchy(data, keys) {
    let prev = {};
    for (const row of data) { for (const k of keys) { if (row[k] && row[k].trim()) prev[k] = row[k]; else row[k] = prev[k] || ''; } }
    return data;
}

let out = [];
function run(desc, fn) {
    try { const r = fn(); out.push('[OK] ' + desc + ' => ' + r); }
    catch (e) { out.push('[FAIL] ' + desc + ' => ' + e.message); }
}
function bodyRows() {
    const h = els.modalBody.innerHTML || '';
    if (h.includes('modal-empty')) return 'EMPTY(' + (h.match(/modal-empty">([^<]*)/) || ['', ''])[1] + ')';
    return (h.match(/<tr>/g) || []).length - 1 + ' data rows';
}

eval(fnEsc + '\n' + fnMoney + '\n' + fnNum + '\n' + fnPct + '\n' + fnShowDetail);

// ---- 用例 ----
run('站点行 孟营二站 自检驳回弹窗（此前为空）', () => { showDetail('兴必达【秦皇岛】孟营二站', 'inspection_self', 'station'); return bodyRows(); });
run('站点行 在水一方站 自检驳回弹窗', () => { showDetail('兴必达【秦皇岛】在水一方站', 'inspection_self', 'station'); return bodyRows(); });
run('城市行 秦皇岛 自检驳回弹窗（应含该市2条）', () => { showDetail('秦皇岛', 'inspection_self', 'city'); return bodyRows(); });
run('区域行 津冀区域 督导驳回弹窗（应0条）', () => { showDetail('津冀区域', 'inspection_supervise', 'area'); return bodyRows(); });
run('区域行 山东区域 督导驳回弹窗（应1条）', () => { showDetail('山东区域', 'inspection_supervise', 'area'); return bodyRows(); });
run('城市行 上海 早会驳回弹窗（应1条，且无空行污染）', () => { showDetail('上海', 'meeting', 'city'); return bodyRows(); });
run('站点行 郑州德化站 督导罚款弹窗（应1条）', () => { showDetail('兴必达【郑州】德化站', 'inspection_supervise', 'station'); return bodyRows(); });
run('健康证弹窗（0条时应显示空态而非全量）', () => { showDetail('兴必达【临沂】兰山区站', 'health', 'station'); return bodyRows(); });
run('餐箱消毒 城市行 商丘（应1条）', () => { showDetail('商丘', 'disinfect', 'city'); return bodyRows(); });
run('装备违规 城市行 滁州（应1条）', () => { showDetail('滁州', 'equipment', 'city'); return bodyRows(); });

// ---- 层级判定抽查（fillHierarchy 之后）----
const comp = JSON.parse(fs.readFileSync('data/compliance.json', 'utf8'));
let rows = comp.slice(1).map(r => ({ 大区: r[0] || '', 分区: r[1] || '', 区域: r[2] || '' }));
fillHierarchy(rows, ['大区', '分区']);
function levelOf(r) {
    const isAreaSum = r.大区 && r.区域 === r.分区;
    const isCitySum = !isAreaSum && r.区域 && r.区域 !== r.分区 && r.区域 !== '兴必达（江苏）网络科技有限公司' && r.区域.indexOf('兴必达') === -1 && r.区域.indexOf('站') === -1;
    return isAreaSum ? 'area' : isCitySum ? 'city' : 'station';
}
const checks = [['中西区域', 'area'], ['西安', 'city'], ['太原', 'city'], ['青岛', 'city'], ['兴必达【西安】东关二站', 'station'], ['集约配送-兴必达【青岛】中央CBD站', 'station'], ['兴必达【秦皇岛】孟营二站', 'station']];
for (const [name, want] of checks) {
    const r = rows.find(x => x.区域 === name);
    run('层级判定 ' + name, () => { if (!r) throw new Error('row not found'); const lv = levelOf(r); if (lv !== want) throw new Error(lv + ' != ' + want); return lv; });
}
console.log(out.join('\n'));
