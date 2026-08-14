# 内存与硬盘优化（管理员权限运行）
$ErrorActionPreference = "Continue"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "需要以管理员身份运行！" -ForegroundColor Red
    Read-Host "按回车退出"; exit
}

Write-Host "正在优化内存(MMAgent)..."
Disable-MMAgent -mc
Disable-MMAgent -PageCombining
Disable-MMAgent -ApplicationPreLaunch
Disable-MMAgent -ApplicationLaunchPrefetching
Disable-MMAgent -OperationAPI
Set-MMAgent -MaxOperationAPIFiles 8192

Write-Host "正在优化硬盘(NTFS)..."
fsutil behavior set disableencryption 1
fsutil behavior set disablefilemetadataoptimization 3
fsutil behavior set disablecompression 1
fsutil behavior set mftzone 8
fsutil behavior set memoryusage 2
fsutil behavior set quotanotify 4294967295
fsutil behavior set disable8dot3 1
fsutil behavior set disablelastaccess 1

Write-Host "完成。部分设置需重启生效。" -ForegroundColor Green
Write-Host "注意：如游戏需要 NTFS 加密，请将 disableencryption 改回 0。" -ForegroundColor Yellow
Read-Host "按回车退出"
