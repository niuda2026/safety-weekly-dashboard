@echo off
chcp 65001 >nul
cd /d "C:\Users\牛艳朝\Desktop\安全数据周报看板"

echo ============================================
echo   安全数据周报看板 - 同步到公网
echo ============================================
echo.
echo   正在推送最新数据到 GitHub Pages...
echo.

REM 刷新环境变量以找到 Git
set "PATH=%PATH%;C:\Program Files\Git\bin;C:\Program Files\Git\cmd"

git add -A
git commit -m "数据更新 %date% %time%"
git push origin main

echo.
echo ============================================
echo   同步完成！
echo   公网地址: https://niuda2026.github.io/safety-weekly-dashboard/
echo   （等待 1-2 分钟后刷新即可看到最新数据）
echo ============================================
echo.
pause
