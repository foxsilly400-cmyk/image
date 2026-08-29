@echo off
REM 一键放行 6008 端口（手机连稳定网关用），需要管理员权限，会弹 UAC 确认
>nul 2>&1 net session || (
  echo 请求管理员权限...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
netsh advfirewall firewall add rule name="stable_gateway_6008" dir=in action=allow protocol=TCP localport=6008 profile=private,domain
echo.
echo 完成。手机访问 http://192.168.1.21:6008
pause
