@echo off
:: 自动导入 NeonUltimate 电源计划并设为活动（使用脚本所在目录，不依赖 D 盘）
powercfg -import "%~dp0NeonUltimate.pow" fb3077ec-9999-4f5b-a20f-422b485d9ed1
powercfg -SETACTIVE "fb3077ec-9999-4f5b-a20f-422b485d9ed1"
echo.
echo NeonUltimate power plan imported and set active.
echo 请到 控制面板-电源选项 确认已选中 NeonUltimate 计划。
pause
