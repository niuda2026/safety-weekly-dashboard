// build_equity_slim.js — 生成「站维度」精简版交通 data.js（供周报看板内嵌安全权益/站长评级看板使用）
// 用法: node build_equity_slim.js <源data.js路径> <输出路径> [护航服装data_excluded.js路径]
// 只保留站维度变量；骑手级明细(RIDERS/SPEED_RIDER_ROWS)置空，体积从 ~20MB 降到 <1MB。
// 额外：把护航服装 ESCORT_DATA 聚合成站级 RATING_CLOTHING_ROWS（工装检核率 cloth / 美团工服率 vis），
//       口径与源「站长安全评级看板.html」buildClothingRows() 完全一致：
//       cloth_rate = Σcn/Σon（目标80%）、vis_rate = Σvc/Σto（目标92%）。
// 只读源文件、只写输出文件，绝不改动原工作台任何数据。
'use strict';
const fs = require('fs');

const srcPath = process.argv[2];
const outPath = process.argv[3];
const escortPath = process.argv[4] || 'D:\\兴达数据库\\护航服装\\data_excluded.js';
if (!srcPath || !outPath) {
  console.error('usage: node build_equity_slim.js <src data.js> <out slim.js> [escort data_excluded.js]');
  process.exit(2);
}

const KEYS = [
  'TAB1_ROWS',          // 安全权益明细（站点/区域/城市行）
  'TAB2_ROWS',          // 站长安全评级明细（站点/区域/城市行：闯红灯率/里程逆行率）
  'CLOTHING_ROWS',      // 骑手服装标准化率（站维度）
  'CHECK_FAIL_ROWS',    // 中西管控名单
  'CHECK_PHOTO_MAP',    // 管控名单照片
  'SPEED_SITE_ROWS',    // 高速监控看板-站
  'DATES',
  'LATEST_DATE',
  'ORDER_QTY_DATE',
  // 骑手级变量保留键名但置空，避免页面引用报错：
  'RIDERS',
  'SPEED_RIDER_ROWS',
];

const src = fs.readFileSync(srcPath, 'utf8');
const d = new Function(src + ';\nreturn {' + KEYS.join(',') + '};')();

// 站维度 only：骑手明细一律置空（用户 2026-09-26 指定）
d.RIDERS = [];
d.SPEED_RIDER_ROWS = [];

// ── 护航服装 ESCORT_DATA → 站级工装检核率/美团工服率聚合 ──
// riders 列: [0]日期 [1]大区 [2]区域 [3]城市 [4]站点 [5]骑手ID [6]骑手
//            [7]cn可检核 [8]on有完成单 [9]vn [10]vv [11]vr [12]vc视觉覆盖 [13]to完成运单 [14]vcr
function buildRatingClothingRows() {
  let escort = null;
  try {
    const raw = fs.readFileSync(escortPath, 'utf8');
    // data_excluded.js 会写 window.ESCORT_DATA，Node 下注入一个假 window 对象
    const fakeWindow = {};
    escort = new Function('window', raw + ';\nreturn window.ESCORT_DATA;')(fakeWindow);
  } catch (e) {
    console.warn('WARN: 护航服装数据不可用(' + e.message + ')，RATING_CLOTHING_ROWS 置空');
    return null;
  }
  if (!escort || !Array.isArray(escort.riders)) return null;
  const dates = escort.dates || [];
  const siteMap = {};
  for (const row of escort.riders) {
    if (!row || !row[4]) continue;
    const cn = Number(row[7]) || 0, on = Number(row[8]) || 0;
    const vc = Number(row[12]) || 0, to = Number(row[13]) || 0;
    const s = siteMap[row[4]] || (siteMap[row[4]] = {
      level: 'site', name: row[4], region: row[1], subregion: row[2], city: row[3] || '',
      cn: 0, on: 0, vc: 0, to: 0, cloth_dayNumDen: {}, vis_dayNumDen: {}
    });
    s.cn += cn; s.on += on; s.vc += vc; s.to += to;
    const dd = row[0];
    // 注意：aggregateWeekly 期望 [num, den] 数组形态（与 TAB2_ROWS 的 *dayNumDen 一致）
    if (s.cloth_dayNumDen[dd]) { s.cloth_dayNumDen[dd][0] += cn; s.cloth_dayNumDen[dd][1] += on; }
    else s.cloth_dayNumDen[dd] = [cn, on];
    if (s.vis_dayNumDen[dd]) { s.vis_dayNumDen[dd][0] += vc; s.vis_dayNumDen[dd][1] += to; }
    else s.vis_dayNumDen[dd] = [vc, to];
  }
  const pct2 = (n, den) => den > 0 ? Math.round(n / den * 10000) / 100 : null;
  const rows = Object.values(siteMap).map(s => ({
    level: 'site', name: s.name, region: s.region, subregion: s.subregion, city: s.city,
    cloth_num: s.cn, cloth_den: s.on, cloth_rate: pct2(s.cn, s.on),
    vis_num: s.vc, vis_den: s.to, vis_rate: pct2(s.vc, s.to),
    cloth_dayNumDen: s.cloth_dayNumDen,
    vis_dayNumDen: s.vis_dayNumDen
  }));
  console.log('RATING_CLOTHING_ROWS site rows=' + rows.length + ' dates=' + dates.length);
  return rows;
}

d.RATING_CLOTHING_ROWS = buildRatingClothingRows();

let out = '// 自动生成：站维度精简数据（不含全量骑手明细）— build_equity_slim.js\n';
out += '// 源: ' + srcPath + '\n';
out += '// 生成时间: ' + new Date().toISOString() + '\n';
for (const k of KEYS) {
  out += 'var ' + k + ' = ' + JSON.stringify(d[k]) + ';\n';
}
// RATING_CLOTHING_ROWS 可能为 null（护航服装数据缺失时），也要输出键名避免页面报错
out += 'var RATING_CLOTHING_ROWS = ' + JSON.stringify(d.RATING_CLOTHING_ROWS) + ';\n';
fs.writeFileSync(outPath, out, 'utf8');
console.log('OK bytes=' + Buffer.byteLength(out) + ' LATEST_DATE=' + d.LATEST_DATE);
