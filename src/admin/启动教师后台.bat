@echo off
chcp 65001 >nul
title 网安教师后台 - 校园钓鱼检测
cd /d "%~dp0"

set "PYEXE=%~dp0runtime\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo  [!] 端口 5000 已被占用，正在打开浏览器...
    start http://127.0.0.1:5000
    pause
    exit /b
)

echo  ============================================
echo   校园钓鱼检测 - 网安教师后台
echo  ============================================
echo  正在启动服务，浏览器 3 秒后自动打开...
echo  关闭本窗口即可停止后台。
echo.

start "" /min cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5000"

"%PYEXE%" server.py

echo.
echo  后台服务已停止。
pause
