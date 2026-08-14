@echo off
:: 调用同目录下的 XHCI-IMOD-Interval.ps1（不再依赖 D 盘）
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0XHCI-IMOD-Interval.ps1"
