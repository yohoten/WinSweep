@echo off
title 关闭 HPET 与延迟优化（bcdedit）
echo ============================================
echo   关闭 HPET 与延迟优化（修改启动配置）
echo   高危操作，建议先创建系统还原点
echo ============================================
echo.
set /p ok=确认继续？[Y/N]:
if /i not "%ok%"=="y" exit /b
echo 正在写入 bcdedit 配置...
bcdedit /set useplatformclock no
bcdedit /set disabledynamictick yes
bcdedit /set useplatformtick no
bcdedit /set tscsyncpolicy default
bcdedit /set nx AlwaysOff
bcdedit /set hypervisorlaunchtype off
bcdedit /set hypervisoriommupolicy Disable
bcdedit /set vsmlaunchtype Off
bcdedit /set vm No
bcdedit /set MSI Default
bcdedit /set isolatedcontext No
bcdedit /set tpmbootentropy ForceDisable
bcdedit /set disableelamdrivers Yes
bcdedit /set nointegritychecks on
bcdedit /set forcelegacyplatform No
bcdedit /event off
bcdedit /ems off
bcdedit /set ems off
bcdedit /timeout 1
echo.
echo [完成] 请重启电脑生效。
echo [还原] 将上述 no/off 项改回 yes/on，或执行 bcdedit /deletevalue 删除。
pause
