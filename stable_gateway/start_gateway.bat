@echo off
REM 稳定网关启动脚本（固定网址 http://127.0.0.1:6008 -> 当前实例）
cd /d %~dp0
start "" /min node gateway.js
echo stable gateway started on http://127.0.0.1:6008
