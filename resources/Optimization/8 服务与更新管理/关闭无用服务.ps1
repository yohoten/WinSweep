# 关闭无用系统服务（管理员权限运行）
# 用法：右键此文件 → 使用 PowerShell 运行；或在 SysCleanTemp Pro 中一键执行
$ErrorActionPreference = "SilentlyContinue"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "需要以管理员身份运行！" -ForegroundColor Red
    Read-Host "按回车退出"; exit
}

$services = @(
    # 系统服务
    "Beep", "diagsvc", "DPS", "WdiServiceHost", "WdiSystemHost",
    "DiagTrack", "MapsBroker", "autotimesvc", "DusmSvc", "tzautoupdate",
    "WSearch", "PcaSvc", "DsmSvc", "WpcMonSvc", "SEMgrSvc",
    "PimIndexMaintenanceSvc", "Sysmain", "NvTelemetryContainer",
    # Hyper-V 服务
    "vmicguestinterface", "vmicheartbeat", "vmickvpexchange", "vmicrdv",
    "vmicshutdown", "vmictimesync", "vmicvmsession", "vmicvss",
    # 其他
    "PhoneSvc", "RetailDemo", "wercplsupport", "FontCache", "FontCache3.0.0.0"
)

Write-Host "即将禁用 $($services.Count) 个服务：$($services -join ', ')" -ForegroundColor Yellow
$ok = Read-Host "确认禁用？[Y/N]"
if ($ok -ne "y" -and $ok -ne "Y") { Write-Host "已取消。"; exit }

foreach ($service in $services) {
    Set-Service -Name $service -StartupType Disabled -ErrorAction SilentlyContinue
    & sc.exe config $service error= ignore | Out-Null
    Write-Host "  已禁用: $service"
}
Write-Host "完成。部分服务重启后生效。" -ForegroundColor Green
Write-Host "还原：将对应服务 StartType 改回 Manual/Automatic 即可。" -ForegroundColor Yellow
Read-Host "按回车退出"
