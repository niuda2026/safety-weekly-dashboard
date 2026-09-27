' ============================================
'  看板服务 - 静默后台启动器
'  无黑色窗口，后台运行 python server.py (端口8421)
'  由 autostart.bat 或开机自启调用
' ============================================
Option Explicit
Dim fso, shell, wd, pythonPath, serverPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' 定位到本脚本所在目录
wd = fso.GetParentFolderName(WScript.ScriptFullName)

' 使用托管 Python 或系统 python，优先 PATH 中的 python
' 隐藏窗口运行 python server.py
shell.CurrentDirectory = wd

' 用隐藏窗口启动（0 = 隐藏）
shell.Run "cmd /c python server.py", 0, False

WScript.Sleep 100
Set shell = Nothing
Set fso = Nothing
