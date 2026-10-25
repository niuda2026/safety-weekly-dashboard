// _export_pdf.js — 把周报看板「所有模块的完整内容」按原样式导出成一份 PDF
// 用法: node _export_pdf.js [输出目录]
// 输出: stdout 打印 __RESULT__{json}
//
// 设计（2026-10-24 v9 分模块打印方案）：
//  早期做法是「一个页面里塞 3 个 iframe 再 page.pdf()」，但 Chromium 打印
//  「比一页还高的 iframe」时会把它整块推到下一页，上一页剩余空间白白留成空白页，
//  无论怎么调 CSS（break-inside / break-before / 去圆角）都消除不掉。
//  现改为：四个模块各自当独立页面打印成矢量 PDF，再用 pdf-lib 合并。
//   1) 首页：头部 + 履约数据 + 安全事故（隐藏罚款明细 iframe，那份单独成节）
//   2) /penalty-board/      履约达成处罚明细（227 行整表）
//   3) 保险赔付补贴监控      工作台保险分组真身
//   4) insurance_rate_analysis.html  保险赔付率解读
//  每个模块内部只是普通表格/卡片，分页由浏览器自然处理，不会再有空白页。
//  全程矢量：文字可搜索可复制、体积小。
const { chromium } = require('playwright');
const { PDFDocument, StandardFonts, rgb } = require('pdf-lib');
const path = require('path');
const fs = require('fs');

const CHROME = process.env.EXPORT_CHROME ||
    'C:\\Users\\牛艳朝\\AppData\\Local\\ms-playwright\\chromium-1228\\chrome-win64\\chrome.exe';
const ROOT = __dirname;
const OUT_DIR = process.argv[2] || path.join(ROOT, '_exports');
const BASE = process.env.EXPORT_BASE || 'http://127.0.0.1:8421/';

const PAGE = { format: 'A3', landscape: true };
const MARGIN = { top: '8mm', bottom: '10mm', left: '7mm', right: '7mm' };
const SCALE = 0.8;

function log(m) { console.log('[export] ' + m); }

// 解开限高 / 滚动 / sticky / 100vh —— 让整页内容一次性进入排版
const EXPAND_FN = `(function(){
    var doc = document, win = window;
    var all = doc.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
        var el = all[i], tag = el.tagName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'LINK') continue;
        var cs = win.getComputedStyle(el);
        if (cs.maxHeight && cs.maxHeight !== 'none') el.style.setProperty('max-height','none','important');
        if (cs.overflowY === 'auto' || cs.overflowY === 'scroll' || cs.overflowY === 'hidden' || cs.overflowY === 'clip')
            el.style.setProperty('overflow-y','visible','important');
        if (cs.overflow === 'auto' || cs.overflow === 'scroll' || cs.overflow === 'clip')
            el.style.setProperty('overflow','visible','important');
        if (cs.position === 'sticky') el.style.setProperty('position','static','important');
        if (cs.position === 'fixed' && tag !== 'IFRAME') {
            // 固定顶栏在打印时只出现在第一页，容易盖住内容 —— 改成随文档流
            el.style.setProperty('position','static','important');
        }
    }
    doc.documentElement.style.setProperty('height','auto','important');
    doc.documentElement.style.setProperty('min-height','0','important');
    if (doc.body) {
        doc.body.style.setProperty('height','auto','important');
        doc.body.style.setProperty('min-height','0','important');
    }
    var rectBottom = 0;
    var scan = doc.querySelectorAll('body *');
    for (var k = 0; k < scan.length; k++) {
        var e2 = scan[k];
        if (e2.tagName === 'SCRIPT' || e2.tagName === 'STYLE') continue;
        var r = e2.getBoundingClientRect();
        if (r.height > 0 && r.width > 0 && r.bottom + (win.scrollY || 0) > rectBottom)
            rectBottom = r.bottom + (win.scrollY || 0);
    }
    return rectBottom > 200 ? Math.ceil(rectBottom)
        : Math.max(doc.body ? doc.body.scrollHeight : 0, doc.documentElement.scrollHeight);
})()`;

const PRINT_CSS = `
    * { transition: none !important; animation: none !important; }
    .panel-header, .attention-block, .stat-card, .kpi-card { break-inside: avoid; }
    /* 汇总卡 / 重点关注卡整块不跨页，避免被页边切成半张 */
    #statsGrid > *, #complianceTotal > *, #complianceAttention > *,
    #accidentSummaryCards > *, .summary-row > * { break-inside: avoid; }
    tr { break-inside: avoid; }
    thead { display: table-header-group; }
    th { position: static !important; }
    iframe { border-radius: 0 !important; box-shadow: none !important; }
    /* 纯操作控件不进 PDF：缩放、截图、上传、导出按钮、tab 切换栏 */
    .zoom-controls, .screenshot-btn, .upload-btn, .upload-progress,
    .tabs, .tab-bar, .btn-clear-filter, .search-box, .select-box { display: none !important; }
    /* 折叠条款全部展开，保证「所有内容」都在（保险赔付率解读的五、六条等） */
    .acc-bd { display: block !important; }
    .acc-item .acc-arrow { transform: rotate(90deg) !important; }
`;

// 单独成节的模块，在页首补一条标题条（其余模块自带面板标题）
function bannerHtml(title, subtitle) {
    return '<div style="margin:0 0 14px;padding:14px 22px;border-radius:12px;' +
        'background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 100%);color:#fff;' +
        'font:700 21px/1.35 \'Microsoft YaHei\',\'PingFang SC\',sans-serif;">' +
        title +
        (subtitle ? '<span style="font-weight:400;font-size:13px;opacity:.86;margin-left:12px;">' + subtitle + '</span>' : '') +
        '</div>';
}

// 首页要单独处理：只留「履约数据 + 安全事故」两个面板
const MAIN_SETUP = `(function(){
    // 两个已隐藏的模块（安全权益 / 站长评级）不导出
    document.querySelectorAll('.mod-hidden').forEach(function(e){ e.style.display = 'none'; });
    // 保险两个面板、罚款明细 iframe 都单独成节导出，这里不重复
    ['panel-insurance-monitor','panel-insurance-rate'].forEach(function(id){
        var e = document.getElementById(id); if (e) e.style.display = 'none';
    });
    var pen = document.getElementById('framePenalty');
    if (pen) { var w = pen.closest('.table-wrap'); (w || pen).style.display = 'none'; }
    // 只保留要导出的两个面板
    ['panel-compliance','panel-accident'].forEach(function(id){
        var e = document.getElementById(id); if (e) e.style.display = 'block';
    });
    // 统计卡两套只留主 KPI
    var gi = document.getElementById('statsGridInsurance');
    if (gi) gi.style.display = 'none';
    return true;
})()`;

(async () => {
    const t0 = Date.now();
    fs.mkdirSync(OUT_DIR, { recursive: true });
    const tmpDir = path.join(OUT_DIR, '_parts');
    fs.mkdirSync(tmpDir, { recursive: true });

    const sections = [
        { key: 'main', url: BASE + '?_export=1', setup: MAIN_SETUP, waitMs: 3500, banner: null },
        { key: 'penalty', url: BASE + 'penalty-board/', setup: null, waitMs: 6000, banner: ['履约达成处罚明细', '周度 · 按大区/分区/城市/站点逐层汇总'] },
        { key: 'subsidy', url: BASE + 'insurance-live/' + encodeURIComponent('专送合作商骑手保障补贴考核看板_2026_V3.html'), setup: null, waitMs: 8000, banner: ['保险赔付补贴监控', '按指标加权得分率结算 · MTPS-ZS-QB-V3'], scale: 0.68 },
        { key: 'rate', url: BASE + 'insurance_rate_analysis.html', setup: null, waitMs: 6000, banner: ['保险赔付率解读', '考核周期口径与结算规则说明'], scale: 0.95 },
    ];

    const browser = await chromium.launch({ executablePath: CHROME });
    const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
    const parts = [];

    try {
        for (const sec of sections) {
            const page = await ctx.newPage();
            page.on('dialog', d => d.dismiss().catch(() => {}));
            try {
                await page.goto(sec.url, { waitUntil: 'domcontentloaded', timeout: 120000 });
                await page.waitForTimeout(1200);

                // 等业务数据渲染（表格有行 / KPI 有数）
                await page.waitForFunction(() => {
                    const rows = document.querySelectorAll('table tbody tr').length;
                    const cards = document.querySelectorAll('.stat-card, .kpi-card, .summary-card').length;
                    return rows > 0 || cards > 0;
                }, { timeout: 45000 }).catch(() => log(sec.key + ' 警告: 等数据超时，继续'));

                await page.waitForTimeout(sec.waitMs);

                if (sec.setup) await page.evaluate(sec.setup);

                // 单独成节的模块补标题条
                if (sec.banner) {
                    const html = bannerHtml(sec.banner[0], sec.banner[1] || '');
                    await page.evaluate(h => {
                        const box = document.createElement('div');
                        box.innerHTML = h;
                        const b = box.firstElementChild;
                        document.body.insertBefore(b, document.body.firstChild);
                    }, html).catch(e => log(sec.key + ' 标题条注入失败：' + e.message));
                    await page.waitForTimeout(400);
                }

                // 先上打印样式（展开折叠条款、隐藏操作控件），再量高度，装出来的高度才准
                await page.addStyleTag({ content: PRINT_CSS });
                await page.waitForTimeout(400);

                // 迭代展开，直到高度收敛
                let prev = -1, h = 0;
                for (let k = 0; k < 5; k++) {
                    h = await page.evaluate(EXPAND_FN).catch(() => 0);
                    if (Math.abs(h - prev) <= 8) break;
                    prev = h;
                    await page.waitForTimeout(1500);
                }
                await page.waitForTimeout(600);

                const part = path.join(tmpDir, 'part_' + sec.key + '.pdf');
                await page.pdf({
                    path: part,
                    format: PAGE.format,
                    landscape: PAGE.landscape,
                    printBackground: true,
                    margin: MARGIN,
                    scale: sec.scale || SCALE,
                    displayHeaderFooter: false,
                });
                parts.push(part);
                log(sec.key + ' 完成 · 内容高 ' + h + 'px · ' + (fs.statSync(part).size / 1024).toFixed(0) + 'KB');
            } finally {
                await page.close().catch(() => {});
            }
        }

        // ===== 合并 + 统一加页码（pdf-lib 标准字体只支持 ASCII，页码用纯数字）=====
        const out = await PDFDocument.create();
        const font = await out.embedFont(StandardFonts.Helvetica);
        const gray = rgb(0.58, 0.65, 0.72);
        for (const f of parts) {
            const src = await PDFDocument.load(fs.readFileSync(f));
            const copied = await out.copyPages(src, src.getPageIndices());
            copied.forEach(p => out.addPage(p));
        }
        const pages = out.getPages();
        const total = pages.length;
        pages.forEach((p, i) => {
            const label = String(i + 1) + ' / ' + total;
            const w = font.widthOfTextAtSize(label, 8);
            p.drawText(label, {
                x: p.getWidth() / 2 - w / 2,
                y: 8,
                size: 8,
                font,
                color: gray,
            });
        });

        const now = new Date();
        const pad = n => String(n).padStart(2, '0');
        const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}`;
        const name = `履约安全周报_${stamp}.pdf`;
        const outFile = path.join(OUT_DIR, name);
        fs.writeFileSync(outFile, await out.save());

        // 清掉分模块中间文件
        for (const f of parts) { try { fs.unlinkSync(f); } catch (e) {} }
        try { fs.rmdirSync(tmpDir); } catch (e) {}

        const size = fs.statSync(outFile).size;
        const ms = Date.now() - t0;
        log('完成 ' + name + ' · ' + total + ' 页 · ' + (size / 1024 / 1024).toFixed(2) + 'MB · 用时 ' + (ms / 1000).toFixed(0) + 's');
        console.log('__RESULT__' + JSON.stringify({ ok: true, file: outFile, name, size, ms, pages: total }));
        await browser.close();
        process.exit(0);
    } catch (e) {
        log('失败：' + (e && e.stack ? e.stack.split('\n')[0] : e));
        console.log('__RESULT__' + JSON.stringify({ ok: false, message: String(e && e.message || e) }));
        await browser.close().catch(() => {});
        process.exit(1);
    }
})();
