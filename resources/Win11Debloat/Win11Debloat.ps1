#Requires -RunAsAdministrator

[CmdletBinding(SupportsShouldProcess)]
param (
    [switch]$Silent,
    [switch]$RunAppConfigurator,
    [switch]$RunDefaults, [switch]$RunWin11Defaults,
    [switch]$RemoveApps, 
    [switch]$RemoveAppsCustom,
    [switch]$RemoveGamingApps,
    [switch]$RemoveCommApps,
    [switch]$RemoveDevApps,
    [switch]$RemoveW11Outlook,
    [switch]$DisableTelemetry,
    [switch]$DisableBingSearches, [switch]$DisableBing,
    [switch]$DisableLockscrTips, [switch]$DisableLockscreenTips,
    [switch]$DisableWindowsSuggestions, [switch]$DisableSuggestions,
    [switch]$ShowHiddenFolders,
    [switch]$ShowKnownFileExt,
    [switch]$HideDupliDrive,
    [switch]$TaskbarAlignLeft,
    [switch]$HideSearchTb, [switch]$ShowSearchIconTb, [switch]$ShowSearchLabelTb, [switch]$ShowSearchBoxTb,
    [switch]$HideTaskview,
    [switch]$DisableCopilot,
    [switch]$DisableWidgets,
    [switch]$HideWidgets,
    [switch]$DisableChat,
    [switch]$HideChat,
    [switch]$ClearStart,
    [switch]$RevertContextMenu,
    [switch]$DisableOnedrive, [switch]$HideOnedrive,
    [switch]$Disable3dObjects, [switch]$Hide3dObjects,
    [switch]$DisableMusic, [switch]$HideMusic,
    [switch]$DisableIncludeInLibrary, [switch]$HideIncludeInLibrary,
    [switch]$DisableGiveAccessTo, [switch]$HideGiveAccessTo,
    [switch]$DisableShare, [switch]$HideShare
)


# Shows application selection form that allows the user to select what apps they want to remove or keep
function ShowAppSelectionForm {
    [reflection.assembly]::loadwithpartialname("System.Windows.Forms") | Out-Null
    [reflection.assembly]::loadwithpartialname("System.Drawing") | Out-Null

    # Initialise form objects
    $form = New-Object System.Windows.Forms.Form
    $label = New-Object System.Windows.Forms.Label
    $button1 = New-Object System.Windows.Forms.Button
    $button2 = New-Object System.Windows.Forms.Button
    $selectionBox = New-Object System.Windows.Forms.CheckedListBox 
    $loadingLabel = New-Object System.Windows.Forms.Label
    $onlyInstalledCheckBox = New-Object System.Windows.Forms.CheckBox
    $checkUncheckCheckBox = New-Object System.Windows.Forms.CheckBox
    $initialFormWindowState = New-Object System.Windows.Forms.FormWindowState

    $global:selectionBoxIndex = -1

    # saveButton eventHandler
    $handler_saveButton_Click= 
    {
        $global:SelectedApps = $selectionBox.CheckedItems

        # Create file that stores selected apps if it doesn't exist
        if (!(Test-Path "$PSScriptRoot/CustomAppsList")) {
            $null = New-Item "$PSScriptRoot/CustomAppsList"
        } 

        Set-Content -Path "$PSScriptRoot/CustomAppsList" -Value $global:SelectedApps

        $form.Close()
    }

    # cancelButton eventHandler
    $handler_cancelButton_Click= 
    {
        $form.Close()
    }

    $selectionBox_SelectedIndexChanged= 
    {
        $global:selectionBoxIndex = $selectionBox.SelectedIndex
    }

    $selectionBox_MouseDown=
    {
        if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
            if([System.Windows.Forms.Control]::ModifierKeys -eq [System.Windows.Forms.Keys]::Shift) {
                if($global:selectionBoxIndex -ne -1) {
                    $topIndex = $global:selectionBoxIndex

                    if ($selectionBox.SelectedIndex -gt $topIndex) {
                        for(($i = ($topIndex)); $i -le $selectionBox.SelectedIndex; $i++){
                            $selectionBox.SetItemChecked($i, $selectionBox.GetItemChecked($topIndex))
                        }
                    }
                    elseif ($topIndex -gt $selectionBox.SelectedIndex) {
                        for(($i = ($selectionBox.SelectedIndex)); $i -le $topIndex; $i++){
                            $selectionBox.SetItemChecked($i, $selectionBox.GetItemChecked($topIndex))
                        }
                    }
                }
            }
            elseif($global:selectionBoxIndex -ne $selectionBox.SelectedIndex) {
                $selectionBox.SetItemChecked($selectionBox.SelectedIndex, -not $selectionBox.GetItemChecked($selectionBox.SelectedIndex))
            }
        }
    }

    $check_All=
    {
        for(($i = 0); $i -lt $selectionBox.Items.Count; $i++){
            $selectionBox.SetItemChecked($i, $checkUncheckCheckBox.Checked)
        }
    }

    $load_Apps=
    {
        # Correct the initial state of the form to prevent the .Net maximized form issue
        $form.WindowState = $initialFormWindowState

        # Reset state to default before loading appslist again
        $global:selectionBoxIndex = -1
        $checkUncheckCheckBox.Checked = $False

        # Show loading indicator
        $loadingLabel.Visible = $true
        $form.Refresh()

        # Clear selectionBox before adding any new items
        $selectionBox.Items.Clear()

        # Set filePath where Appslist can be found
        $appsFile = "$PSScriptRoot/Appslist.txt"
        $listOfApps = ""

        if ($onlyInstalledCheckBox.Checked -and ($global:wingetInstalled -eq $true)) {
            # Attempt to get a list of installed apps via winget, times out after 10 seconds
            $job = Start-Job { return winget list --accept-source-agreements --disable-interactivity }
            $jobDone = $job | Wait-Job -TimeOut 10

            if (-not $jobDone) {
                # Show error that the script was unable to get list of apps from winget
                [System.Windows.MessageBox]::Show('无法通过 winget 加载已安装应用列表，部分应用可能无法显示在列表中。','错误','Ok','Error')
            }
            else {
                # Add output of job (list of apps) to $listOfApps
                $listOfApps = Receive-Job -Job $job
            }
        }

        # Go through appslist and add items one by one to the selectionBox
        Foreach ($app in (Get-Content -Path $appsFile | Where-Object { $_ -notmatch '^\s*$' } )) { 
            $appChecked = $true

            # Remove first # if it exists and set AppChecked to false
            if ($app.StartsWith('#')) {
                $app = $app.TrimStart("#")
                $appChecked = $false
            }
            # Remove any comments from the Appname
            if (-not ($app.IndexOf('#') -eq -1)) {
                $app = $app.Substring(0, $app.IndexOf('#'))
            }
            # Remove any remaining spaces from the Appname
            if (-not ($app.IndexOf(' ') -eq -1)) {
                $app = $app.Substring(0, $app.IndexOf(' '))
            }

            $appString = $app.Trim('*')

            # Make sure appString is not empty
            if ($appString.length -gt 0) {
                if ($onlyInstalledCheckBox.Checked) {
                    # onlyInstalledCheckBox is checked, check if app is installed before adding it to selectionBox
                    if ($listOfApps -like ("* " + $appString + " *")) {
                        $installed = "installed"
                    }
                    elseif (($appString -eq "Microsoft.Edge") -and ($listOfApps -like "* XPFFTQ037JWMHS *")) {
                        $installed = "installed"
                    }
                    else {
                        $installed = Get-AppxPackage -Name $app
                    }

                    if ($installed.length -eq 0) {
                        # App is not installed, continue to next item without adding this app to the selectionBox
                        continue
                    }
                }

                # Add the app to the selectionBox and set it's checked status
                $selectionBox.Items.Add($appString, $appChecked) | Out-Null
            }
        }
        
        # Hide loading indicator
        $loadingLabel.Visible = $False

        # Sort selectionBox alphabetically
        $selectionBox.Sorted = $True
    }

    $form.Text = "Win11Debloat 应用选择"
    $form.Name = "appSelectionForm"
    $form.DataBindings.DefaultDataSourceUpdateMode = 0
    $form.ClientSize = New-Object System.Drawing.Size(400,502)
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $False

    $button1.TabIndex = 4
    $button1.Name = "saveButton"
    $button1.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $button1.UseVisualStyleBackColor = $True
    $button1.Text = "确认"
    $button1.Location = New-Object System.Drawing.Point(27,472)
    $button1.Size = New-Object System.Drawing.Size(75,23)
    $button1.DataBindings.DefaultDataSourceUpdateMode = 0
    $button1.add_Click($handler_saveButton_Click)

    $form.Controls.Add($button1)

    $button2.TabIndex = 5
    $button2.Name = "cancelButton"
    $button2.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $button2.UseVisualStyleBackColor = $True
    $button2.Text = "取消"
    $button2.Location = New-Object System.Drawing.Point(129,472)
    $button2.Size = New-Object System.Drawing.Size(75,23)
    $button2.DataBindings.DefaultDataSourceUpdateMode = 0
    $button2.add_Click($handler_cancelButton_Click)

    $form.Controls.Add($button2)

    $label.Location = New-Object System.Drawing.Point(13,5)
    $label.Size = New-Object System.Drawing.Size(400,14)
    $Label.Font = 'Microsoft Sans Serif,8'
    $label.Text = '勾选要移除的应用，取消勾选要保留的应用'

    $form.Controls.Add($label)

    $loadingLabel.Location = New-Object System.Drawing.Point(16,46)
    $loadingLabel.Size = New-Object System.Drawing.Size(300,418)
    $loadingLabel.Text = '正在加载应用...'
    $loadingLabel.BackColor = "White"
    $loadingLabel.Visible = $false

    $form.Controls.Add($loadingLabel)

    $onlyInstalledCheckBox.TabIndex = 6
    $onlyInstalledCheckBox.Location = New-Object System.Drawing.Point(230,474)
    $onlyInstalledCheckBox.Size = New-Object System.Drawing.Size(150,20)
    $onlyInstalledCheckBox.Text = '仅显示已安装的应用'
    $onlyInstalledCheckBox.add_CheckedChanged($load_Apps)

    $form.Controls.Add($onlyInstalledCheckBox)

    $checkUncheckCheckBox.TabIndex = 7
    $checkUncheckCheckBox.Location = New-Object System.Drawing.Point(16,22)
    $checkUncheckCheckBox.Size = New-Object System.Drawing.Size(150,20)
    $checkUncheckCheckBox.Text = '全选/取消全选'
    $checkUncheckCheckBox.add_CheckedChanged($check_All)

    $form.Controls.Add($checkUncheckCheckBox)

    $selectionBox.FormattingEnabled = $True
    $selectionBox.DataBindings.DefaultDataSourceUpdateMode = 0
    $selectionBox.Name = "selectionBox"
    $selectionBox.Location = New-Object System.Drawing.Point(13,43)
    $selectionBox.Size = New-Object System.Drawing.Size(374,424)
    $selectionBox.TabIndex = 3
    $selectionBox.add_SelectedIndexChanged($selectionBox_SelectedIndexChanged)
    $selectionBox.add_Click($selectionBox_MouseDown)

    $form.Controls.Add($selectionBox)

    # Save the initial state of the form
    $initialFormWindowState = $form.WindowState

    # Load apps into selectionBox
    $form.add_Load($load_Apps)

    # Focus selectionBox when form opens
    $form.Add_Shown({$form.Activate(); $selectionBox.Focus()})

    # Show the Form
    return $form.ShowDialog()
}


# Reads list of apps from file and removes them for all user accounts and from the OS image.
function RemoveAppsFromFile {
    param (
        $appsFilePath
    )

    $appsList = @()

    Write-Output "> 正在移除默认预装应用..."

    # Get list of apps from file at the path provided, and remove them one by one
    Foreach ($app in (Get-Content -Path $appsFilePath | Where-Object { $_ -notmatch '^#.*' -and $_ -notmatch '^\s*$' } )) { 
        # Remove any spaces before and after the Appname
        $app = $app.Trim()

        # Remove any comments from the Appname
        if (-not ($app.IndexOf('#') -eq -1)) {
            $app = $app.Substring(0, $app.IndexOf('#'))
        }
        # Remove any remaining spaces from the Appname
        if (-not ($app.IndexOf(' ') -eq -1)) {
            $app = $app.Substring(0, $app.IndexOf(' '))
        }
        
        $appString = $app.Trim('*')
        $appsList += $appString
    }

    RemoveApps $appsList
}


# Removes apps specified during function call from all user accounts and from the OS image.
function RemoveApps {
    param (
        $appslist
    )

    Foreach ($app in $appsList) { 
        Write-Output "正在尝试移除 $app..."

        if (($app -eq "Microsoft.OneDrive") -or ($app -eq "Microsoft.Edge")) {
            # Use winget to remove OneDrive and Edge
            if ($global:wingetInstalled -eq $false) {
                Write-Host "WinGet 未安装或版本过旧，无法移除 $app" -ForegroundColor Red
            }
            else {
                # Uninstall app via winget
                winget uninstall --accept-source-agreements --disable-interactivity --id $app
            }
        }
        else {
            # Use Remove-AppxPackage to remove all other apps
            $app = '*' + $app + '*'

            # Remove installed app for all existing users
            Get-AppxPackage -Name $app -AllUsers | Remove-AppxPackage -AllUsers

            # Remove provisioned app from OS image, so the app won't be installed for any new users
            Get-AppxProvisionedPackage -Online | Where-Object { $_.PackageName -like $app } | ForEach-Object { Remove-ProvisionedAppxPackage -Online -AllUsers -PackageName $_.PackageName }
        }
    }
}


# Import & execute regfile
function RegImport {
    param (
        $message,
        $path
    )

    Write-Output $message
    reg import $path
    Write-Output ""
}


# Stop & Restart the Windows explorer process
function RestartExplorer {
    Write-Output "> 正在重启 Windows 资源管理器以应用所有更改。注意：此操作可能导致屏幕短暂闪烁。"

    Start-Sleep 0.3

    taskkill /f /im explorer.exe

    Start-Sleep 0.3

    Start-Process explorer.exe

    Write-Output ""
}


# Clear all pinned apps from the start menu. 
# Credit: https://lazyadmin.nl/win-11/customize-windows-11-start-menu-layout/
function ClearStartMenu {
    param (
        $message
    )

    Write-Output $message

    # Path to start menu template
    $startmenuTemplate = "$PSScriptRoot/Start/start2.bin"

    # Get all user profile folders
    $usersStartMenu = get-childitem -path "C:\Users\*\AppData\Local\Packages\Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy\LocalState"

    # Copy Start menu to all users folders
    ForEach ($startmenu in $usersStartMenu) {
        $startmenuBinFile = $startmenu.Fullname + "\start2.bin"

        # Check if bin file exists
        if (Test-Path $startmenuBinFile) {
            Copy-Item -Path $startmenuTemplate -Destination $startmenu -Force

            $cpyMsg = "已为用户 " + $startmenu.Fullname.Split("\")[2] + " 替换开始菜单"
            Write-Output $cpyMsg
        }
        else {
            # Bin file doesn't exist, indicating the user is not running the correct version of Windows. Exit function
            Write-Output "错误：未找到开始菜单文件。请确保您运行的是 Windows 11 22H2 或更高版本"
            return
        }
    }

    # Also apply start menu template to the default profile

    # Path to default profile
    $defaultProfile = "C:\Users\default\AppData\Local\Packages\Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy\LocalState"

    # Create folder if it doesn't exist
    if (-not(Test-Path $defaultProfile)) {
        new-item $defaultProfile -ItemType Directory -Force | Out-Null
        Write-Output "已为默认用户创建 LocalState 文件夹"
    }

    # Copy template to default profile
    Copy-Item -Path $startmenuTemplate -Destination $defaultProfile -Force
    Write-Output "已复制开始菜单模板到默认用户文件夹"
    Write-Output ""
}


# Add parameter to script and write to file
function AddParameter {
    param (
        $parameterName,
        $message
    )

    # Add key if it doesn't already exist
    if (-not $global:Params.ContainsKey($parameterName)) {
        $global:Params.Add($parameterName, $true)
    }

    # Create or clear file that stores last used settings
    if (!(Test-Path "$PSScriptRoot/SavedSettings")) {
        $null = New-Item "$PSScriptRoot/SavedSettings"
    } 
    elseif ($global:FirstSelection) {
        $null = Clear-Content "$PSScriptRoot/SavedSettings"
    }
    
    $global:FirstSelection = $false

    # Create entry and add it to the file
    $entry = $parameterName + "#- " + $message
    Add-Content -Path "$PSScriptRoot/SavedSettings" -Value $entry
}


function PrintHeader {
    param (
        $title
    )

    $fullTitle = " Win11Debloat 脚本 - " + $title

    Clear-Host
    Write-Output "-------------------------------------------------------------------------------------------"
    Write-Output $fullTitle
    Write-Output "-------------------------------------------------------------------------------------------"
}


function PrintFromFile {
    param (
        $path
    )

    Clear-Host

    # Get & print script menu from file
    Foreach ($line in (Get-Content -Path $path )) {   
        Write-Output $line
    }
}


function AwaitKeyToExit {
    # Suppress prompt if Silent parameter was passed
    if (-not $Silent) {
        Write-Output ""
        Write-Output "按任意键退出..."
        $null = [System.Console]::ReadKey()
    }
}


 # Check if winget is installed & if it is, check if the version is at least v1.4
if ((Get-AppxPackage -Name "*Microsoft.DesktopAppInstaller*") -and ((winget -v) -replace 'v','' -gt 1.4)) {
    $global:wingetInstalled = $true
}
else {
    $global:wingetInstalled = $false

    # Show warning that requires user confirmation, Suppress confirmation if Silent parameter was passed
    if (-not $Silent) {
        Write-Warning "Winget 未安装或版本过旧。这可能导致 Win11Debloat 无法移除某些应用。"
        Write-Output ""
        Write-Output "按任意键继续..."
        Read-Host | Out-Null
    }
}

# Hide progress bars for app removal, as they block Win11Debloat's output
$ProgressPreference = 'SilentlyContinue'

$global:Params = $PSBoundParameters
$global:FirstSelection = $true
$SPParams = 'WhatIf', 'Confirm', 'Verbose', 'Silent'
$SPParamCount = 0

# Count how many SPParams exist within Params
# This is later used to check if any options were selected
foreach ($Param in $SPParams) {
    if ($global:Params.ContainsKey($Param)) {
        $SPParamCount++
    }
}

# Check if SavedSettings file exists, if it doesn't exist check if LastSettings file exists
if (Test-Path "$PSScriptRoot/SavedSettings") {
    if ([String]::IsNullOrWhiteSpace((Get-content "$PSScriptRoot/SavedSettings"))) {
        # Remove SavedSettings file if it's empty
        Remove-Item -Path "$PSScriptRoot/SavedSettings" -recurse
    }
}
elseif (Test-Path "$PSScriptRoot/LastSettings") {
    if ([String]::IsNullOrWhiteSpace((Get-content "$PSScriptRoot/LastSettings"))) {
        # Remove LastSettings file if it's empty
        Remove-Item -Path "$PSScriptRoot/LastSettings" -recurse
    }
    else {
        # Rename LastSettings file to SavedSettings if it isn't empty
        Rename-Item -Path "$PSScriptRoot/LastSettings" -NewName "$PSScriptRoot/SavedSettings"
    }
}

# Only run the app selection form if the 'RunAppConfigurator' parameter was passed to the script
if ($RunAppConfigurator) {
    PrintHeader "应用配置"

    $result = ShowAppSelectionForm

    # Show different message based on whether the app selection was saved or cancelled
    if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host "应用配置在未保存的情况下被关闭。" -ForegroundColor Red
    }
    else {
        Write-Output "您的应用选择已保存到脚本根目录的 'CustomAppsList' 文件。"
    }

    AwaitKeyToExit

    # Exit script
    Exit
}

# Change script execution based on provided parameters or user input
if ((-not $global:Params.Count) -or $RunDefaults -or $RunWin11Defaults -or ($SPParamCount -eq $global:Params.Count)) {
    if ($RunDefaults -or $RunWin11Defaults) {
        $Mode = '1'
    }
    else {
        # Show menu and wait for user input, loops until valid input is provided
        Do { 
            $ModeSelectionMessage = "请选择选项 (1/2/3/0)" 

            PrintHeader '主菜单'

            Write-Output "(1) 默认模式：应用默认设置"
            Write-Output "(2) 自定义模式：按需修改脚本"
            Write-Output "(3) 应用移除模式：选择并移除应用，不修改其他设置"

            # Only show this option if SavedSettings file exists
            if (Test-Path "$PSScriptRoot/SavedSettings") {
                Write-Output "(4) 应用上次保存的自定义设置"
                
                $ModeSelectionMessage = "请选择选项 (1/2/3/4/0)" 
            }

            Write-Output ""
            Write-Output "(0) 显示脚本信息"
            Write-Output ""
            Write-Output ""

            $Mode = Read-Host $ModeSelectionMessage

            # Show information based on user input, Suppress user prompt if Silent parameter was passed
            if ($Mode -eq '0') {
                # Get & print script information from file
                PrintFromFile "$PSScriptRoot/Menus/Info"

                Write-Output ""
                Write-Output "按任意键返回..."
                $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
            }
            elseif (($Mode -eq '4')-and -not (Test-Path "$PSScriptRoot/SavedSettings")) {
                $Mode = $null
            }
        }
        while ($Mode -ne '1' -and $Mode -ne '2' -and $Mode -ne '3' -and $Mode -ne '4') 
    }

    # Add execution parameters based on the mode
    switch ($Mode) {
        # Default mode, loads defaults after confirmation
        '1' { 
            # Print the default settings & require userconfirmation, unless Silent parameter was passed
            if (-not $Silent) {
                PrintFromFile "$PSScriptRoot/Menus/DefaultSettings"

                Write-Output ""
                Write-Output "按回车执行脚本，或按 CTRL+C 退出..."
                Read-Host | Out-Null
            }

            $DefaultParameterNames = 'RemoveApps','DisableTelemetry','DisableBing','DisableLockscreenTips','DisableSuggestions','ShowKnownFileExt','DisableWidgets','HideChat','DisableCopilot'

            PrintHeader '默认模式'

            # Add default parameters if they don't already exist
            foreach ($ParameterName in $DefaultParameterNames) {
                if (-not $global:Params.ContainsKey($ParameterName)){
                    $global:Params.Add($ParameterName, $true)
                }
            }

            # Only add this option for Windows 10 users, if it doesn't already exist
            if ((get-ciminstance -query "select caption from win32_operatingsystem where caption like '%Windows 10%'") -and (-not $global:Params.ContainsKey('Hide3dObjects'))) {
                $global:Params.Add('Hide3dObjects', $Hide3dObjects)
            }
        }

        # Custom mode, show & add options based on user input
        '2' { 
            # Get current Windows build version to compare against features
            $WinVersion = Get-ItemPropertyValue 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' CurrentBuild

            PrintHeader '自定义模式'

            # Show options for removing apps, only continue on valid input
            Do {
                Write-Host "选项：" -ForegroundColor Yellow
                Write-Host " (n) 不移除任何应用" -ForegroundColor Yellow
                Write-Host " (1) 仅移除 'Appslist.txt' 中的默认预装应用" -ForegroundColor Yellow
                Write-Host " (2) 移除默认预装应用，以及邮件、日历、开发者和游戏相关应用"  -ForegroundColor Yellow
                Write-Host " (3) 自行选择要移除或保留的应用" -ForegroundColor Yellow
                $RemoveCommAppInput = Read-Host "是否移除预装应用？(n/1/2/3)" 

                # Show app selection form if user entered option 3
                if ($RemoveCommAppInput -eq '3') {
                    $result = ShowAppSelectionForm

                    if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
                        # User cancelled or closed app selection, show error and change RemoveCommAppInput so the menu will be shown again
                        Write-Output ""
                        Write-Host "已取消应用选择，请重试" -ForegroundColor Red

                        $RemoveCommAppInput = 'c'
                    }
                    
                    Write-Output ""
                }
            }
            while ($RemoveCommAppInput -ne 'n' -and $RemoveCommAppInput -ne '0' -and $RemoveCommAppInput -ne '1' -and $RemoveCommAppInput -ne '2' -and $RemoveCommAppInput -ne '3') 

            # Select correct option based on user input
            switch ($RemoveCommAppInput) {
                '1' {
                    AddParameter 'RemoveApps' '移除默认预装应用'
                }
                '2' {
                    AddParameter 'RemoveApps' '移除默认预装应用'
                    AddParameter 'RemoveCommApps' '移除邮件、日历和人员应用'
                    AddParameter 'RemoveW11Outlook' '移除新的 Windows 版 Outlook 应用'
                    AddParameter 'RemoveDevApps' '移除开发者相关应用'
                    AddParameter 'RemoveGamingApps' '移除 Xbox 应用和 Xbox Game Bar'
                }
                '3' {
                    Write-Output "您已选择移除 $($global:SelectedApps.Count) 个应用"

                    AddParameter 'RemoveAppsCustom' "移除 $($global:SelectedApps.Count) 个应用:"
                }
            }

            # Only show this option for Windows 11 users running build 22621 or later
            if ($WinVersion -ge 22621){
                Write-Output ""

                if ($( Read-Host -Prompt "移除开始菜单中的所有固定应用？这将影响所有现有和新建用户，且无法撤销 (y/n)" ) -eq 'y') {
                    AddParameter 'ClearStart' '为新建和现有用户移除开始菜单中的所有固定应用'
                }
            }

            Write-Output ""

            if ($( Read-Host -Prompt "禁用遥测、诊断数据、应用启动跟踪和定向广告？(y/n)" ) -eq 'y') {
                AddParameter 'DisableTelemetry' '禁用遥测、诊断数据和定向广告'
            }

            Write-Output ""

            if ($( Read-Host -Prompt "禁用并移除 Windows 搜索中的必应搜索、必应 AI 和 Cortana？(y/n)" ) -eq 'y') {
                AddParameter 'DisableBing' '禁用并移除 Windows 搜索中的必应搜索、必应 AI 和 Cortana'
            }

            Write-Output ""

            if ($( Read-Host -Prompt "禁用开始菜单、设置、通知、资源管理器和锁屏中的提示、技巧、建议和广告？(y/n)" ) -eq 'y') {
                AddParameter 'DisableSuggestions' '禁用开始菜单、设置、通知和 Windows 资源管理器中的提示、技巧、建议和广告'
                AddParameter 'DisableLockscreenTips' '禁用锁屏提示与技巧'
            }

            # Only show this option for Windows 11 users running build 22621 or later
            if ($WinVersion -ge 22621){
                Write-Output ""

                if ($( Read-Host -Prompt "禁用 Windows Copilot？这将影响所有用户 (y/n)" ) -eq 'y') {
                    AddParameter 'DisableCopilot' '禁用 Windows Copilot'
                }
            }

            # Only show this option for Windows 11 users running build 22000 or later
            if ($WinVersion -ge 22000){
                Write-Output ""

                if ($( Read-Host -Prompt "恢复旧的 Windows 10 风格右键菜单？(y/n)" ) -eq 'y') {
                    AddParameter 'RevertContextMenu' '恢复旧的 Windows 10 风格右键菜单'
                }
            }

            Write-Output ""

            if ($( Read-Host -Prompt "是否对任务栏及相关服务进行任何更改？(y/n)" ) -eq 'y') {
                # Only show these specific options for Windows 11 users running build 22000 or later
                if ($WinVersion -ge 22000){
                    Write-Output ""

                    if ($( Read-Host -Prompt "   将任务栏按钮左对齐？(y/n)" ) -eq 'y') {
                        AddParameter 'TaskbarAlignLeft' '将任务栏图标左对齐'
                    }

                    # Show options for search icon on taskbar, only continue on valid input
                    Do {
                        Write-Output ""
                        Write-Host "   选项：" -ForegroundColor Yellow
                        Write-Host "    (n) 不更改" -ForegroundColor Yellow
                        Write-Host "    (1) 从任务栏隐藏搜索图标" -ForegroundColor Yellow
                        Write-Host "    (2) 在任务栏显示搜索图标" -ForegroundColor Yellow
                        Write-Host "    (3) 在任务栏显示带文字的搜索图标" -ForegroundColor Yellow
                        Write-Host "    (4) 在任务栏显示搜索框" -ForegroundColor Yellow
                        $TbSearchInput = Read-Host "   隐藏或更改任务栏搜索图标？(n/1/2/3/4)" 
                    }
                    while ($TbSearchInput -ne 'n' -and $TbSearchInput -ne '0' -and $TbSearchInput -ne '1' -and $TbSearchInput -ne '2' -and $TbSearchInput -ne '3' -and $TbSearchInput -ne '4') 

                    # Select correct taskbar search option based on user input
                    switch ($TbSearchInput) {
                        '1' {
                            AddParameter 'HideSearchTb' '从任务栏隐藏搜索图标'
                        }
                        '2' {
                            AddParameter 'ShowSearchIconTb' '在任务栏显示搜索图标'
                        }
                        '3' {
                            AddParameter 'ShowSearchLabelTb' '在任务栏显示带文字的搜索图标'
                        }
                        '4' {
                            AddParameter 'ShowSearchBoxTb' '在任务栏显示搜索框'
                        }
                    }

                    Write-Output ""

                    if ($( Read-Host -Prompt "   从任务栏隐藏任务视图按钮？(y/n)" ) -eq 'y') {
                        AddParameter 'HideTaskview' '从任务栏隐藏任务视图按钮'
                    }
                }

                Write-Output ""

                if ($( Read-Host -Prompt "   禁用小组件服务并从任务栏隐藏图标？(y/n)" ) -eq 'y') {
                    AddParameter 'DisableWidgets' '禁用小组件服务并从任务栏隐藏小组件（新闻和兴趣）图标'
                }

                # Only show this options for Windows users running build 22621 or earlier
                if ($WinVersion -le 22621){
                    Write-Output ""

                    if ($( Read-Host -Prompt "   从任务栏隐藏聊天（Meet Now）图标？(y/n)" ) -eq 'y') {
                        AddParameter 'HideChat' '从任务栏隐藏聊天（Meet Now）图标'
                    }
                }
            }

            Write-Output ""

            if ($( Read-Host -Prompt "是否对 Windows 资源管理器进行任何更改？(y/n)" ) -eq 'y') {
                Write-Output ""

                if ($( Read-Host -Prompt "   显示隐藏的文件、文件夹和驱动器？(y/n)" ) -eq 'y') {
                    AddParameter 'ShowHiddenFolders' '显示隐藏的文件、文件夹和驱动器'
                }

                Write-Output ""

                if ($( Read-Host -Prompt "   显示已知文件类型的扩展名？(y/n)" ) -eq 'y') {
                    AddParameter 'ShowKnownFileExt' '显示已知文件类型的扩展名'
                }

                Write-Output ""

                if ($( Read-Host -Prompt "   从 Windows 资源管理器侧栏隐藏重复的可移动驱动器，使其仅在“此电脑”下显示？(y/n)" ) -eq 'y') {
                    AddParameter 'HideDupliDrive' '从 Windows 资源管理器导航窗格隐藏重复的可移动驱动器'
                }

                # Only show option for disabling these specific folders for Windows 10 users
                if (get-ciminstance -query "select caption from win32_operatingsystem where caption like '%Windows 10%'"){
                    Write-Output ""

                    if ($( Read-Host -Prompt "是否要从 Windows 资源管理器侧栏隐藏任何文件夹？(y/n)" ) -eq 'y') {
                        Write-Output ""

                        if ($( Read-Host -Prompt "   从 Windows 资源管理器侧栏隐藏 OneDrive 文件夹？(y/n)" ) -eq 'y') {
                            AddParameter 'HideOnedrive' '从 Windows 资源管理器侧栏隐藏 OneDrive 文件夹'
                        }

                        Write-Output ""
                        
                        if ($( Read-Host -Prompt "   从 Windows 资源管理器侧栏隐藏 3D 对象文件夹？(y/n)" ) -eq 'y') {
                            AddParameter 'Hide3dObjects' "在 Windows 资源管理器的“此电脑”下隐藏 3D 对象文件夹" 
                        }
                        
                        Write-Output ""

                        if ($( Read-Host -Prompt "   从 Windows 资源管理器侧栏隐藏音乐文件夹？(y/n)" ) -eq 'y') {
                            AddParameter 'HideMusic' "在 Windows 资源管理器的“此电脑”下隐藏音乐文件夹"
                        }
                    }
                }
            }

            # Only show option for disabling context menu items for Windows 10 users or if the user opted to restore the Windows 10 context menu
            if ((get-ciminstance -query "select caption from win32_operatingsystem where caption like '%Windows 10%'") -or $global:Params.ContainsKey('RevertContextMenu')){
                Write-Output ""

                if ($( Read-Host -Prompt "是否要禁用任何右键菜单选项？(y/n)" ) -eq 'y') {
                    Write-Output ""

                    if ($( Read-Host -Prompt "   从右键菜单隐藏“包含到库中”选项？(y/n)" ) -eq 'y') {
                        AddParameter 'HideIncludeInLibrary' "从右键菜单隐藏“包含到库中”选项"
                    }

                    Write-Output ""

                    if ($( Read-Host -Prompt "   从右键菜单隐藏“授予访问权限”选项？(y/n)" ) -eq 'y') {
                        AddParameter 'HideGiveAccessTo' "从右键菜单隐藏“授予访问权限”选项"
                    }

                    Write-Output ""

                    if ($( Read-Host -Prompt "   从右键菜单隐藏“共享”选项？(y/n)" ) -eq 'y') {
                        AddParameter 'HideShare' "从右键菜单隐藏“共享”选项"
                    }
                }
            }

            # Suppress prompt if Silent parameter was passed
            if (-not $Silent) {
                Write-Output ""
                Write-Output ""
                Write-Output ""
                Write-Output "按回车确认您的选择并执行脚本，或按 CTRL+C 退出..."
                Read-Host | Out-Null
            }

            PrintHeader '自定义模式'
        }

        # App removal, remove apps based on user selection
        '3' {
            PrintHeader "应用移除"

            $result = ShowAppSelectionForm

            if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
                Write-Output "您已选择移除 $($global:SelectedApps.Count) 个应用"
                AddParameter 'RemoveAppsCustom' "移除 $($global:SelectedApps.Count) 个应用:"

                # Suppress prompt if Silent parameter was passed
                if (-not $Silent) {
                    Write-Output ""
                    Write-Output "按回车移除所选应用，或按 CTRL+C 退出..."
                    Read-Host | Out-Null
                }
            }
            else {
                Write-Host "已取消选择，未移除任何应用！" -ForegroundColor Red
            }

            Write-Output ""
        }

        # Load custom options selection from the "SavedSettings" file
        '4' {
            if (-not $Silent) {
                PrintHeader '自定义模式'
                Write-Output "Win11Debloat 将执行以下更改："

                # Get & print default settings info from file
                Foreach ($line in (Get-Content -Path "$PSScriptRoot/SavedSettings" )) { 
                    # Remove any spaces before and after the Appname
                    $line = $line.Trim()
                
                    # Check if line has # char, show description, add parameter
                    if (-not ($line.IndexOf('#') -eq -1)) {
                        Write-Output $line.Substring(($line.IndexOf('#') + 1), ($line.Length - $line.IndexOf('#') - 1))
                        $paramName = $line.Substring(0, $line.IndexOf('#'))

                        if ($paramName -eq "RemoveAppsCustom") {
                            # If paramName is RemoveAppsCustom, check if CustomAppsFile exists
                            if (Test-Path "$PSScriptRoot/CustomAppsList") {
                                # Apps file exists, print list of apps
                                $appsList = @()

                                # Get apps list from file
                                Foreach ($app in (Get-Content -Path "$PSScriptRoot/CustomAppsList" )) { 
                                    # Remove any spaces before and after the app name
                                    $app = $app.Trim()

                                    $appsList += $app
                                }

                                Write-Host $appsList -ForegroundColor DarkGray
                            }
                            else {
                                # Apps file does not exist, print error and continue to next item
                                Write-Host "无法从文件加载自定义应用列表，不会移除任何应用！" -ForegroundColor Red
                                continue
                            }
                        }

                        if (-not $global:Params.ContainsKey($ParameterName)){
                            $global:Params.Add($paramName, $true)
                        }
                    }
                }

                Write-Output ""
                Write-Output ""
                Write-Output "按回车执行脚本，或按 CTRL+C 退出..."
                Read-Host | Out-Null
            }

            PrintHeader '自定义模式'
        }
    }
}
else {
    PrintHeader '自定义模式'
}


# If the number of keys in SPParams equals the number of keys in Params then no modifications/changes were selected
#  or added by the user, and the script can exit without making any changes.
if ($SPParamCount -eq $global:Params.Keys.Count) {
    Write-Output "脚本未做任何更改即完成。"
    
    AwaitKeyToExit
}
else {
    # Execute all selected/provided parameters
    switch ($global:Params.Keys) {
        'RemoveApps' {
            RemoveAppsFromFile "$PSScriptRoot/Appslist.txt" 
            continue
        }
        'RemoveAppsCustom' {
            if (Test-Path "$PSScriptRoot/CustomAppsList") {
                $appsList = @()

                # Get apps list from file
                Foreach ($app in (Get-Content -Path "$PSScriptRoot/CustomAppsList" )) { 
                    # Remove any spaces before and after the app name
                    $app = $app.Trim()

                    $appsList += $app
                }

                Write-Output "> 正在移除 $($appsList.Count) 个应用..."
                RemoveApps $appsList
            }
            else {
                Write-Host "> 无法从文件加载自定义应用列表，未移除任何应用！" -ForegroundColor Red
            }

            Write-Output ""
            continue
        }
        'RemoveCommApps' {
            Write-Output "> 正在移除邮件、日历和人员应用..."
            
            $appsList = 'Microsoft.windowscommunicationsapps', 'Microsoft.People'
            RemoveApps $appsList

            Write-Output ""
            continue
        }
        'RemoveW11Outlook' {
            Write-Output "> 正在移除新的 Windows 版 Outlook 应用..."
            
            $appsList = 'Microsoft.OutlookForWindows'
            RemoveApps $appsList

            Write-Output ""
            continue
        }
        'RemoveDevApps' {
            Write-Output "> 正在移除开发者相关应用..."

            $appsList = 'Microsoft.PowerAutomateDesktop', 'Microsoft.RemoteDesktop', 'Windows.DevHome'
            RemoveApps $appsList

            Write-Output ""

            continue
        }
        'RemoveGamingApps' {
            Write-Output "> 正在移除游戏相关应用..."

            $appsList = 'Microsoft.GamingApp', 'Microsoft.XboxGameOverlay', 'Microsoft.XboxGamingOverlay'
            RemoveApps $appsList

            Write-Output ""

            continue
        }
        'ClearStart' {
            ClearStartMenu "> 正在移除开始菜单中的所有固定应用..."
            continue
        }
        'DisableTelemetry' {
            RegImport "> 正在禁用遥测、诊断数据、应用启动跟踪和定向广告..." $PSScriptRoot\Regfiles\Disable_Telemetry.reg
            continue
        }
        {$_ -in "DisableBingSearches", "DisableBing"} {
            RegImport "> 正在禁用 Windows 搜索中的必应搜索、必应 AI 和 Cortana..." $PSScriptRoot\Regfiles\Disable_Bing_Cortana_In_Search.reg
            
            # Also remove the app package for bing search
            $appsList = 'Microsoft.BingSearch'
            RemoveApps $appsList

            Write-Output ""

            continue
        }
        {$_ -in "DisableLockscrTips", "DisableLockscreenTips"} {
            RegImport "> 正在禁用锁屏提示与技巧..." $PSScriptRoot\Regfiles\Disable_Lockscreen_Tips.reg
            continue
        }
        {$_ -in "DisableSuggestions", "DisableWindowsSuggestions"} {
            RegImport "> 正在禁用 Windows 中的提示、技巧、建议和广告..." $PSScriptRoot\Regfiles\Disable_Windows_Suggestions.reg
            continue
        }
        'RevertContextMenu' {
            RegImport "> 正在恢复旧的 Windows 10 风格右键菜单..." $PSScriptRoot\Regfiles\Disable_Show_More_Options_Context_Menu.reg
            continue
        }
        'TaskbarAlignLeft' {
            RegImport "> 正在将任务栏按钮左对齐..." $PSScriptRoot\Regfiles\Align_Taskbar_Left.reg
            continue
        }
        'HideSearchTb' {
            RegImport "> 正在从任务栏隐藏搜索图标..." $PSScriptRoot\Regfiles\Hide_Search_Taskbar.reg
            continue
        }
        'ShowSearchIconTb' {
            RegImport "> 正在将任务栏搜索改为仅图标..." $PSScriptRoot\Regfiles\Show_Search_Icon.reg
            continue
        }
        'ShowSearchLabelTb' {
            RegImport "> 正在将任务栏搜索改为图标加文字..." $PSScriptRoot\Regfiles\Show_Search_Icon_And_Label.reg
            continue
        }
        'ShowSearchBoxTb' {
            RegImport "> 正在将任务栏搜索改为搜索框..." $PSScriptRoot\Regfiles\Show_Search_Box.reg
            continue
        }
        'HideTaskview' {
            RegImport "> 正在从任务栏隐藏任务视图按钮..." $PSScriptRoot\Regfiles\Hide_Taskview_Taskbar.reg
            continue
        }
        'DisableCopilot' {
            RegImport "> 正在禁用 Windows Copilot..." $PSScriptRoot\Regfiles\Disable_Copilot.reg
            continue
        }
        {$_ -in "HideWidgets", "DisableWidgets"} {
            RegImport "> 正在禁用小组件服务并从任务栏隐藏小组件图标..." $PSScriptRoot\Regfiles\Disable_Widgets_Taskbar.reg
            continue
        }
        {$_ -in "HideChat", "DisableChat"} {
            RegImport "> 正在从任务栏隐藏聊天图标..." $PSScriptRoot\Regfiles\Disable_Chat_Taskbar.reg
            continue
        }
        'ShowHiddenFolders' {
            RegImport "> 正在显示隐藏的文件、文件夹和驱动器..." $PSScriptRoot\Regfiles\Show_Hidden_Folders.reg
            continue
        }
        'ShowKnownFileExt' {
            RegImport "> 正在显示已知文件类型的扩展名..." $PSScriptRoot\Regfiles\Show_Extensions_For_Known_File_Types.reg
            continue
        }
        'HideDupliDrive' {
            RegImport "> 正在从 Windows 资源管理器导航窗格隐藏重复的可移动驱动器..." $PSScriptRoot\Regfiles\Hide_duplicate_removable_drives_from_navigation_pane_of_File_Explorer.reg
            continue
        }
        {$_ -in "HideOnedrive", "DisableOnedrive"} {
            RegImport "> 正在从 Windows 资源管理器导航窗格隐藏 OneDrive 文件夹..." $PSScriptRoot\Regfiles\Hide_Onedrive_Folder.reg
            continue
        }
        {$_ -in "Hide3dObjects", "Disable3dObjects"} {
            RegImport "> 正在从 Windows 资源管理器导航窗格隐藏 3D 对象文件夹..." $PSScriptRoot\Regfiles\Hide_3D_Objects_Folder.reg
            continue
        }
        {$_ -in "HideMusic", "DisableMusic"} {
            RegImport "> 正在从 Windows 资源管理器导航窗格隐藏音乐文件夹..." $PSScriptRoot\Regfiles\Hide_Music_folder.reg
            continue
        }
        {$_ -in "HideIncludeInLibrary", "DisableIncludeInLibrary"} {
            RegImport "> 正在从右键菜单隐藏 '包含到库中'..." $PSScriptRoot\Regfiles\Disable_Include_in_library_from_context_menu.reg
            continue
        }
        {$_ -in "HideGiveAccessTo", "DisableGiveAccessTo"} {
            RegImport "> 正在从右键菜单隐藏 '授予访问权限'..." $PSScriptRoot\Regfiles\Disable_Give_access_to_context_menu.reg
            continue
        }
        {$_ -in "HideShare", "DisableShare"} {
            RegImport "> 正在从右键菜单隐藏 '共享'..." $PSScriptRoot\Regfiles\Disable_Share_from_context_menu.reg
            continue
        }
    }

    RestartExplorer

    Write-Output ""
    Write-Output ""
    Write-Output "脚本执行成功！"

    AwaitKeyToExit
}
