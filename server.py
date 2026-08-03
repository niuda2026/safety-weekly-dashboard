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
from urllib.parse import urlparse

PORT = 8080
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


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

    try:
        subprocess.run([git_exe, "add", "-A"], cwd=project_dir, capture_output=True, timeout=10, env=env)
        subprocess.run(
            [git_exe, "commit", "-m", f"数据同步 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"],
            cwd=project_dir, capture_output=True, timeout=10, env=env
        )
        result = subprocess.run(
            [git_exe, "push", "origin", "main"],
            cwd=project_dir, capture_output=True, timeout=30, text=True, env=env
        )
        if result.returncode == 0:
            return True, "同步成功"
        else:
            return False, result.stderr.strip() or "推送失败"
    except subprocess.TimeoutExpired:
        return False, "推送超时，请检查网络后重试"
    except FileNotFoundError:
        return False, "未找到 Git，请确认 Git 已安装"


class SyncHandler(http.server.SimpleHTTPRequestHandler):
    """自定义 HTTP 请求处理器"""

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


if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"\n{'='*50}")
    print(f"  安全数据周报看板 - 本地服务器")
    print(f"{'='*50}")
    print(f"\n  本机访问:   http://localhost:{PORT}")
    print(f"  局域网访问: http://{local_ip}:{PORT}")
    print(f"\n  [同步到公网] 按钮可一键推送 GitHub")
    print(f"  按 Ctrl+C 停止服务器")
    print(f"{'='*50}\n")

    server = http.server.HTTPServer(("0.0.0.0", PORT), SyncHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止。")
        server.server_close()
