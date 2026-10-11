"""
安全数据周报看板 - 本地服务器
支持静态文件服务 + 一键同步到 GitHub
"""
import http.server
import json
import os
import subprocess
import sys
import socket
import time
import posixpath
import re as _re
from urllib.parse import urlparse, unquote

# 默认端口（冷门 8421，避开 8080/8899 被 WorkBuddy/Edge/企业微信等进程抢占或阻塞）
PORT = 8421
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ===== 安全权益看板 只读暴露（2026-09-26 新增）=====
# 仅做「读取」：把交通安全分组里的安全权益看板及其 data.js 透出给周报看板 iframe，
# 绝不写入原工作台任何数据。带路径穿越防护。
TRAFFIC_BOARD_DIR = r"D:\兴达数据库\交通安全行为看板"
TRAFFIC_LIBS_DIR = r"D:\兴达数据库\_libs"

# 站维度精简版 data.js（2026-09-26）：周报板内嵌安全权益看板只展示站维度，
# 不加载全量骑手明细（RIDERS/SPEED_RIDER_ROWS 置空，体积 20MB -> <1MB）。
# 由 build_equity_slim.js 生成；data.js 每日更新后自动重新生成（按 mtime 判断）。
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
TRAFFIC_DATA_JS = os.path.join(TRAFFIC_BOARD_DIR, "data.js")
EQUITY_SLIM_JS = os.path.join(DATA_DIR, "equity_slim_data.js")
EQUITY_SLIM_BUILDER = os.path.join(PROJECT_DIR, "build_equity_slim.js")

# 护航服装数据源（36MB data_excluded.js）：评级看板工装/美团工服列依赖它。
# 真实目录在 D:\兴达数据库\护航服装，不在交通安全看板目录下，单独映射只读透出并缓存。
HUHU_FU_DIR = r"D:\兴达数据库\护航服装"

# 保险赔付补贴监控（保险分组）只读暴露（2026-09-27 新增）
# 周报看板「保险赔付补贴监控」Tab 实时对接工作台保险分组真身 + 其最新数据文件。
# 仅只读：把 D:\兴达数据库\骑手保障补贴 透出到 /insurance-live/，绝不写入工作台任何数据。
INSURANCE_DIR = r"D:\兴达数据库\骑手保障补贴"
INSURANCE_V3 = "专送合作商骑手保障补贴考核看板_2026_V3.html"

# 履约达成处罚周度（履约项目看板）只读透出（2026-09-27 新增）
# 把 D:\兴达数据库\履约项目\penalty_weekly.js 透出给周报看板，绝不改写原工作台任何文件。
PENALTY_PROJECT_DIR = r"D:\兴达数据库\履约项目"
PENALTY_WEEKLY_JS = "penalty_weekly.js"
# 履约项目看板整页嵌入：页面 HTML + 其引用的数据 js 白名单（与 <script src> 一一对应）
PENALTY_BOARD_HTML = "兴达履约项目看板.html"
PENALTY_JS_WHITELIST = {
    "penalty_weekly.js", "penalty_monthly.js", "box_rider_data.js", "data.js",
    "inspection_data.js", "inspection_daily_data.js", "knife_rider_data.js",
    "morning_review_data.js", "充换电血压_data.js",
}


def _find_node():
    import shutil
    p = shutil.which("node")
    if p:
        return p
    for cand in (
        r"C:\nodejs\node-v20.19.2-win-x64\node.exe",
        r"C:\Users\牛艳朝\.workbuddy\binaries\node\versions\22.22.2-3\node.exe",
    ):
        if os.path.isfile(cand):
            return cand
    return None


def _ensure_equity_slim():
    """保证站维度精简 data.js 存在且比源 data.js / 护航服装数据新；返回 True 表示可用。"""
    try:
        if not os.path.isfile(TRAFFIC_DATA_JS):
            return False
        src_mt = os.path.getmtime(TRAFFIC_DATA_JS)
        # 护航服装 data_excluded.js 也参与 RATING_CLOTHING_ROWS 聚合，mtime 一并纳入重建判断
        escort_js = os.path.join(HUHU_FU_DIR, "data_excluded.js")
        if os.path.isfile(escort_js):
            src_mt = max(src_mt, os.path.getmtime(escort_js))
        if os.path.isfile(EQUITY_SLIM_JS) and os.path.getmtime(EQUITY_SLIM_JS) >= src_mt:
            return True
        node = _find_node()
        if not node or not os.path.isfile(EQUITY_SLIM_BUILDER):
            return False
        # 先写到临时文件再原子替换，避免生成中途被请求读到半截
        tmp = EQUITY_SLIM_JS + ".tmp"
        r = subprocess.run(
            [node, EQUITY_SLIM_BUILDER, TRAFFIC_DATA_JS, tmp, escort_js],
            capture_output=True, timeout=120,
            creationflags=0x08000000,  # CREATE_NO_WINDOW：pythonw 环境下防止弹黑窗
        )
        if r.returncode != 0 or not os.path.isfile(tmp):
            return False
        os.replace(tmp, EQUITY_SLIM_JS)
        return True
    except Exception:
        return False


def get_local_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def find_git():
    """查找 Git 可执行文件路径"""
    candidates = [
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files (x86)\Git\bin\git.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Git\bin\git.exe"),
        "git"  # fallback to PATH
    ]
    for path in candidates:
        if os.path.isfile(path) or (path == "git" and shutil.which("git")):
            return path
    return None


def sync_to_github():
    """执行 git add / commit / push"""
    import shutil
    project_dir = os.path.dirname(os.path.abspath(__file__))
    git_exe = find_git()
    if not git_exe:
        return False, "未找到 Git，请确认 Git 已安装"

    # Ensure Git bin directory is in PATH for subprocess
    env = os.environ.copy()
    git_dir = os.path.dirname(git_exe)
    if git_dir and os.path.isdir(git_dir):
        env["PATH"] = git_dir + os.pathsep + env.get("PATH", "")

    import time
    # CREATE_NO_WINDOW：8421 由 pythonw（无控制台）启动时，子进程 git.exe 会被
    # Windows 分配新控制台并弹出黑窗口（Windows Terminal 接管）。必须显式禁止建窗。
    NO_WINDOW = 0x08000000
    try:
        subprocess.run([git_exe, "add", "-A"], cwd=project_dir, capture_output=True, timeout=10, env=env,
                       creationflags=NO_WINDOW)
        subprocess.run(
            [git_exe, "commit", "-m", f"数据同步 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"],
            cwd=project_dir, capture_output=True, timeout=10, env=env, creationflags=NO_WINDOW
        )
        # 重试最多3次 push，GitHub 网络不稳定
        last_error = ""
        for attempt in range(3):
            try:
                result = subprocess.run(
                    [git_exe, "push", "origin", "main"],
                    cwd=project_dir, capture_output=True, timeout=60, text=True, env=env,
                    creationflags=NO_WINDOW
                )
                if result.returncode == 0:
                    return True, "同步成功"
                last_error = result.stderr.strip() or "推送失败"
            except subprocess.TimeoutExpired:
                last_error = "推送超时"
            if attempt < 2:
                time.sleep(5)
        return False, last_error
    except FileNotFoundError:
        return False, "未找到 Git，请确认 Git 已安装"


class SyncHandler(http.server.SimpleHTTPRequestHandler):
    """自定义 HTTP 请求处理器"""

    # ── 2026-09-27 新增：全站统一注入 Access-Control-Allow-Origin（去重，不会重复发两次）。
    #    用途：履约项目看板（8777/file:// 打开）点周度罚款/驳回数值时，跨域拉取本服务
    #    /data/*.json 源明细；嵌入 8421 的 iframe 走同源不受影响。只加响应头，不改任何业务逻辑。
    def send_response(self, code, message=None):
        self._acao_sent = False
        super().send_response(code, message)

    def send_header(self, keyword, value):
        if str(keyword).lower() == "access-control-allow-origin":
            if getattr(self, "_acao_sent", False):
                return
            self._acao_sent = True
        super().send_header(keyword, value)

    def end_headers(self):
        # 注意：这里不能提前置 _acao_sent=True，否则下方 send_header 会被去重判断当成
        # 「已发过」直接 return，导致头永远写不出去（2026-09-27 踩坑）。置位交给 send_header。
        if not getattr(self, "_acao_sent", False):
            self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/sync":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body)

                count = 0
                for filename, content in data.items():
                    if filename.endswith(".json"):
                        filepath = os.path.join(DATA_DIR, filename)
                        with open(filepath, "w", encoding="utf-8") as f:
                            json.dump(content, f, ensure_ascii=False)
                        count += 1

                # 同步到 GitHub
                success, msg = sync_to_github()

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                result = {
                    "status": "ok" if success else "error",
                    "message": f"已写入 {count} 个文件。" + msg,
                    "sync": msg
                }
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ===== 安全权益看板 只读暴露 =====
    def _serve_traffic_file(self, root, rel_path):
        """从 root 只读返回单个文件，带路径穿越防护；失败一律 404。"""
        rel = unquote(rel_path)  # 解码 %E5%AE%89... 之类的中文/特殊字符
        rel = rel.replace("\\", "/")
        rel = posixpath.normpath(rel)
        if rel.startswith("/") or ".." in rel.split("/") or rel in ("", "."):
            self.send_error(404, "Not Found")
            return
        full = os.path.normpath(os.path.join(root, rel))
        root_norm = os.path.normpath(root)
        if full != root_norm and not full.startswith(root_norm + os.sep):
            self.send_error(404, "Not Found")
            return
        if not os.path.isfile(full):
            self.send_error(404, "Not Found")
            return
        try:
            with open(full, "rb") as f:
                data = f.read()
        except Exception:
            self.send_error(404, "Not Found")
            return
        # 安全权益看板 HTML 内硬编码了 data.js?09-25-xxxx 版本串，浏览器会缓存导致拿不到最新数据。
        # 这里把版本串改写成带时间戳的 ?t=，配合下面的 no-store，保证每次都拉最新 data.js。
        # 同时修复两个问题：
        #   1) xlsx 库引用指向不存在的 兴达丨交通安全行为看板_files/ 文件夹（404）→ 改到真实存在的库；
        #   2) 注入 CSS 隐藏骑手维度 tab（内嵌场景只需站维度）。
        ctype = self.guess_type(full)
        if ctype == "text/html":
            ctype = "text/html; charset=utf-8"
        elif ctype in ("application/javascript", "text/javascript", None) or full.lower().endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        if full.lower().endswith(".html"):
            try:
                text = data.decode("utf-8")
                text = _re.sub(r"data\.js\?[^\"')\s>]+", "data.js?t=" + str(int(time.time())), text)
                text = _re.sub(
                    r"\.?/?兴达丨交通安全行为看板_files/xlsx\.full\.min\.js\.下载",
                    "/equity-board/xlsx.full.min.js",
                    text,
                )
                # 内嵌场景：隐藏骑手维度 tab + 标题头/tab栏/KPI卡片与大区卡片（只留筛选和站维度明细表）。
                # 注意：这是代理内存改写，D:\兴达数据库 原看板文件不受影响。
                # 同时隐藏站长评级看板的 #summary-cards-rating / #summary-cards-clothing（内嵌只看站维度明细表）。
                inject = ('<style>.tab-item[data-tab="rider"],'
                          '.tab-item[data-tab="speed-rider"]{display:none!important}'
                          '.header,.tab-bar,'
                          '#summary-cards-equity,#summary-cards-rating,#summary-cards-clothing'
                          '{display:none!important}</style>')
                if "<head>" in text:
                    text = text.replace("<head>", "<head>" + inject, 1)
                else:
                    text = inject + text
                data = text.encode("utf-8")
            except Exception:
                pass
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_slim_data_js(self):
        """返回站维度精简版 data.js（no-store，保证数据更新后立即可见）。"""
        try:
            with open(EQUITY_SLIM_JS, "rb") as f:
                data = f.read()
        except Exception:
            self.send_error(404, "Not Found")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_cached_file(self, root, rel_path):
        """只读返回单个文件（不改写），带长缓存；用于体积大、几乎不变的文件（如 36MB 的 data_excluded.js）。"""
        rel = unquote(rel_path).replace("\\", "/")
        rel = posixpath.normpath(rel)
        if rel.startswith("/") or ".." in rel.split("/") or rel in ("", "."):
            self.send_error(404, "Not Found")
            return
        full = os.path.normpath(os.path.join(root, rel))
        root_norm = os.path.normpath(root)
        if full != root_norm and not full.startswith(root_norm + os.sep):
            self.send_error(404, "Not Found")
            return
        if not os.path.isfile(full):
            self.send_error(404, "Not Found")
            return
        try:
            with open(full, "rb") as f:
                data = f.read()
        except Exception:
            self.send_error(404, "Not Found")
            return
        ctype = self.guess_type(full)
        if full.lower().endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        elif ctype in (None,):
            ctype = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _serve_nostore_file(self, root, rel_path):
        """只读返回单个文件，no-store（保证每次拉最新），带路径穿越防护；失败一律 404。"""
        rel = unquote(rel_path).replace("\\", "/")
        rel = posixpath.normpath(rel)
        if rel.startswith("/") or ".." in rel.split("/") or rel in ("", "."):
            self.send_error(404, "Not Found")
            return
        full = os.path.normpath(os.path.join(root, rel))
        root_norm = os.path.normpath(root)
        if full != root_norm and not full.startswith(root_norm + os.sep):
            self.send_error(404, "Not Found")
            return
        if not os.path.isfile(full):
            self.send_error(404, "Not Found")
            return
        try:
            with open(full, "rb") as f:
                data = f.read()
        except Exception:
            self.send_error(404, "Not Found")
            return
        ctype = self.guess_type(full)
        if full.lower().endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        elif full.lower().endswith(".html"):
            ctype = "text/html; charset=utf-8"
        elif ctype in (None,):
            ctype = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_penalty_board(self):
        """履约项目看板整页只读透出（内存改写，原文件不动）：
        1) 绝对路径资源改写到本服务路由（履约项目 js → /penalty-board/<name> 白名单；
           交通安全 data.js → /equity-board/data.js 站维度精简版；_libs → /_libs/）；
        2) 内嵌场景隐藏顶部导航/主tab栏/iframe内KPI卡片（周报看板 complianceTotal 已展示 KPI），
           并自动切到 履约安全检查 → 履约达成处罚-周度 子面板。"""
        full = os.path.join(PENALTY_PROJECT_DIR, PENALTY_BOARD_HTML)
        try:
            with open(full, "rb") as f:
                text = f.read().decode("utf-8")
        except Exception:
            self.send_error(404)
            return
        text = _re.sub(r'src="D:/兴达数据库/履约项目/([^"]+\.js)"',
                       lambda m: 'src="/penalty-board/%s"' % m.group(1), text)
        text = text.replace('src="D:/兴达数据库/交通安全行为看板/data.js"',
                            'src="/equity-board/data.js"')
        text = _re.sub(r'src="\.\./_libs/([^"]+)"', r'src="/_libs/\1"', text)
        inject = (
            '<style>.header,.tab-bar,#summary-cards-penalty-week,#summary-cards-penalty-month'
            '{display:none!important}'
            '#panel-safety > .sub-tab-bar{display:none!important}</style>'
            # 2026-10-11 加固：switchTab 与 switchSafetySub 拆成独立 try（此前 switchTab 渲染
            # 巡检子页读缺失数据抛错会把整个 try 块打断，导致永远停在默认的巡检平台子页）；
            # 并在切换后校验实际激活子页，未落到 penalty-week 则有限次重试。
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
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        # 安全权益看板（交通安全分组）只读透出
        if path in ("/equity-board", "/equity-board/"):
            self._serve_traffic_file(TRAFFIC_BOARD_DIR, "安全权益看板.html")
            return
        if path.startswith("/equity-board/"):
            rel = path[len("/equity-board/"):]
            rel_dec = unquote(rel).replace("\\", "/")
            # ASCII 别名（2026-09-27）：主页 iframe 改用 ASCII 文件名，公网静态托管直接命中同名文件；
            # 本地则映射回 D:\兴达数据库 原中文名文件，两边同路径、行为一致。
            if rel_dec == "index.html":
                self._serve_traffic_file(TRAFFIC_BOARD_DIR, "安全权益看板.html")
                return
            if rel_dec == "rating.html":
                self._serve_traffic_file(TRAFFIC_BOARD_DIR, "站长安全评级看板.html")
                return
            # 护航服装数据源（36MB），应从其真实目录透出（交通安全看板目录下无此子目录）
            if rel_dec.startswith("护航服装/"):
                self._serve_cached_file(HUHU_FU_DIR, rel[len("护航服装/"):])
                return
            # data.js 走站维度精简版（不含全量骑手明细）；生成失败则回退原版
            if rel_dec == "data.js":
                if _ensure_equity_slim() and os.path.isfile(EQUITY_SLIM_JS):
                    self._serve_slim_data_js()
                    return
            # 项目目录兜底：公网静态托管所需的 ASCII 落库文件（escort_slim.js / xlsx 等）
            # 本地也能直接命中，保证本地与公网看到的内容一致
            local_eq = os.path.join(PROJECT_DIR, "equity-board", rel_dec)
            if os.path.isfile(local_eq) and not rel_dec.endswith(".html"):
                self._serve_nostore_file(os.path.join(PROJECT_DIR, "equity-board"), rel_dec)
                return
            self._serve_traffic_file(TRAFFIC_BOARD_DIR, rel)
            return
        # 护航服装数据源（36MB data_excluded.js）：只读透出 + 缓存，避免每次重传
        if path.startswith("/护航服装/"):
            self._serve_cached_file(HUHU_FU_DIR, path[len("/护航服装/"):])
            return
        # 保险赔付补贴监控（保险分组）只读透出：实时加载工作台真身 + 最新数据
        if path in ("/insurance-live", "/insurance-live/"):
            self._serve_nostore_file(INSURANCE_DIR, INSURANCE_V3)
            return
        if path.startswith("/insurance-live/"):
            self._serve_nostore_file(INSURANCE_DIR, path[len("/insurance-live/"):])
            return
        # 履约达成处罚周度（履约项目看板）只读透出：绝不改写原工作台任何文件
        if path in ("/penalty-board", "/penalty-board/"):
            self._serve_penalty_board()
            return
        if path.startswith("/penalty-board/"):
            rel = unquote(path[len("/penalty-board/"):])
            # 仅白名单数据 js 可透出，防目录穿越
            if rel in PENALTY_JS_WHITELIST:
                self._serve_nostore_file(PENALTY_PROJECT_DIR, rel)
                return
            self.send_error(404)
            return
        # 共享前端库（html2canvas 等导出用），只读透出
        if path.startswith("/_libs/"):
            self._serve_traffic_file(TRAFFIC_LIBS_DIR, path[len("/_libs/"):])
            return
        # 首页 HTML 加 no-store：保证每次打开都拉最新（改完即时生效，满足「实时更新」）
        if path in ('/', '/index.html', '/安全数据周报看板.html'):
            rel = 'index.html' if path in ('/', '/index.html') else '安全数据周报看板.html'
            self._serve_nostore_file(PROJECT_DIR, rel)
            return
        # 其余走原有静态服务（本项目的 data/ 等）
        super().do_GET()


# ===== 8770 M盘BI注入服务看门狗（2026-10-06）=====
# 保险V3看板「从M盘更新BI数据」依赖 127.0.0.1:8770 注入服务。该服务此前仅靠
# HKCU Run/双击bat 拉起，掉线后无人兜底。8421 是开机自启的持久进程，由它每60s
# 探测 8770，掉线即以 DETACHED+DEVNULL 拉起（子进程随 8421 常驻，不被会话回收）。
_MBI_PYW = r"D:\兴达数据库\py_env\Scripts\pythonw.exe"
_MBI_SRV = r"D:\兴达数据库\bi_insurance\_bi_m_service.py"


def _mbi_alive():
    """探测 8770 是否有进程监听。"""
    try:
        s = socket.create_connection(("127.0.0.1", 8770), timeout=1.5)
        s.close()
        return True
    except OSError:
        return False


def _mbi_start():
    """拉起 8770 注入服务（DETACHED_PROCESS|NEW_GROUP|NO_WINDOW + DEVNULL 三件套）。"""
    if not (os.path.isfile(_MBI_PYW) and os.path.isfile(_MBI_SRV)):
        return
    try:
        flags = 0x00000008 | 0x00000200 | 0x08000000
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        subprocess.Popen([_MBI_PYW, _MBI_SRV], cwd=os.path.dirname(_MBI_SRV),
                         creationflags=flags, startupinfo=si,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        print("[watchdog] 8770 掉线，已重新拉起 M盘BI注入服务")
    except Exception as e:
        print("[watchdog] 拉起 8770 失败: %r" % e)


def _mbi_watchdog():
    time.sleep(20)  # 等本服务先稳定
    while True:
        try:
            if not _mbi_alive():
                _mbi_start()
        except Exception:
            pass
        time.sleep(60)


# ===== 可视化大屏数据自动重建（2026-10-06 实时化）=====
# 上游任一源文件（交通安全/履约/护航/地图/理赔/BI latest/保费/data_center）更新后，
# 60 秒内自动跑 node build_screen_data.js 重建 _大屏数据.js；
# 大屏页面自身每 60s 轮询拉取新数据热渲染 → 形成实时闭环。
# 只读源文件 + 只写大屏自己的 _大屏数据.js，不碰 8768/定时任务/抓取链路。
_XD_ROOT     = r"D:\兴达数据库"
_SCREEN_DIR  = os.path.join(_XD_ROOT, "可视化大屏")
_SCREEN_OUT  = os.path.join(_SCREEN_DIR, "_大屏数据.js")
_SCREEN_SRCS = [
    os.path.join(_XD_ROOT, "交通安全行为看板", "data.js"),
    os.path.join(_XD_ROOT, "履约项目", "data.js"),
    os.path.join(_XD_ROOT, "护航服装", "data.js"),
    os.path.join(_XD_ROOT, "全国站点地图", "data.js"),
    os.path.join(_XD_ROOT, "美团保险", "insurance_data.js"),
    os.path.join(_XD_ROOT, "骑手保障补贴", "bi_data", "latest.json"),
    os.path.join(_XD_ROOT, "bi_insurance", "premium_latest.json"),
    os.path.join(_XD_ROOT, "data_center.json"),
    # ---- 第二屏（项目总览）新增源 ----
    os.path.join(_XD_ROOT, "在职骑手详情", "health_cert_data.js"),
    os.path.join(_XD_ROOT, "履约项目", "充换电血压_data.js"),
    os.path.join(_XD_ROOT, "履约项目", "box_rider_data.js"),
    os.path.join(_XD_ROOT, "履约项目", "knife_rider_data.js"),
    os.path.join(_XD_ROOT, "履约项目", "morning_review_data.js"),
    os.path.join(_XD_ROOT, "履约项目", "penalty_weekly.js"),
    os.path.join(_XD_ROOT, "110工单", "110_data.js"),
    os.path.join(_XD_ROOT, "考核文件库", "checkup_files_data.js"),
]
_SCREEN_STATE = {"fail_until": 0.0}
_NODE_CANDIDATES = [
    r"C:\nodejs\node-v20.19.2-win-x64\node.exe",
]


def _find_node():
    for p in _NODE_CANDIDATES:
        if os.path.isfile(p):
            return p
    try:
        import glob as _glob
        hits = _glob.glob(os.path.join(os.path.expanduser("~"), ".workbuddy",
                                       "binaries", "node", "versions", "*", "node.exe"))
        if hits:
            return sorted(hits)[-1]
    except Exception:
        pass
    return None


def _screen_srcs_fresh():
    """上游是否有比 _大屏数据.js 更新的源文件；返回 (bool, newest_mtime)。"""
    try:
        out_m = os.path.getmtime(_SCREEN_OUT)
    except OSError:
        return True, 0.0
    newest = 0.0
    for f in _SCREEN_SRCS:
        try:
            m = os.path.getmtime(f)
        except OSError:
            continue
        newest = max(newest, m)
    return newest > out_m + 2, newest  # 2s 容差


def _screen_rebuild():
    node = _find_node()
    if not node:
        return
    try:
        flags = 0x08000000  # CREATE_NO_WINDOW
        r = subprocess.run([node, "build_screen_data.js"], cwd=_SCREEN_DIR,
                           capture_output=True, text=True, timeout=180,
                           creationflags=flags)
        if r.returncode == 0:
            print("[screen] 大屏数据已自动重建: " + (r.stdout or "").strip().splitlines()[-1][:120])
        else:
            _SCREEN_STATE["fail_until"] = time.time() + 300
            print("[screen] 重建失败(退出码 %s)，5 分钟后再试: %s" % (r.returncode, (r.stderr or "")[:150]))
    except Exception as e:
        _SCREEN_STATE["fail_until"] = time.time() + 300
        print("[screen] 重建异常: %r" % e)


def _screen_watchdog():
    time.sleep(35)  # 错开 8770 看门狗首拍
    while True:
        try:
            if time.time() >= _SCREEN_STATE["fail_until"]:
                fresh, _ = _screen_srcs_fresh()
                if fresh:
                    _screen_rebuild()
        except Exception:
            pass
        time.sleep(60)


if __name__ == "__main__":
    # 端口可用参数覆盖：python server.py [lan] [端口]，默认 8421
    # 使用 ThreadingHTTPServer 支持多连接并发（避免被 WorkBuddy/Edge 等长连接阻塞）
    import threading
    threading.Thread(target=_mbi_watchdog, daemon=True).start()
    threading.Thread(target=_screen_watchdog, daemon=True).start()
    import re
    port = 8421
    bind_host = "127.0.0.1"
    for arg in sys.argv[1:]:
        if arg.lower() == "lan":
            bind_host = "0.0.0.0"
        elif re.fullmatch(r"\d+", arg):
            port = int(arg)
    PORT = port
    local_ip = get_local_ip()
    print(f"\n{'='*50}")
    print(f"  安全数据周报看板 - 本地服务器")
    print(f"{'='*50}")
    print(f"\n  本机访问:   http://localhost:{PORT}")
    if bind_host == "0.0.0.0":
        print(f"  局域网访问: http://{local_ip}:{PORT}")
    else:
        print(f"  (当前仅本机访问，局域网开放请运行: python server.py lan)")
    print(f"\n  [同步到公网] 按钮可一键推送 GitHub")
    print(f"  按 Ctrl+C 停止服务器")
    print(f"{'='*50}\n")

    # 使用 ThreadingHTTPServer 支持多连接并发（避免单线程被长连接阻塞导致其他浏览器被拒）
    server = http.server.ThreadingHTTPServer((bind_host, PORT), SyncHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止。")
        server.server_close()
