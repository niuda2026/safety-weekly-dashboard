# -*- coding: utf-8 -*-
r"""
_refresh_public.py —— 公网 _public 静态快照一键刷新（2026-09-28 定稿版）
先跑本脚本，再 workbuddy_sites_deploy(directory=_public) 即完成"公网==本地"同步。

源对照（教训固化，勿改错源）：
  交通安全实时  D:\兴达数据库\交通安全行为看板\data.js
                → node build_equity_slim.js 生成 data/equity_slim_data.js → _public/equity-board/data.js
  内嵌板 HTML   _public/equity-board/{index,rating}.html 只改 data.js?t= 版本串（不能从 D 盘重生成，
                公网版是适配静态托管的特制副本，引用 escort_slim.js 而非 36MB data_excluded.js）。
                ⚠ 每次同步必须刷 t，否则 CDN 按 URL 缓存旧 slim → 明细表停旧日期（09-28 踩坑）。
  保险 V3 板    D:\兴达数据库\骑手保障补贴\专送合作商骑手保障补贴考核看板_2026_V3.html
                → _public/insurance_subsidy_v3.html（公网走 f.rel，本地走 /insurance-live/）
  保险赔付率    D:\兴达数据库\骑手保障补贴\bi_data\latest.json（437KB 真源！）
                → _public/bi_data/latest.json   ⚠ 不是 bi_insurance\latest.json（54KB 另一份，09-28 踩坑）
  保险保费      D:\兴达数据库\bi_insurance\premium_latest.json → _public/premium_latest.json
                （本地 V3 板靠 8766 实时服务补，公网无 8766 用此同源快照）
  履约看板      D:\兴达数据库\履约项目\兴达履约项目看板.html 改写后 → _public/penalty-board/index.html
                （本地是 server.py /penalty-board/ 路由动态改写，公网必须落成静态 index.html，
                 否则目录列表 → 明细表不显示，09-28 踩坑）
  履约数据 js   履约项目\{penalty_weekly,penalty_monthly,data,knife_rider_data,box_rider_data,
                inspection_data,morning_review_data}.js → _public/penalty-board/
                ⚠ 充换电血压_data.js 中文名静态沙箱不支持 → 改名 chargebp_data.js 并同步改写 src
  共享库        _libs\{html2canvas,chart,xlsx} → _public/_libs/（履约看板 ../_libs/ 改写为 /_libs/）
                ⚠ 三个库缺一不可，靠 onerror 回退 CDN 是异步的，赶不上主脚本执行
  周报本体      项目 data/*.json + index.html → _public/（不拷中文名 安全数据周报看板.html）
                ⚠ index.html 必须经 publicize_index() 改写：公网是静态托管，没有 /export-pdf，
                  导出按钮改为下载随包发布的 weekly-report.pdf
  整册 PDF      node _export_pdf.js → _exports/*.pdf 最新一份 → _public/weekly-report.pdf
                （加 --with-pdf 才生成；依赖本机 8421 服务在跑）
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import time

PROJECT = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(PROJECT, "_public")
D = r"D:\兴达数据库"

TRAFFIC_DATA_JS = os.path.join(D, "交通安全行为看板", "data.js")
ESCORT_JS = os.path.join(D, "护航服装", "data_excluded.js")
INS_DIR = os.path.join(D, "骑手保障补贴")
INS_V3_HTML = os.path.join(INS_DIR, "专送合作商骑手保障补贴考核看板_2026_V3.html")
INS_BI_LATEST = os.path.join(INS_DIR, "bi_data", "latest.json")
BI_PREMIUM = os.path.join(D, "bi_insurance", "premium_latest.json")
PEN_DIR = os.path.join(D, "履约项目")
PEN_BOARD_HTML = os.path.join(PEN_DIR, "兴达履约项目看板.html")
LIBS = os.path.join(D, "_libs")

SLIM_BUILDER = os.path.join(PROJECT, "build_equity_slim.js")
SLIM_OUT = os.path.join(PROJECT, "data", "equity_slim_data.js")
PUB_SLIM = os.path.join(PUB, "equity-board", "data.js")

PEN_JS = ["penalty_weekly.js", "penalty_monthly.js", "data.js", "knife_rider_data.js",
          "box_rider_data.js", "inspection_data.js", "inspection_daily_data.js",
          "morning_review_data.js"]

# 内嵌「交通安全四项」看板（与 server.py /four-board/ 注入完全一致：postMessage 联动 + 隐藏 KPI/大区卡）
# 2026-10-19：同步隐藏「骑手明细」tab —— 公网只保留站维度，骑手个人级明细不外露
FOUR_BOARD_HTML = os.path.join(D, "交通安全行为看板", "骑手交通行为明细看板.html")
FOUR_XLSX = os.path.join(D, "交通安全行为看板", "xlsx.full.min.js")
FOUR_FILTER_INJECT = (
    '<style>#panel-four .summary-row,#panel-four .region-cards-row{display:none!important}'
    '.tab-item[data-tab="rider"]{display:none!important}</style>'
    '<script>(function(){'
    'function dist(key,level){var rows=(typeof METRIC_CFG!=="undefined"&&METRIC_CFG.four)?METRIC_CFG.four.rows:[];'
    'var s={};rows.forEach(function(r){if(level&&r.level!==level)return;var v=r[key];if(v)s[v]=1;});'
    'return Object.keys(s);}'
    'function apply(f){try{'
    'if(typeof sfState==="undefined"||!sfState.four||typeof initStationFilters!=="function"||typeof applyFilter!=="function")return false;'
    '["region","subregion","city"].forEach(function(k){'
    'var opts=dist(k,k==="city"?"merchant":"subregion");'
    'sfState.four[k]=(f[k]||[]).filter(function(v){return opts.indexOf(v)>=0;});});'
    'initStationFilters("four");applyFilter("four");return true;}catch(e){return false;}}'
    'window.addEventListener("message",function(ev){var d=ev.data||{};'
    'if(d.type!=="xd-four-filter")return;'
    'var n=0;(function go(){if(apply(d)||n++>50)return;setTimeout(go,300);})();});'
    'try{var q=new URLSearchParams(location.search),f={};'
    '["region","subregion","city"].forEach(function(k){var v=q.get(k);if(v)f[k]=v.split(",").filter(Boolean);});'
    'if(Object.keys(f).length){var m=0;(function go(){if(apply(f)||m++>50)return;setTimeout(go,300);})();}}catch(e){}'
    '})();</script>'
)


def log(msg):
    print(msg, flush=True)


def cp(src, dst):
    if not os.path.isfile(src):
        log("  [缺失!] %s" % src)
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    log("  cp %s -> %s (%d B)" % (os.path.basename(src), os.path.relpath(dst, PROJECT), os.path.getsize(dst)))
    return True


def find_node():
    import shutil as sh
    # 优先用装了 Playwright 的那套（导 PDF 必须）
    for c in (r"C:\Users\牛艳朝\.workbuddy\binaries\node\versions\22.22.2-6\node.exe",
              r"C:\nodejs\node-v20.19.2-win-x64\node.exe",
              os.path.expanduser(r"~\.workbuddy\binaries\node\versions\22.22.2-3\node.exe")):
        if os.path.isfile(c):
            return c
    return sh.which("node")


def step1_equity_slim():
    log("[1] 交通安全 slim 重建")
    if not os.path.isfile(TRAFFIC_DATA_JS):
        log("  [缺失!] %s" % TRAFFIC_DATA_JS)
        return
    node = find_node()
    src_mt = os.path.getmtime(TRAFFIC_DATA_JS)
    if os.path.isfile(ESCORT_JS):
        src_mt = max(src_mt, os.path.getmtime(ESCORT_JS))
    if os.path.isfile(SLIM_OUT) and os.path.getmtime(SLIM_OUT) >= src_mt:
        log("  slim 已是最新（mtime >= 源），跳过重建")
    elif node and os.path.isfile(SLIM_BUILDER):
        r = subprocess.run([node, SLIM_BUILDER, TRAFFIC_DATA_JS, SLIM_OUT, ESCORT_JS],
                           capture_output=True, timeout=180)
        if r.returncode != 0:
            log("  [失败] build_equity_slim: %s" % r.stderr.decode("utf-8", "ignore")[:300])
            return
        log("  重建完成 %d B" % os.path.getsize(SLIM_OUT))
    else:
        log("  [警告] node 或 builder 缺失，沿用现有 slim")
    cp(SLIM_OUT, PUB_SLIM)


def step2_equity_html_patch():
    log("[2] 内嵌板 HTML 版本串刷新（CDN 缓存穿透）")
    t = str(int(time.time() * 1000))
    for name in ("index.html", "rating.html"):
        f = os.path.join(PUB, "equity-board", name)
        if not os.path.isfile(f):
            log("  [缺失!] %s" % f)
            continue
        with open(f, encoding="utf-8") as fh:
            html = fh.read()
        html2, n = re.subn(r'data\.js\?[^"\'\)\s>]+', 'data.js?t=' + t, html)
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write(html2)
        log("  %s: %d 处 -> t=%s" % (name, n, t))


def step3_insurance():
    log("[3] 保险快照（源=骑手保障补贴，保费=bi_insurance）")
    cp(INS_V3_HTML, os.path.join(PUB, "insurance_subsidy_v3.html"))
    cp(INS_BI_LATEST, os.path.join(PUB, "bi_data", "latest.json"))
    cp(BI_PREMIUM, os.path.join(PUB, "premium_latest.json"))
    cp(os.path.join(INS_DIR, "v3_data.js"), os.path.join(PUB, "v3_data.js"))
    cp(os.path.join(PROJECT, "insurance_subsidy_v2.html"), os.path.join(PUB, "insurance_subsidy_v2.html"))
    cp(os.path.join(PROJECT, "insurance_subsidy_monitor.html"), os.path.join(PUB, "insurance_subsidy_monitor.html"))
    cp(os.path.join(PROJECT, "insurance_rate_analysis.html"), os.path.join(PUB, "insurance_rate_analysis.html"))


def build_penalty_index():
    """改写履约看板 HTML 为公网静态版（与本地 server.py /penalty-board/ 路由行为一致）。"""
    with open(PEN_BOARD_HTML, encoding="utf-8") as fh:
        text = fh.read()
    t = str(int(time.time() * 1000))
    # 1) 中文名数据文件先改名（静态沙箱不支持中文文件名）
    text = text.replace('src="D:/兴达数据库/履约项目/充换电血压_data.js"',
                        'src="/penalty-board/chargebp_data.js"')
    # 2) 履约项目 js → /penalty-board/
    text = re.sub(r'src="D:/兴达数据库/履约项目/([^"]+\.js)"',
                  lambda m: 'src="/penalty-board/%s"' % m.group(1), text)
    # 3) 交通安全 data.js → slim（公网加 ?t= 防 CDN 缓存旧 slim；本地 server.py 靠 no-store）
    text = text.replace('src="D:/兴达数据库/交通安全行为看板/data.js"',
                        'src="/equity-board/data.js?t=' + t + '"')
    # 4) ../_libs → /_libs
    text = re.sub(r'src="\.\./_libs/([^"]+)"', r'src="/_libs/\1"', text)
    # 5) 注入与 server.py 完全一致的隐藏样式 + 自动切到 履约安全检查→履约达成处罚-周度
    #    2026-10-11 加固：switchTab 与 switchSafetySub 拆成独立 try（此前 switchTab 渲染巡检子页
    #    读缺失数据抛错会把整个 try 块打断，导致永远停在默认的巡检平台子页）；并在切换后校验实际
    #    激活子页，未落到 penalty-week 则有限次重试。务必让 inspection_daily_data.js 随 PEN_JS 落地。
    inject = (
        '<style>.header,.tab-bar,#summary-cards-penalty-week,#summary-cards-penalty-month'
        '{display:none!important}'
        '#panel-safety > .sub-tab-bar{display:none!important}</style>'
        '<script>(function(){var n=0;function go(){n++;'
        'if(typeof switchTab!=="function"||typeof switchSafetySub!=="function"){'
        'if(n<40)setTimeout(go,300);return;}'
        'try{switchTab("safety");}catch(e){}'
        'try{switchSafetySub("penalty-week");}catch(e){}'
        'var act=document.querySelector(\'#panel-safety [data-csub].active\');'
        'var pnl=document.getElementById("sub-penalty-week");'
        'if(!act||act.getAttribute("data-csub")!=="penalty-week"'
        '||!pnl||!pnl.classList.contains("active")){'
        'if(n<40)setTimeout(go,500);}}'
        'if(document.readyState==="complete"){setTimeout(go,150);}'
        'else{window.addEventListener("load",function(){setTimeout(go,150);});}})();</script>'
    )
    if "<head>" in text:
        text = text.replace("<head>", "<head>" + inject, 1)
    else:
        text = inject + text
    out = os.path.join(PUB, "penalty-board", "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    log("  生成 %s (%d B)" % (os.path.relpath(out, PROJECT), os.path.getsize(out)))


def step3b_four_board():
    """内嵌「交通安全四项」看板静态副本（公网版，与本地 /four-board/ 路由同源同源）。
    数据用 slim（TAB1_ROWS 已在其中；四项表/筛选下拉均读 METRIC_CFG.four.rows=TAB1_ROWS 派生，
    不依赖被置空的 RIDERS），无需 18MB 全量 data.js。"""
    log("[3b] 交通安全四项看板静态副本（slim 数据）")
    PUB_FOUR = os.path.join(PUB, "four-board")
    os.makedirs(PUB_FOUR, exist_ok=True)
    if not os.path.isfile(FOUR_BOARD_HTML):
        log("  [缺失!] %s" % FOUR_BOARD_HTML)
        return
    with open(FOUR_BOARD_HTML, encoding="utf-8") as fh:
        html = fh.read()
    t = str(int(time.time() * 1000))
    # ../_libs → /_libs（公网根 _libs 已存在）
    html = re.sub(r'src="\.\./_libs/([^"]+)"', r'src="/_libs/\1"', html)
    # data.js?版本串 → data.js?t= 防 CDN 缓存
    html = re.sub(r'data\.js\?[^"\'\)\s>]+', 'data.js?t=' + t, html)
    # 注入 postMessage 联动 + 隐藏 KPI/大区卡（与 server.py 一致）
    if "<head>" in html:
        html = html.replace("<head>", "<head>" + FOUR_FILTER_INJECT, 1)
    else:
        html = FOUR_FILTER_INJECT + html
    # 公网静态沙箱不支持中文文件名 → 改用 ASCII 名 ride_four.html，并同步改写公网 V3 的 fourFrameSrc
    out_html = os.path.join(PUB_FOUR, "ride_four.html")
    with open(out_html, "w", encoding="utf-8", newline="") as fh:
        fh.write(html)
    log("  生成 %s (%d B)" % (os.path.relpath(out_html, PROJECT), os.path.getsize(out_html)))
    # 同步改写公网 V3 副本的 fourFrameSrc：中文名 → ride_four.html
    pub_v3 = os.path.join(PUB, "insurance_subsidy_v3.html")
    if os.path.isfile(pub_v3):
        with open(pub_v3, encoding="utf-8") as fh:
            v3 = fh.read()
        v3b = v3.replace('"/four-board/" + encodeURIComponent("骑手交通行为明细看板.html")',
                         '"/four-board/ride_four.html"')
        if v3b != v3:
            with open(pub_v3, "w", encoding="utf-8", newline="") as fh:
                fh.write(v3b)
            log("  公网 V3 fourFrameSrc 已改写为 ride_four.html")
    # ⚠ 必须用全量 data.js（18MB）：四项表 getFourRows 依赖全量骑手明细，slim 的 TAB1_ROWS 映射后得 0 行
    #   （2026-10-19 Playwright 实测：slim 副本 table-four 0 行，全量副本 221 行）
    cp(TRAFFIC_DATA_JS, os.path.join(PUB_FOUR, "data.js"))
    # 导出 Excel 用的 xlsx
    cp(FOUR_XLSX, os.path.join(PUB_FOUR, "xlsx.full.min.js"))


def step4_penalty():
    log("[4] 履约看板静态化")
    for f in PEN_JS:
        cp(os.path.join(PEN_DIR, f), os.path.join(PUB, "penalty-board", f))
    cp(os.path.join(PEN_DIR, "充换电血压_data.js"), os.path.join(PUB, "penalty-board", "chargebp_data.js"))
    build_penalty_index()


def step5_libs():
    """公网必须自带全部依赖库。
    ⚠ 不能只靠 index.html 里的 onerror 回退 CDN：onerror 里 appendChild 是异步的，
      主脚本早已执行完 → `Chart is not defined`，公网整页图表全废（2026-10-24 实测）。"""
    log("[5] 共享库 _libs")
    for name in ("html2canvas-1.4.1.min.js", "chart.umd-4.4.7.min.js", "xlsx-0.18.5.full.min.js"):
        cp(os.path.join(LIBS, name), os.path.join(PUB, "_libs", name))


# 公网版 downloadAllData：静态托管没有 /export-pdf 服务，改为下载
# 同步时预先生成并随包发布的整册 PDF（ASCII 名 weekly-report.pdf）。
# 本机通过 8421 打开时仍优先走服务端实时导出。
PUBLIC_DOWNLOAD_FN = '''async function downloadAllData() {
    const btn = document.querySelector('[onclick="downloadAllData()"]');
    const oldText = btn ? btn.textContent : '';
    const setBtn = (t, dis) => { if (btn) { btn.textContent = t; btn.disabled = !!dis; } };
    setBtn('正在准备…', true);
    // 1) 本机服务在跑时走服务端实时导出（内容最新）
    try {
        const res = await fetch('/export-pdf', { method: 'POST' });
        const ct = res.headers.get('content-type') || '';
        if (res.ok && ct.indexOf('json') >= 0) {
            const data = await res.json();
            if (data && data.ok && data.url) {
                const a = document.createElement('a');
                a.href = data.url + '?t=' + Date.now();
                a.download = data.name || '履约安全周报.pdf';
                document.body.appendChild(a); a.click(); a.remove();
                setBtn('已生成（' + (data.pages || '') + '页），下载中…', true);
                setTimeout(() => setBtn(oldText, false), 3000);
                return;
            }
        }
    } catch (e) { /* 静态托管无此接口，走下面的静态 PDF */ }
    // 2) 静态托管：下载随包发布的整册 PDF
    const url = '/weekly-report.pdf?t=' + Date.now();
    try {
        const head = await fetch(url, { method: 'HEAD' });
        if (!head.ok) throw new Error('尚未生成（HTTP ' + head.status + '）');
    } catch (e) {
        setBtn(oldText, false);
        if (confirm('整册 PDF 暂不可用：' + e.message +
            '\\n\\n是否改为导出 Excel（只有数据表，不含看板样式）？')) {
            downloadAllDataExcel();
        }
        return;
    }
    const a = document.createElement('a');
    a.href = url;
    a.download = '履约安全周报.pdf';
    document.body.appendChild(a); a.click(); a.remove();
    setBtn('下载中…', true);
    setTimeout(() => setBtn(oldText, false), 3000);
}

'''


def publicize_index(src_html):
    """把本地 index.html 改写成公网静态版。

    - downloadAllData 换成公网版（静态 PDF 兜底）
    - 去掉仅本地服务才有的实时入口
    """
    start = src_html.find('async function downloadAllData() {')
    if start < 0:
        raise RuntimeError("index.html 里找不到 downloadAllData()，公网适配失败")
    end_mark = '// 原「下载所有数据」逻辑'
    end = src_html.find(end_mark, start)
    if end < 0:
        raise RuntimeError("index.html 里找不到 downloadAllData 结束标记，公网适配失败")
    return src_html[:start] + PUBLIC_DOWNLOAD_FN + src_html[end:]


def step6_weekly(with_pdf=False):
    log("[6] 周报本体 data/*.json + index.html + monthly_summary")
    n = 0
    for f in glob.glob(os.path.join(PROJECT, "data", "*.json")):
        if cp(f, os.path.join(PUB, "data", os.path.basename(f))):
            n += 1
    log("  data/*.json 共 %d 个" % n)
    with open(os.path.join(PROJECT, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    out = os.path.join(PUB, "index.html")
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write(publicize_index(html))
    log("  生成 %s (%d B，已做公网适配)" % (os.path.relpath(out, PROJECT), os.path.getsize(out)))
    cp(os.path.join(D, "交通安全行为看板", "monthly_summary.js"), os.path.join(PUB, "monthly_summary.js"))
    if with_pdf:
        step6b_weekly_pdf()


def _service_up(port=8421):
    import socket
    s = socket.socket()
    s.settimeout(1.2)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def step6b_weekly_pdf():
    """随包发布一份整册 PDF（公网无动态导出能力，封面按钮直接下载它）。"""
    log("[6b] 生成整册 PDF 供公网下载")
    node = find_node()
    script = os.path.join(PROJECT, "_export_pdf.js")
    if not node or not os.path.isfile(script):
        log("  [跳过] node 或 _export_pdf.js 缺失")
        return
    if not _service_up(8421):
        log("  [跳过] 8421 未启动，PDF 导出依赖本地页面渲染")
        return
    out_dir = os.path.join(PROJECT, "_exports")
    t0 = time.time()
    env = dict(os.environ)
    env["NODE_PATH"] = r"C:\Users\牛艳朝\.workbuddy\binaries\node\workspace\node_modules"
    r = subprocess.run([node, script, out_dir], capture_output=True, timeout=900, env=env)
    out = (r.stdout or b"").decode("utf-8", "ignore")
    err = (r.stderr or b"").decode("utf-8", "ignore")
    if r.returncode != 0:
        log("  [失败] rc=%s %s" % (r.returncode, (err or out)[-400:]))
        return
    pdfs = sorted(glob.glob(os.path.join(out_dir, "*.pdf")), key=os.path.getmtime)
    if not pdfs:
        log("  [失败] 未产出 PDF")
        return
    newest = pdfs[-1]
    dst = os.path.join(PUB, "weekly-report.pdf")
    shutil.copyfile(newest, dst)
    log("  发布 weekly-report.pdf (%d B, 耗时 %.0fs，源 %s)"
        % (os.path.getsize(dst), time.time() - t0, os.path.basename(newest)))


CLEANUP_FILES = ["server.py", "start_server.bat", "start_silent.vbs", "sync.bat",
                 "update_data.bat", "update_insurance.bat", "gen_dashboard_data.py",
                 "使用说明.txt", "日常操作速查.txt", "开机自启.bat", "注册开机自启.bat"]


def step7_cleanup():
    """清理 _public 内中文名文件与本地运维遗留文件（静态沙箱不支持中文文件名，
    解压会整目录失败）。这些文件是 09-04 初建副本遗留，看板从不引用。"""
    log("[7] 清理 _public 内中文名/本地运维遗留文件")
    removed = 0
    for root, dirs, files in os.walk(PUB):
        for f in files:
            if not all(ord(c) < 128 for c in f):
                p = os.path.join(root, f)
                try:
                    os.remove(p); removed += 1
                except Exception as e:
                    log("  [清理失败] %s: %s" % (p, e))
    for f in CLEANUP_FILES:
        p = os.path.join(PUB, f)
        if os.path.isfile(p):
            try:
                os.remove(p); removed += 1
            except Exception:
                pass
    log("  共清理 %d 个文件" % removed)


def main():
    t0 = time.time()
    with_pdf = "--with-pdf" in sys.argv
    log("=== _refresh_public 开始%s ===" % ("（含整册 PDF）" if with_pdf else ""))
    step1_equity_slim()
    step2_equity_html_patch()
    step3_insurance()
    step3b_four_board()
    step4_penalty()
    step5_libs()
    step6_weekly(with_pdf=with_pdf)
    step7_cleanup()
    log("=== 完成，耗时 %.1fs。下一步：workbuddy_sites_deploy(directory=_public) ===" % (time.time() - t0))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
