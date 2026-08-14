# 网络延迟优化（管理员权限运行）
$ErrorActionPreference = "Continue"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "需要以管理员身份运行！" -ForegroundColor Red
    Read-Host "按回车退出"; exit
}

Write-Host "正在设置 TCP 参数..."
$interfaceKeysPath = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
Get-ChildItem $interfaceKeysPath | ForEach-Object {
    $path = $_.PSParentPath + '\' + $_.PSChildName
    Set-ItemProperty -Path $path -Name "TCPNoDelay" -Value 1
    Set-ItemProperty -Path $path -Name "TcpAckFrequency" -Value 1
    Set-ItemProperty -Path $path -Name "TcpDelAckTicks" -Value 0
}

netsh int ipv4 set dynamicport tcp start=1025 num=64511
netsh int ipv4 set dynamicport udp start=1025 num=64511
netsh int tcp set global rss = enabled
netsh int tcp set global autotuning=experimental
netsh int tcp set supplemental template=internet congestionprovider=ctcp
netsh int tcp set supplemental template=datacenter congestionprovider=ctcp
netsh int tcp set supplemental template=compat congestionprovider=ctcp
netsh int tcp set supplemental template=datacentercustom congestionprovider=ctcp
netsh int tcp set supplemental template=internetcustom congestionprovider=ctcp
netsh int tcp set global ecncapability=enabled
netsh int tcp set global rsc=disabled
netsh winsock set autotuning on
netsh int tcp set global dca=enabled
netsh int tcp set global netdma=enabled
netsh int tcp set global timestamps=disabled

Write-Host "完成。" -ForegroundColor Green
Read-Host "按回车退出"
