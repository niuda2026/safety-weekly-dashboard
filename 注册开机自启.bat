@echo off
REM 注册开机任务计划（开机后延迟 90 秒启动看板服务）
REM 用 schtasks 创建 SYSTEM 账户任务，无窗口，不依赖 WorkBuddy 会话

set "TASK_NAME=WorkBuddySafetyDashboardAutoStart"
set "PROJ=C:\Users\牛艳朝\WorkBuddy\2026-09-04-04-42-17\safety-weekly-dashboard"
set "PY=C:\Users\牛艳朝\.workbuddy\binaries\python\versions\3.13.12\python.exe"

REM 先删除同名旧任务（如果有）
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM 创建开机触发 + 延迟90秒 的任务
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PY%\" \"%PROJ%\server.py\" 8421" ^
  /sc onstart ^
  /delay 0001:30 ^
  /ru SYSTEM ^
  /rl HIGHEST ^
  /f

if %errorlevel%==0 (
  echo.
  echo   ✓ 开机自启任务已创建
  echo     任务名: %TASK_NAME%
  echo     触发: 开机后 1 分 30 秒
  echo     服务: 8421 端口
  echo.
) else (
  echo   ✗ 创建失败，请以管理员权限运行此 bat
)
pause