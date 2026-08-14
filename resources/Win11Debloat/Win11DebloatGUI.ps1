# Win11Debloat 中文版 - 图形界面前端（Windows 7 Aero 风格）
# 勾选要执行的优化项，点击「开始执行」后调用核心脚本 Win11Debloat.ps1 并实时显示日志。
# 请通过 Run-GUI.bat 以管理员身份启动本脚本。

# 检查是否以管理员身份运行
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    [System.Windows.Forms.MessageBox]::Show("需要以管理员身份运行！`n请通过 Run-GUI.bat 启动，或在 PowerShell 中右键以管理员身份运行。", "Win11Debloat 中文版", "OK", "Warning") | Out-Null
    exit
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# ---------- DWM 支持：将系统标题栏染成 Aero 深蓝（模拟 Win7 Aero 玻璃标题栏） ----------
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win7Dwm {
    [DllImport("dwmapi.dll", PreserveSig = true)]
    public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);
}
"@

# ---------- Win7 Aero 调色板 ----------
$script:C = @{
    AeroTitle    = [System.Drawing.Color]::FromArgb(36, 80, 125)    # 深 Aero 蓝（横幅顶部）
    AeroTitle2   = [System.Drawing.Color]::FromArgb(74, 132, 181)   # 浅 Aero 蓝（横幅底部渐变）
    AeroLink     = [System.Drawing.Color]::FromArgb(120, 170, 215)  # 横幅内的亮蓝（副标题）
    WindowBg     = [System.Drawing.Color]::FromArgb(232, 240, 250)  # 内容区浅蓝
    GroupBg      = [System.Drawing.Color]::FromArgb(244, 248, 253)  # 分组框底色
    GroupBorder  = [System.Drawing.Color]::FromArgb(170, 190, 215)  # 分组框浅蓝边框
    AeroText     = [System.Drawing.Color]::FromArgb(31, 74, 122)    # 深蓝文字
    BtnMainBg    = [System.Drawing.Color]::FromArgb(59, 110, 165)   # 主按钮 Aero 蓝
    BtnMainHov   = [System.Drawing.Color]::FromArgb(78, 132, 181)   # 主按钮悬停
    BtnMainEdge  = [System.Drawing.Color]::FromArgb(47, 90, 138)    # 主按钮边线
    BtnBg        = [System.Drawing.Color]::FromArgb(245, 245, 245)  # 普通按钮灰白
    BtnHov       = [System.Drawing.Color]::FromArgb(222, 235, 247)  # 普通按钮悬停浅蓝
    BtnEdge      = [System.Drawing.Color]::FromArgb(150, 150, 150)  # 普通按钮边线
    BtnText      = [System.Drawing.Color]::FromArgb(31, 74, 122)    # 按钮文字深蓝
}

# ---------- 全局状态 ----------
$script:customApps = $false          # 是否已通过应用选择器保存自定义应用列表
$script:proc = $null                 # 核心脚本子进程
$script:timer = $null
$script:outFile = ""
$script:errFile = ""
$script:lastRead = ""
$script:logBox = $null

# ---------- 构建窗体 ----------
$form = New-Object System.Windows.Forms.Form
$form.Text = "Win11Debloat 中文版 - 系统预装清理"
$form.ClientSize = New-Object System.Drawing.Size(632, 814)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = $script:C.WindowBg
$form.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)

# ===== 顶部 Aero 玻璃横幅（模拟 Win7 Aero 渐变标题栏） =====
$banner = New-Object System.Windows.Forms.Panel
$banner.Location = New-Object System.Drawing.Point(0, 0)
$banner.Size = New-Object System.Drawing.Size(632, 74)
$banner.Anchor = [System.Windows.Forms.AnchorStyles]::Top -bor [System.Windows.Forms.AnchorStyles]::Left -bor [System.Windows.Forms.AnchorStyles]::Right
$banner.Add_Paint({
    param($s, $e)
    $rect = New-Object System.Drawing.Rectangle(0, 0, $banner.Width, $banner.Height)
    $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($rect, $script:C.AeroTitle, $script:C.AeroTitle2, 90)
    $e.Graphics.FillRectangle($brush, $rect)
    $brush.Dispose()
    # 底部一条亮线（Aero 玻璃边缘高光）
    $pen = New-Object System.Drawing.Pen($script:C.AeroLink, 1)
    $e.Graphics.DrawLine($pen, 0, $banner.Height - 1, $banner.Width, $banner.Height - 1)
    $pen.Dispose()
})
$form.Controls.Add($banner)

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Text = "Win11Debloat 系统预装清理工具"
$lblTitle.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 16, [System.Drawing.FontStyle]::Bold)
$lblTitle.ForeColor = [System.Drawing.Color]::White
$lblTitle.BackColor = [System.Drawing.Color]::Transparent
$lblTitle.Location = New-Object System.Drawing.Point(18, 16)
$lblTitle.Size = New-Object System.Drawing.Size(600, 32)
$banner.Controls.Add($lblTitle)

$lblSub = New-Object System.Windows.Forms.Label
$lblSub.Text = "勾选要执行的优化项目，点击「开始执行」。更改通过对应 .reg 文件恢复。"
$lblSub.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)
$lblSub.ForeColor = $script:C.AeroLink
$lblSub.BackColor = [System.Drawing.Color]::Transparent
$lblSub.Location = New-Object System.Drawing.Point(18, 50)
$lblSub.Size = New-Object System.Drawing.Size(600, 18)
$banner.Controls.Add($lblSub)

# ===== 组 1：应用清理 =====
$grpApps = New-Object System.Windows.Forms.GroupBox
$grpApps.Text = " 应用清理 "
$grpApps.ForeColor = $script:C.AeroText
$grpApps.BackColor = $script:C.GroupBg
$grpApps.Location = New-Object System.Drawing.Point(12, 82)
$grpApps.Size = New-Object System.Drawing.Size(608, 94)
$form.Controls.Add($grpApps)

$chkRemoveDefault = New-Object System.Windows.Forms.CheckBox
$chkRemoveDefault.Text = "移除默认预装应用（Appslist.txt 列表中的应用）"
$chkRemoveDefault.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkRemoveDefault.BackColor = $script:C.GroupBg
$chkRemoveDefault.Location = New-Object System.Drawing.Point(16, 24)
$chkRemoveDefault.Size = New-Object System.Drawing.Size(430, 22)
$chkRemoveDefault.Checked = $true
$grpApps.Controls.Add($chkRemoveDefault)

$btnSelectApps = New-Object System.Windows.Forms.Button
$btnSelectApps.Text = "选择要移除的应用..."
$btnSelectApps.Location = New-Object System.Drawing.Point(16, 54)
$btnSelectApps.Size = New-Object System.Drawing.Size(170, 28)
$grpApps.Controls.Add($btnSelectApps)

$script:lblApps = New-Object System.Windows.Forms.Label
$script:lblApps.Text = ""
$script:lblApps.ForeColor = [System.Drawing.Color]::Green
$script:lblApps.BackColor = $script:C.GroupBg
$script:lblApps.Location = New-Object System.Drawing.Point(198, 59)
$script:lblApps.Size = New-Object System.Drawing.Size(400, 20)
$grpApps.Controls.Add($script:lblApps)

# ===== 组 2：隐私与系统优化 =====
$grpSystem = New-Object System.Windows.Forms.GroupBox
$grpSystem.Text = " 隐私与系统优化 "
$grpSystem.ForeColor = $script:C.AeroText
$grpSystem.BackColor = $script:C.GroupBg
$grpSystem.Location = New-Object System.Drawing.Point(12, 184)
$grpSystem.Size = New-Object System.Drawing.Size(608, 180)
$form.Controls.Add($grpSystem)

$chkTelemetry = New-Object System.Windows.Forms.CheckBox
$chkTelemetry.Text = "禁用遥测、诊断数据、应用启动跟踪和定向广告"
$chkTelemetry.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkTelemetry.BackColor = $script:C.GroupBg
$chkTelemetry.Location = New-Object System.Drawing.Point(16, 24)
$chkTelemetry.Size = New-Object System.Drawing.Size(560, 22)
$chkTelemetry.Checked = $true
$grpSystem.Controls.Add($chkTelemetry)

$chkBing = New-Object System.Windows.Forms.CheckBox
$chkBing.Text = "禁用并移除 Windows 搜索中的必应搜索、必应 AI 和 Cortana"
$chkBing.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkBing.BackColor = $script:C.GroupBg
$chkBing.Location = New-Object System.Drawing.Point(16, 50)
$chkBing.Size = New-Object System.Drawing.Size(560, 22)
$grpSystem.Controls.Add($chkBing)

$chkLockscreenTips = New-Object System.Windows.Forms.CheckBox
$chkLockscreenTips.Text = "禁用锁屏提示与技巧（可能更改锁屏壁纸）"
$chkLockscreenTips.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkLockscreenTips.BackColor = $script:C.GroupBg
$chkLockscreenTips.Location = New-Object System.Drawing.Point(16, 76)
$chkLockscreenTips.Size = New-Object System.Drawing.Size(560, 22)
$grpSystem.Controls.Add($chkLockscreenTips)

$chkSuggestions = New-Object System.Windows.Forms.CheckBox
$chkSuggestions.Text = "禁用开始菜单、设置、通知等中的提示、技巧、建议和广告"
$chkSuggestions.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkSuggestions.BackColor = $script:C.GroupBg
$chkSuggestions.Location = New-Object System.Drawing.Point(16, 102)
$chkSuggestions.Size = New-Object System.Drawing.Size(560, 22)
$grpSystem.Controls.Add($chkSuggestions)

$chkCopilot = New-Object System.Windows.Forms.CheckBox
$chkCopilot.Text = "禁用 Windows Copilot"
$chkCopilot.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkCopilot.BackColor = $script:C.GroupBg
$chkCopilot.Location = New-Object System.Drawing.Point(16, 128)
$chkCopilot.Size = New-Object System.Drawing.Size(560, 22)
$grpSystem.Controls.Add($chkCopilot)

$chkContextMenu = New-Object System.Windows.Forms.CheckBox
$chkContextMenu.Text = "恢复旧的 Windows 10 风格右键菜单"
$chkContextMenu.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkContextMenu.BackColor = $script:C.GroupBg
$chkContextMenu.Location = New-Object System.Drawing.Point(16, 154)
$chkContextMenu.Size = New-Object System.Drawing.Size(560, 22)
$grpSystem.Controls.Add($chkContextMenu)

# ===== 组 3：任务栏与开始菜单 =====
$grpTaskbar = New-Object System.Windows.Forms.GroupBox
$grpTaskbar.Text = " 任务栏与开始菜单 "
$grpTaskbar.ForeColor = $script:C.AeroText
$grpTaskbar.BackColor = $script:C.GroupBg
$grpTaskbar.Location = New-Object System.Drawing.Point(12, 372)
$grpTaskbar.Size = New-Object System.Drawing.Size(608, 168)
$form.Controls.Add($grpTaskbar)

$chkAlignLeft = New-Object System.Windows.Forms.CheckBox
$chkAlignLeft.Text = "任务栏按钮左对齐"
$chkAlignLeft.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkAlignLeft.BackColor = $script:C.GroupBg
$chkAlignLeft.Location = New-Object System.Drawing.Point(16, 24)
$chkAlignLeft.Size = New-Object System.Drawing.Size(560, 22)
$grpTaskbar.Controls.Add($chkAlignLeft)

$lblSearch = New-Object System.Windows.Forms.Label
$lblSearch.Text = "任务栏搜索图标："
$lblSearch.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$lblSearch.BackColor = $script:C.GroupBg
$lblSearch.Location = New-Object System.Drawing.Point(16, 52)
$lblSearch.Size = New-Object System.Drawing.Size(110, 22)
$grpTaskbar.Controls.Add($lblSearch)

$comboSearch = New-Object System.Windows.Forms.ComboBox
$comboSearch.DropDownStyle = "DropDownList"
$comboSearch.Location = New-Object System.Drawing.Point(130, 50)
$comboSearch.Size = New-Object System.Drawing.Size(220, 24)
$comboSearch.Items.AddRange(@("不更改", "隐藏搜索图标", "仅显示图标", "图标 + 文字", "显示搜索框"))
$comboSearch.SelectedIndex = 0
$grpTaskbar.Controls.Add($comboSearch)

$chkTaskview = New-Object System.Windows.Forms.CheckBox
$chkTaskview.Text = "隐藏任务视图按钮"
$chkTaskview.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkTaskview.BackColor = $script:C.GroupBg
$chkTaskview.Location = New-Object System.Drawing.Point(16, 80)
$chkTaskview.Size = New-Object System.Drawing.Size(560, 22)
$grpTaskbar.Controls.Add($chkTaskview)

$chkWidgets = New-Object System.Windows.Forms.CheckBox
$chkWidgets.Text = "禁用小组件服务并隐藏任务栏小组件图标"
$chkWidgets.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkWidgets.BackColor = $script:C.GroupBg
$chkWidgets.Location = New-Object System.Drawing.Point(16, 106)
$chkWidgets.Size = New-Object System.Drawing.Size(560, 22)
$grpTaskbar.Controls.Add($chkWidgets)

$chkChat = New-Object System.Windows.Forms.CheckBox
$chkChat.Text = "隐藏聊天（Meet Now）图标"
$chkChat.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkChat.BackColor = $script:C.GroupBg
$chkChat.Location = New-Object System.Drawing.Point(16, 132)
$chkChat.Size = New-Object System.Drawing.Size(560, 22)
$grpTaskbar.Controls.Add($chkChat)

# ===== 组 4：Windows 资源管理器 =====
$grpExplorer = New-Object System.Windows.Forms.GroupBox
$grpExplorer.Text = " Windows 资源管理器 "
$grpExplorer.ForeColor = $script:C.AeroText
$grpExplorer.BackColor = $script:C.GroupBg
$grpExplorer.Location = New-Object System.Drawing.Point(12, 548)
$grpExplorer.Size = New-Object System.Drawing.Size(608, 120)
$form.Controls.Add($grpExplorer)

$chkHiddenFolders = New-Object System.Windows.Forms.CheckBox
$chkHiddenFolders.Text = "显示隐藏的文件、文件夹和驱动器"
$chkHiddenFolders.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkHiddenFolders.BackColor = $script:C.GroupBg
$chkHiddenFolders.Location = New-Object System.Drawing.Point(16, 24)
$chkHiddenFolders.Size = New-Object System.Drawing.Size(560, 22)
$grpExplorer.Controls.Add($chkHiddenFolders)

$chkFileExt = New-Object System.Windows.Forms.CheckBox
$chkFileExt.Text = "显示已知文件类型的扩展名"
$chkFileExt.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkFileExt.BackColor = $script:C.GroupBg
$chkFileExt.Location = New-Object System.Drawing.Point(16, 50)
$chkFileExt.Size = New-Object System.Drawing.Size(560, 22)
$grpExplorer.Controls.Add($chkFileExt)

$chkDupDrive = New-Object System.Windows.Forms.CheckBox
$chkDupDrive.Text = "从资源管理器导航窗格隐藏重复的可移动驱动器"
$chkDupDrive.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
$chkDupDrive.BackColor = $script:C.GroupBg
$chkDupDrive.Location = New-Object System.Drawing.Point(16, 76)
$chkDupDrive.Size = New-Object System.Drawing.Size(560, 22)
$grpExplorer.Controls.Add($chkDupDrive)

# ===== 日志区域 =====
$lblLog = New-Object System.Windows.Forms.Label
$lblLog.Text = "执行日志："
$lblLog.ForeColor = $script:C.AeroText
$lblLog.Location = New-Object System.Drawing.Point(14, 676)
$lblLog.Size = New-Object System.Drawing.Size(120, 18)
$form.Controls.Add($lblLog)

$script:logBox = New-Object System.Windows.Forms.RichTextBox
$script:logBox.Location = New-Object System.Drawing.Point(12, 698)
$script:logBox.Size = New-Object System.Drawing.Size(608, 74)
$script:logBox.ReadOnly = $true
$script:logBox.BackColor = [System.Drawing.Color]::White
$script:logBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$script:logBox.BorderStyle = "FixedSingle"
$form.Controls.Add($script:logBox)

# ===== 底部按钮（Win7 经典样式） =====
$btnRun = New-Object System.Windows.Forms.Button
$btnRun.Text = "开始执行"
$btnRun.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 10, [System.Drawing.FontStyle]::Bold)
$btnRun.Location = New-Object System.Drawing.Point(12, 782)
$btnRun.Size = New-Object System.Drawing.Size(110, 30)
$btnRun.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnRun.BackColor = $script:C.BtnMainBg
$btnRun.ForeColor = [System.Drawing.Color]::White
$btnRun.FlatAppearance.BorderColor = $script:C.BtnMainEdge
$btnRun.FlatAppearance.BorderSize = 1
$btnRun.FlatAppearance.MouseOverBackColor = $script:C.BtnMainHov
$form.Controls.Add($btnRun)

$btnClose = New-Object System.Windows.Forms.Button
$btnClose.Text = "关闭"
$btnClose.Location = New-Object System.Drawing.Point(132, 782)
$btnClose.Size = New-Object System.Drawing.Size(80, 30)
$btnClose.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnClose.BackColor = $script:C.BtnBg
$btnClose.ForeColor = $script:C.BtnText
$btnClose.FlatAppearance.BorderColor = $script:C.BtnEdge
$btnClose.FlatAppearance.BorderSize = 1
$btnClose.FlatAppearance.MouseOverBackColor = $script:C.BtnHov
$btnClose.Add_Click({ $form.Close() })
$form.Controls.Add($btnClose)

# ---------- Win7 通用按钮样式辅助 ----------
function Set-Win7Button {
    param($btn, [bool]$primary)
    $btn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    if ($primary) {
        $btn.BackColor = $script:C.BtnMainBg
        $btn.ForeColor = [System.Drawing.Color]::White
        $btn.FlatAppearance.BorderColor = $script:C.BtnMainEdge
        $btn.FlatAppearance.MouseOverBackColor = $script:C.BtnMainHov
    } else {
        $btn.BackColor = $script:C.BtnBg
        $btn.ForeColor = $script:C.BtnText
        $btn.FlatAppearance.BorderColor = $script:C.BtnEdge
        $btn.FlatAppearance.MouseOverBackColor = $script:C.BtnHov
    }
    $btn.FlatAppearance.BorderSize = 1
}

# 给"选择要移除的应用"按钮应用 Win7 样式
Set-Win7Button -btn $btnSelectApps -primary $false

# ---------- 窗体 Shown：用 DWM 把系统标题栏染成 Aero 深蓝 ----------
$script:captionColor = 0x007A4A1F   # 深 Aero 蓝 RGB(31,74,122) → COLORREF 0x007A4A1F
$form.Add_Shown({
    try {
        $attrVal = $script:captionColor
        [void][Win7Dwm]::DwmSetWindowAttribute($form.Handle, 35, [ref]$attrVal, 4)   # DWMWA_CAPTION_COLOR
        $txtVal = 0x00FFFFFF
        [void][Win7Dwm]::DwmSetWindowAttribute($form.Handle, 36, [ref]$txtVal, 4)     # DWMWA_TEXT_COLOR 白色标题文字
    } catch { }
})

# ---------- 事件：选择要移除的应用 ----------
$btnSelectApps.Add_Click({
    $appsFile = Join-Path $PSScriptRoot "Appslist.txt"
    if (-not (Test-Path $appsFile)) {
        [System.Windows.Forms.MessageBox]::Show("未找到 Appslist.txt 文件。", "应用选择", "OK", "Error") | Out-Null
        return
    }

    # 解析应用列表（去掉注释和空白）
    $list = @(Get-Content $appsFile | Where-Object { $_ -notmatch '^\s*$' } | ForEach-Object {
        $line = $_
        if ($line.StartsWith('#')) { $line = $line.TrimStart('#') }
        if ($line.IndexOf('#') -ne -1) { $line = $line.Substring(0, $line.IndexOf('#')) }
        if ($line.IndexOf(' ') -ne -1) { $line = $line.Substring(0, $line.IndexOf(' ')) }
        ($line.Trim('*')).Trim()
    } | Where-Object { $_.Length -gt 0 } | Sort-Object -Unique)

    if ($list.Count -eq 0) {
        [System.Windows.Forms.MessageBox]::Show("Appslist.txt 中未解析到任何应用。", "应用选择", "OK", "Error") | Out-Null
        return
    }

    # 读取上次保存的选择
    $savedSet = @()
    $custFile = Join-Path $PSScriptRoot "CustomAppsList"
    if (Test-Path $custFile) { $savedSet = @(Get-Content $custFile | Where-Object { $_.Trim() }) }

    # 构建选择对话框（同样使用 Aero 蓝配色）
    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = "选择要移除的应用"
    $dlg.ClientSize = New-Object System.Drawing.Size(430, 520)
    $dlg.StartPosition = "CenterParent"
    $dlg.FormBorderStyle = "FixedDialog"
    $dlg.MaximizeBox = $false
    $dlg.BackColor = $script:C.WindowBg
    $dlg.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)

    $chkAll = New-Object System.Windows.Forms.CheckBox
    $chkAll.Text = "全选 / 取消全选"
    $chkAll.ForeColor = $script:C.AeroText
    $chkAll.Location = New-Object System.Drawing.Point(14, 12)
    $chkAll.Size = New-Object System.Drawing.Size(150, 22)
    $dlg.Controls.Add($chkAll)

    $clb = New-Object System.Windows.Forms.CheckedListBox
    $clb.Location = New-Object System.Drawing.Point(14, 40)
    $clb.Size = New-Object System.Drawing.Size(400, 408)
    $clb.Sorted = $true
    $clb.BackColor = [System.Drawing.Color]::White
    foreach ($app in $list) {
        $isChecked = if ($savedSet.Count -gt 0) { $savedSet -contains $app } else { $true }
        [void]$clb.Items.Add($app, $isChecked)
    }
    $dlg.Controls.Add($clb)

    $chkAll.Add_CheckedChanged({
        for ($i = 0; $i -lt $clb.Items.Count; $i++) { $clb.SetItemChecked($i, $chkAll.Checked) }
    })

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Text = "确认"
    $btnOk.Location = New-Object System.Drawing.Point(216, 462)
    $btnOk.Size = New-Object System.Drawing.Size(95, 30)
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    Set-Win7Button -btn $btnOk -primary $true
    $dlg.Controls.Add($btnOk)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Text = "取消"
    $btnCancel.Location = New-Object System.Drawing.Point(319, 462)
    $btnCancel.Size = New-Object System.Drawing.Size(95, 30)
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    Set-Win7Button -btn $btnCancel -primary $false
    $dlg.Controls.Add($btnCancel)

    $dlg.AcceptButton = $btnOk
    $dlg.CancelButton = $btnCancel

    # 对话框也用 DWM 深蓝标题栏
    $dlg.Add_Shown({
        try {
            $attrVal = $script:captionColor
            [void][Win7Dwm]::DwmSetWindowAttribute($dlg.Handle, 35, [ref]$attrVal, 4)
            $txtVal = 0x00FFFFFF
            [void][Win7Dwm]::DwmSetWindowAttribute($dlg.Handle, 36, [ref]$txtVal, 4)
        } catch { }
    })

    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $selected = @($clb.CheckedItems | ForEach-Object { $_.ToString() })
        if ($selected.Count -gt 0) {
            Set-Content -Path $custFile -Value $selected -Encoding UTF8
            $script:customApps = $true
            $script:lblApps.Text = "✓ 已选择移除 $($selected.Count) 个应用"
            [System.Windows.Forms.MessageBox]::Show("已保存对 $($selected.Count) 个应用的选择。", "应用选择") | Out-Null
        } else {
            $script:customApps = $false
            $script:lblApps.Text = ""
            [System.Windows.Forms.MessageBox]::Show("未选择任何应用，将不会移除自定义应用。", "应用选择") | Out-Null
        }
    }
})

# ---------- 收集参数 ----------
function Get-Params {
    $params = @()
    if ($chkRemoveDefault.Checked) { $params += '-RemoveApps' }
    if ($script:customApps)       { $params += '-RemoveAppsCustom' }
    if ($chkTelemetry.Checked)    { $params += '-DisableTelemetry' }
    if ($chkBing.Checked)         { $params += '-DisableBing' }
    if ($chkLockscreenTips.Checked) { $params += '-DisableLockscreenTips' }
    if ($chkSuggestions.Checked)  { $params += '-DisableSuggestions' }
    if ($chkCopilot.Checked)      { $params += '-DisableCopilot' }
    if ($chkContextMenu.Checked)  { $params += '-RevertContextMenu' }
    if ($chkAlignLeft.Checked)    { $params += '-TaskbarAlignLeft' }
    switch ($comboSearch.SelectedIndex) {
        1 { $params += '-HideSearchTb' }
        2 { $params += '-ShowSearchIconTb' }
        3 { $params += '-ShowSearchLabelTb' }
        4 { $params += '-ShowSearchBoxTb' }
    }
    if ($chkTaskview.Checked)     { $params += '-HideTaskview' }
    if ($chkWidgets.Checked)      { $params += '-DisableWidgets' }
    if ($chkChat.Checked)         { $params += '-HideChat' }
    if ($chkHiddenFolders.Checked){ $params += '-ShowHiddenFolders' }
    if ($chkFileExt.Checked)      { $params += '-ShowKnownFileExt' }
    if ($chkDupDrive.Checked)     { $params += '-HideDupliDrive' }
    return $params
}

# ---------- 事件：开始执行 ----------
$btnRun.Add_Click({
    $params = @(Get-Params)
    if ($params.Count -eq 0) {
        [System.Windows.Forms.MessageBox]::Show("请至少勾选一项要执行的操作。", "Win11Debloat 中文版", "OK", "Information") | Out-Null
        return
    }

    $ps1 = Join-Path $PSScriptRoot "Win11Debloat.ps1"
    if (-not (Test-Path $ps1)) {
        [System.Windows.Forms.MessageBox]::Show("未找到核心脚本 Win11Debloat.ps1，请确认文件完整。", "错误", "OK", "Error") | Out-Null
        return
    }

    $btnRun.Enabled = $false
    $btnRun.Text = "执行中..."
    $script:logBox.Clear()
    $script:logBox.AppendText("===== 正在启动 Win11Debloat，请稍候... =====`r`n")
    $script:logBox.AppendText("参数：" + ($params -join ' ') + "`r`n`r`n")
    $script:logBox.Refresh()

    $script:outFile = Join-Path $env:TEMP "w11d_out.txt"
    $script:errFile = Join-Path $env:TEMP "w11d_err.txt"
    Remove-Item $script:outFile, $script:errFile -ErrorAction SilentlyContinue

    # 附加 -Silent：让核心脚本静默执行，不等待按键
    $paramsStr = ($params -join ' ')
    $argStr = "-NoProfile -ExecutionPolicy Bypass -File `"$ps1`" $paramsStr -Silent"
    $script:proc = Start-Process -FilePath powershell.exe -ArgumentList $argStr `
        -RedirectStandardOutput $script:outFile -RedirectStandardError $script:errFile `
        -PassThru -WindowStyle Hidden

    $script:lastRead = ""
    $script:timer.Start()
})

# ---------- 定时器：刷新日志 ----------
$script:timer = New-Object System.Windows.Forms.Timer
$script:timer.Interval = 400
$script:timer.Add_Tick({
    if (Test-Path $script:outFile) {
        $content = Get-Content $script:outFile -Raw
        if ($content) {
            if ($script:lastRead.Length -lt $content.Length) {
                $script:logBox.AppendText($content.Substring($script:lastRead.Length))
                $script:logBox.SelectionStart = $script:logBox.TextLength
                $script:logBox.ScrollToCaret()
            }
            $script:lastRead = $content
        }
    }

    if ($script:proc -and $script:proc.HasExited) {
        $script:timer.Stop()

        # 读取剩余输出
        if (Test-Path $script:outFile) {
            $content = Get-Content $script:outFile -Raw
            if ($content -and $script:lastRead.Length -lt $content.Length) {
                $script:logBox.AppendText($content.Substring($script:lastRead.Length))
            }
        }
        if (Test-Path $script:errFile) {
            $err = Get-Content $script:errFile -Raw
            if ($err -and $err.Trim()) {
                $script:logBox.AppendText("`r`n[错误输出]`r`n" + $err)
            }
        }

        $script:logBox.AppendText("`r`n===== 执行完成（退出码：" + $script:proc.ExitCode + "）=====")
        $script:logBox.SelectionStart = $script:logBox.TextLength
        $script:logBox.ScrollToCaret()

        $btnRun.Enabled = $true
        $btnRun.Text = "开始执行"
        [System.Windows.Forms.MessageBox]::Show("执行完成。" + $(if ($script:proc.ExitCode -eq 0) { "`n所有更改已应用，部分设置可能需要重启后生效。" } else { "`n执行过程中出现错误，请查看日志。" }), "Win11Debloat 中文版", "OK", "Information") | Out-Null
    }
})

# ---------- 显示窗体 ----------
$form.ShowDialog() | Out-Null
