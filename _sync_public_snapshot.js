/**
 * _sync_public_snapshot.js — 公网静态托管快照同步（每周/每次部署前跑一次）
 *
 * 背景：公网静态托管没有本地 8421 的动态路由（/equity-board/、/护航服装/、/insurance-live/），
 * 且静态沙箱不支持中文文件名。本脚本把公网需要的所有资源以 ASCII 文件名落在本项目目录内：
 *
 *   equity-board/index.html          ← D:\兴达数据库\交通安全行为看板\安全权益看板.html（改写引用+注入内嵌CSS）
 *   equity-board/rating.html         ← D:\兴达数据库\交通安全行为看板\站长安全评级看板.html（同上 + escort 引用改瘦身影子）
 *   equity-board/data.js             ← data/equity_slim_data.js（站维度精简版，1.3MB）
 *   equity-board/escort_slim.js      ← 护航服装 data_excluded.js 按站×日聚合瘦身（36MB → 约0.5MB，数值完全一致）
 *   equity-board/xlsx.full.min.js    ← D:\兴达数据库\_libs\xlsx-0.18.5.full.min.js
 *   equity-board/html2canvas-1.4.1.min.js ← D:\兴达数据库\_libs
 *   insurance_subsidy_v3.html        ← D:\兴达数据库\骑手保障补贴\专送...V3.html（公网回退副本）
 *   bi_data/latest.json              ← D:\兴达数据库\骑手保障补贴\bi_data\latest.json
 *   premium_latest.json              ← D:\兴达数据库\bi_insurance\premium_latest.json
 *
 * 本地 8421 不受影响：server.py 仍实时透出 D:\ 兴达数据库原文件（见 server.py alias）。
 * 用法：node _sync_public_snapshot.js
 */
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const PROJ = __dirname;
const TRAFFIC = "D:\\兴达数据库\\交通安全行为看板";
const LIBS = "D:\\兴达数据库\\_libs";
const HUHU = "D:\\兴达数据库\\护航服装";
const INS = "D:\\兴达数据库\\骑手保障补贴";
const BI_INS = "D:\\兴达数据库\\bi_insurance";
const TS = Date.now();

function read(p) { return fs.readFileSync(p, "utf8"); }
function copy(src, dst) { fs.copyFileSync(src, dst); console.log("copy", path.basename(src), "->", path.relative(PROJ, dst), Math.round(fs.statSync(src).size / 1024) + "KB"); }

/* ---------- 1) 保证站维度精简 data.js 是新的 ---------- */
const srcDataJs = path.join(TRAFFIC, "data.js");
const slimJs = path.join(PROJ, "data", "equity_slim_data.js");
const escortSrc = path.join(HUHU, "data_excluded.js");
const srcMt = Math.max(fs.statSync(srcDataJs).mtimeMs, fs.statSync(escortSrc).mtimeMs);
if (!fs.existsSync(slimJs) || fs.statSync(slimJs).mtimeMs < srcMt) {
    console.log("slim data.js 过期，重新生成 ...");
    const node = process.execPath;
    execFileSync(node, [path.join(PROJ, "build_equity_slim.js"), srcDataJs, slimJs + ".tmp", escortSrc], { stdio: "inherit" });
    fs.renameSync(slimJs + ".tmp", slimJs);
}
console.log("slim data.js ok:", Math.round(fs.statSync(slimJs).size / 1024) + "KB");

/* ---------- 2) 护航服装 ESCORT_DATA 站×日聚合瘦身 ----------
 * 站长评级看板 buildClothingRows 只按 site/subregion/city/region/total 聚合求和，
 * 求和满足结合律 → 先把骑手级行聚合成 (d,region,subr,city,site) 一行，结果数值完全一致。
 * 保留 15 列形态：[d,region,subr,city,site,rid,rider,cn,on,vn,vv,vr,vc,to,vcr]
 */
function buildEscortSlim() {
    const code = read(escortSrc);
    const fakeWindow = {};
    const fn2 = new Function("window", code + "\nreturn window.ESCORT_DATA;");
    const data = fn2(fakeWindow);
    if (!data || !data.riders) throw new Error("ESCORT_DATA 解析失败");
    const keyOf = r => r[0] + "|" + r[1] + "|" + r[2] + "|" + r[3] + "|" + r[4];
    const map = new Map(), order = [];
    for (const r of data.riders) {
        if (!r || !r[4]) continue;           // 无站点行的行，看板本来也会跳过
        const k = keyOf(r);
        let s = map.get(k);
        if (!s) {
            s = [r[0], r[1], r[2], r[3], r[4], "", "", 0, 0, 0, 0, 0, 0, 0, 0];
            map.set(k, s); order.push(s);
        }
        s[7] += r[7] || 0;   // cn
        s[8] += r[8] || 0;   // on
        s[9] += r[9] || 0;   // vn
        s[10] += r[10] || 0; // vv
        s[12] += r[12] || 0; // vc
        s[13] += r[13] || 0; // to
    }
    const out = "window.ESCORT_DATA = " + JSON.stringify({ dates: data.dates || [], riders: order }) + ";";
    return { out, nRiders: data.riders.length, nSlim: order.length, dates: data.dates };
}

/* ---------- 3) 看板 HTML 改写（对齐 server.py 的代理改写口径） ---------- */
function rewriteBoard(html, opts) {
    let t = html;
    t = t.replace(/data\.js\?[^"')\s>]+/g, "data.js?t=" + TS);
    t = t.replace(/\.?\/?兴达丨交通安全行为看板_files\/xlsx\.full\.min\.js\.下载/g, "./xlsx.full.min.js");
    t = t.replace(/\.\.\/_libs\/html2canvas-1\.4\.1\.min\.js/g, "./html2canvas-1.4.1.min.js");
    if (opts.escort) t = t.replace(/\.\.\/护航服装\/data_excluded\.js\?[^"')\s>]*/g, "./escort_slim.js?t=" + TS);
    // 注入内嵌 CSS（与 server.py 一致：内嵌只看站维度明细表）
    const inject = '<style>.tab-item[data-tab="rider"],'
        + '.tab-item[data-tab="speed-rider"]{display:none!important}'
        + '.header,.tab-bar,'
        + '#summary-cards-equity,#summary-cards-rating,#summary-cards-clothing'
        + '{display:none!important}</style>';
    if (t.includes("<head>")) t = t.replace("<head>", "<head>" + inject);
    else t = inject + t;
    return t;
}

/* ---------- 主流程 ---------- */
const eqDir = path.join(PROJ, "equity-board");
fs.mkdirSync(eqDir, { recursive: true });
fs.mkdirSync(path.join(PROJ, "bi_data"), { recursive: true });

const escort = buildEscortSlim();
fs.writeFileSync(path.join(eqDir, "escort_slim.js"), escort.out, "utf8");
console.log("escort_slim.js:", escort.nRiders, "骑手行 ->", escort.nSlim, "站日行,",
    Math.round(fs.statSync(path.join(eqDir, "escort_slim.js")).size / 1024) + "KB, 日期", escort.dates[0], "~", escort.dates[escort.dates.length - 1]);

copy(path.join(slimJs), path.join(eqDir, "data.js"));
copy(path.join(LIBS, "xlsx-0.18.5.full.min.js"), path.join(eqDir, "xlsx.full.min.js"));
copy(path.join(LIBS, "html2canvas-1.4.1.min.js"), path.join(eqDir, "html2canvas-1.4.1.min.js"));

fs.writeFileSync(path.join(eqDir, "index.html"), rewriteBoard(read(path.join(TRAFFIC, "安全权益看板.html")), {}), "utf8");
console.log("equity-board/index.html ok");
fs.writeFileSync(path.join(eqDir, "rating.html"), rewriteBoard(read(path.join(TRAFFIC, "站长安全评级看板.html")), { escort: true }), "utf8");
console.log("equity-board/rating.html ok");

/* ---------- 4) 保险快照刷新 ---------- */
copy(path.join(INS, "专送合作商骑手保障补贴考核看板_2026_V3.html"), path.join(PROJ, "insurance_subsidy_v3.html"));
copy(path.join(INS, "bi_data", "latest.json"), path.join(PROJ, "bi_data", "latest.json"));
copy(path.join(BI_INS, "premium_latest.json"), path.join(PROJ, "premium_latest.json"));

console.log("\n全部同步完成，时间戳", TS);
