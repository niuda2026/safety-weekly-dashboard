@echo off
chcp 65001 >nul
echo ============================================
echo   安全数据周报看板 - 本地服务器
echo ============================================
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set ip=%%a
    set ip=!ip:~1!
    goto :found
)
:found
echo   局域网访问地址: http://!ip!:8080
echo   本机访问地址:   http://localhost:8080
echo.
echo   按 Ctrl+C 停止服务器
echo ============================================
echo.
cd /d "C:\Users\牛艳朝\Desktop\安全数据周报看板"
python -m http.server 8080 --bind 0.0.0.0
pause
