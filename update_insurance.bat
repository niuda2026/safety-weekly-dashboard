@echo off
chcp 65001 >nul
title 同步保险看板数据（默认只读）

REM ============================================================
REM  同步保险两块看板（保险赔付率解读 + 保险赔付补贴监控）
REM
REM  默认模式 = 纯只读复制：只从履约安全工作台【读取】文件，
REM              绝不写入、绝不改动工作台里的任何脚本和数据。
REM
REM  带参数 --recalc 才会在工作台里跑一次 monthly_archive.py
REM  （那是工作台自己的脚本，会重算 monthly_summary.js 并联动
REM   刷新 V3 内嵌数据，改动前会自动备份到 D:\兴达看板备份）。
REM  只有工作台当天已刷 data.js、但月度/V3 数字还是旧的时才用。
REM
REM  用法：
REM    update_insurance.bat            ← 平时用这个（只读，最安全）
REM    update_insurance.bat --recalc   ← 数字对不上时才用
REM
REM  跑完浏览器按 Ctrl+Shift+R 强刷看板即可。
REM ============================================================

set "RECALC=0"
if /i "%~1"=="--recalc" set "RECALC=1"
if /i "%~1"=="--重算" set "RECALC=1"

set "SRC_RATE=D:\兴达数据库\美团保险\保险赔付率解读.html"
set "SRC_MON=D:\兴达数据库\骑手保障补贴\保险赔付补贴监控.html"
set "SRC_V3=D:\兴达数据库\骑手保障补贴\专送合作商骑手保障补贴考核看板_2026_V3.html"
set "SRC_V2=D:\兴达数据库\骑手保障补贴\专送合作商骑手保障补贴考核看板.html"

set "DB=D:\兴达数据库"
set "PY_DIR=D:\兴达数据库\py_env"
set "PYTHON=C:\Users\牛艳朝\.workbuddy\binaries\python\versions\3.13.12\python.exe"

set "DST=%~dp0"

echo.
echo   模式：%RECALC%
if "%RECALC%"=="1" (echo   == 重算模式（会改动工作台 monthly_summary / V3）==) else (echo   == 只读模式（不写入工作台任何文件）==)

echo.
echo   [1/4] 同步看板 HTML（只读复制）...
if exist "%SRC_RATE%" (
    copy /Y "%SRC_RATE%" "%DST%insurance_rate_analysis.html" >nul
    echo          保险赔付率解读  OK
) else (
    echo          保险赔付率解读 源不存在，跳过
)
if exist "%SRC_MON%" (
    copy /Y "%SRC_MON%" "%DST%insurance_subsidy_monitor.html" >nul
    echo          保险赔付补贴监控外壳  OK
) else (
    echo          保险赔付补贴监控外壳 源不存在，跳过
)
if exist "%SRC_V2%" (
    copy /Y "%SRC_V2%" "%DST%insurance_subsidy_v2.html" >nul
    echo          补贴考核看板 V2  OK
) else (
    echo          补贴考核看板 V2 源不存在，跳过
)
if exist "%SRC_V3%" (
    copy /Y "%SRC_V3%" "%DST%insurance_subsidy_v3.html" >nul
    echo          补贴考核看板 V3  OK
) else (
    echo          补贴考核看板 V3 源不存在，跳过
)

echo.
echo   [2/4] 重算月度汇总...
if "%RECALC%"=="1" (
    if exist "%DB%\monthly_archive.py" (
        if exist "%PY_DIR%\python.exe" (
            "%PY_DIR%\python.exe" "%DB%\monthly_archive.py" --input "D:\兴达数据库\交通安全行为看板\data.js" --out "D:\兴达数据库\交通安全行为看板\monthly_summary.js" --month 2026-09 --force 2>&1 | findstr /C:"months:" /C:"归档" /C:"ERROR" /C:"异常"
        ) else (
            echo          未找到 D:\兴达数据库\py_env\python.exe，跳过重算
        )
    ) else (
        echo          未找到 monthly_archive.py，跳过
    )
) else (
    echo          只读模式，已跳过（工作台数据保持原样）
    echo          若看板数字比工作台旧，请改用：update_insurance.bat --recalc
)

echo.
echo   [3/4] 复制数据文件（只读）...
if exist "%DB%\骑手保障补贴\v3_data.js" (
    copy /Y "%DB%\骑手保障补贴\v3_data.js" "%DST%v3_data.js" >nul
    echo          v3_data.js 已复制
) else (
    echo          v3_data.js 不存在
)
if exist "%DB%\骑手保障补贴\monthly_summary.js" (
    copy /Y "%DB%\交通安全行为看板\monthly_summary.js" "%DST%monthly_summary.js" >nul
    echo          monthly_summary.js 已复制
) else (
    echo          monthly_summary.js 不存在
)
if exist "%DB%\骑手保障补贴\bi_data\latest.json" (
    if not exist "%DST%bi_data" mkdir "%DST%bi_data"
    copy /Y "%DB%\骑手保障补贴\bi_data\latest.json" "%DST%bi_data\latest.json" >nul
    copy /Y "%DB%\骑手保障补贴\bi_data\latest.json" "%DST%latest.json" >nul
    echo          bi_data\latest.json 已复制
) else (
    echo          bi_data\latest.json 不存在
)
if exist "%DB%\bi_insurance\premium_latest.json" (
    copy /Y "%DB%\bi_insurance\premium_latest.json" "%DST%premium_latest.json" >nul
    echo          premium_latest.json 已复制
) else (
    echo          premium_latest.json 不存在
)

echo.
echo   [4/4] 修正内部文件引用（中文 -^> 英文，只改本目录副本）...
cd /d "%DST%"
"%PYTHON%" -c "import io;p='insurance_subsidy_monitor.html';s=io.open(p,encoding='utf-8').read();s=s.replace('专送合作商骑手保障补贴考核看板_2026_V3.html','insurance_subsidy_v3.html').replace('专送合作商骑手保障补贴考核看板.html','insurance_subsidy_v2.html');io.open(p,'w',encoding='utf-8').write(s);print('          外壳引用已修正')" 2>nul
if errorlevel 1 echo          修正失败（手动改 insurance_subsidy_monitor.html 即可）

echo.
netstat -ano | findstr "LISTENING" | findstr ":8421" >nul
if %errorlevel%==0 (
    echo   服务在跑，请去浏览器按 Ctrl+Shift+R 强刷看板
) else (
    echo   服务未启动，请双击 start_server.bat 启动
)

echo.
echo   完成！
echo.
pause
