@echo off
title 彻底关闭 Windows Defender
echo ============================================
echo   彻底关闭 Windows Defender（可选，不可逆）
echo ============================================
echo.
echo [重要] 使用前请先在「Windows 安全中心」操作：
echo   1. 关闭 实时保护
echo   2. 关闭 篡改防护(Tamper Protection)
echo.
set /p ok=是否已关闭实时保护与篡改防护？[Y/N]:
if /i not "%ok%"=="y" exit /b
echo.
echo 正在停止并禁用 Defender 服务...
sc stop WinDefend >nul 2>&1
sc config WinDefend start= disabled
echo 正在写入 Defender 禁用策略...
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection" /v DisableRealtimeMonitoring /t REG_DWORD /d 1 /f
echo.
echo [完成] 请重启电脑生效。
echo [还原] 删除上述两条注册表项，并将 WinDefend 服务改回 automatic。
pause
