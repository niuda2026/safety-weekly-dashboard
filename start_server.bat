@echo off
chcp 65001 >nul
REM 自动定位到本脚本所在目录（不再写死路径，拷贝到任意位置都可用）
cd /d "%~dp0"
python server.py
pause
