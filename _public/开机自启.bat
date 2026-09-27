@echo off
chcp 65001 >nul
title 安全数据周报看板服务

REM 指向 WorkBuddy 新项目
set "PROJ=C:\Users\牛艳朝\WorkBuddy\2026-09-04-04-42-17\safety-weekly-dashboard"
set "PY=C:\Users\牛艳朝\.workbuddy\binaries\python\versions\3.13.12\python.exe"

cd /d "%PROJ%"

REM 已在运行则直接退出（8421 被占用说明服务在）
netstat -ano | findstr "LISTENING" | findstr ":8421" >nul
if %errorlevel%==0 goto end

REM 最小化启动
start "" /min "%PY%" server.py

:end
exit /b 0
