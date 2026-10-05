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
  共享库        _libs\html2canvas-1.4.1.min.js → _public/_libs/（履约看板 ../_libs/ 改写为 /_libs/）
  周报本体      项目 data/*.json + index.html → _public/（不拷中文名 安全数据周报看板.html）
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
          "box_rider_data.js", "inspection_data.js", "morning_review_data.js"]


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
    p = sh.which("node")
    if p:
        return p
    for c in (r"C:\nodejs\node-v20.19.2-win-x64\node.exe",
              os.path.expanduser(r"~\.workbuddy\binaries\node\versions\22.22.2-3\node.exe")):
        if os.path.isfile(c):
            return c
    return None


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
    inject = (
        '<style>.header,.tab-bar,#summary-cards-penalty-week,#summary-cards-penalty-month'
        '{display:none!important}'
        '#panel-safety > .sub-tab-bar{display:none!important}</style>'
        '<script>(function(){function go(){try{'
        'if(typeof switchTab==="function"&&typeof switchSafetySub==="function"){'
        'switchTab("safety");switchSafetySub("penalty-week");}'
        'else{setTimeout(go,300);}}catch(e){setTimeout(go,500);}}'
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


def step4_penalty():
    log("[4] 履约看板静态化")
    for f in PEN_JS:
        cp(os.path.join(PEN_DIR, f), os.path.join(PUB, "penalty-board", f))
    cp(os.path.join(PEN_DIR, "充换电血压_data.js"), os.path.join(PUB, "penalty-board", "chargebp_data.js"))
    build_penalty_index()


def step5_libs():
    log("[5] 共享库 _libs")
    cp(os.path.join(LIBS, "html2canvas-1.4.1.min.js"), os.path.join(PUB, "_libs", "html2canvas-1.4.1.min.js"))


def step6_weekly():
    log("[6] 周报本体 data/*.json + index.html + monthly_summary")
    n = 0
    for f in glob.glob(os.path.join(PROJECT, "data", "*.json")):
        if cp(f, os.path.join(PUB, "data", os.path.basename(f))):
            n += 1
    log("  data/*.json 共 %d 个" % n)
    cp(os.path.join(PROJECT, "index.html"), os.path.join(PUB, "index.html"))
    cp(os.path.join(D, "交通安全行为看板", "monthly_summary.js"), os.path.join(PUB, "monthly_summary.js"))


def main():
    t0 = time.time()
    log("=== _refresh_public 开始 ===")
    step1_equity_slim()
    step2_equity_html_patch()
    step3_insurance()
    step4_penalty()
    step5_libs()
    step6_weekly()
    log("=== 完成，耗时 %.1fs。下一步：workbuddy_sites_deploy(directory=_public) ===" % (time.time() - t0))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
