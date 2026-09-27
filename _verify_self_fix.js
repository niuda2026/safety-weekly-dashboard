// Node harness: 验证自检驳回/自检罚款修复（金光站补行 + 逐级汇总）与弹窗同源
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
const fnProc = extract(html, 'processCompliance');
const fnFill = extract(html, 'fillHierarchy');
const fnEsc = extract(html, 'esc');
const fnMoney = extract(html, 'money');
const fnNum = extract(html, 'num');

const els = {};
global.document = {
    getElementById: function (id) {
        if (!els[id]) els[id] = { style: {}, textContent: '', innerHTML: '', addEventListener: function () {}, classList: { add() {}, remove() {} } };
        return els[id];
    }
};
const store = { detailData: {} };
const files = { meeting: 'meeting_reject', inspection: 'inspection_detail', disinfect: 'disinfect_data', equipmentDetail: 'equipment_detail', health: 'health_violation' };
for (const [k, f] of Object.entries(files)) store.detailData[k] = JSON.parse(fs.readFileSync('data/' + f + '.json', 'utf8'));

let out = [];
function run(desc, fn) {
    try { const r = fn(); out.push('[OK] ' + desc + ' => ' + r); }
    catch (e) { out.push('[FAIL] ' + desc + ' => ' + e.message); }
}
function bodyRows() {
    const h = els.modalBody.innerHTML || '';
    if (h.includes('modal-empty')) return 'EMPTY';
    return (h.match(/<tr>/g) || []).length - 1 + ' data rows';
}

const raw = JSON.parse(fs.readFileSync('data/compliance.json', 'utf8'));
let rows;
eval(fnProc + '\n' + fnFill + '\n' + fnEsc + '\n' + fnMoney + '\n' + fnNum + '\n' + (extract(html, 'showDetail')));
rows = fillHierarchy(processCompliance(raw), ['大区', '分区']);

// 与 renderComplianceTable 相同的层级判定
function levelOf(r) {
    const isAreaSum = r.大区 && r.区域 === r.分区;
    const isCitySum = !isAreaSum && r.区域 && r.区域 !== r.分区 && r.区域 !== '兴必达（江苏）网络科技有限公司' && r.区域.indexOf('兴必达') === -1 && r.区域.indexOf('站') === -1;
    return isAreaSum ? 'area' : isCitySum ? 'city' : 'station';
}
function rowOf(name) { return rows.find(x => x.区域 === name); }
function expect(desc, cond) { run(desc, () => { if (!cond) throw new Error('assert fail'); return 'pass'; }); }

const jg = rowOf('兴必达【天津】金光站');
expect('金光站行已存在', !!jg);
expect('金光站 层级=station', jg && levelOf(jg) === 'station');
expect('金光站 大区/分区已回填', jg && jg.大区 === '华北一区' && jg.分区 === '津冀区域');
expect('金光站 自检 1次/100元', jg && String(num(jg.自检驳回)) === '1' && money(jg.自检罚款) === '¥100.00');
const tj = rowOf('天津');
expect('天津 层级=city 且 1次/100元', tj && levelOf(tj) === 'city' && String(num(tj.自检驳回)) === '1' && String(num(tj.自检罚款)) === '100');
const jzy = rowOf('津冀区域');
expect('津冀区域 层级=area 且 3次/300元', jzy && levelOf(jzy) === 'area' && String(num(jzy.自检驳回)) === '3' && String(num(jzy.自检罚款)) === '300');
const gs = rowOf('兴必达（江苏）网络科技有限公司');
expect('公司合计 5次/500元', gs && String(num(gs.自检驳回)) === '5' && String(num(gs.自检罚款)) === '500');
const sd = rowOf('山东区域'), xa = rowOf('中西区域');
expect('山东区域保持 1/100', sd && String(num(sd.自检驳回)) === '1' && String(num(sd.自检罚款)) === '100');
expect('中西区域保持 1/100', xa && String(num(xa.自检驳回)) === '1' && String(num(xa.自检罚款)) === '100');
// 其他列未被误改：金光站行 甲方预计总罚款=0、督导=0
expect('金光站行其余列为0（不污染其他指标）', jg && String(num(jg.甲方预计总罚款)) === '0' && String(num(jg.督导罚款)) === '0');

// 弹窗与表格同源校验
run('弹窗 金光站 自检驳回（应1条）', () => { showDetail('兴必达【天津】金光站', 'inspection_self', 'station'); return bodyRows(); });
run('弹窗 天津 城市自检驳回（应1条）', () => { showDetail('天津', 'inspection_self', 'city'); return bodyRows(); });
run('弹窗 津冀区域 自检驳回（应3条）', () => { showDetail('津冀区域', 'inspection_self', 'area'); return bodyRows(); });

console.log(out.join('\n'));
