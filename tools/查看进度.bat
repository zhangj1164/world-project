@echo off
title 《春秋》分析进度监控
cd /d F:\Personal\world-project

:: 从 .env 读取配置
for /f "tokens=1,2 delims==" %%a in (.env) do (
    set %%a=%%b
)

python progress_watch.py
pause
