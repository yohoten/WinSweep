; ═══════════════════════════════════════════════════════════════════════════
;  WinSweep — Inno Setup 安装脚本（种子模板）
;
;  编译方式
;    推荐：python build.py                    自动生成 version.iss 与 dist/app 后编译
;    手工：ISCC.exe installer\WinSweep.iss     需先备好 icon.ico 与 dist/app
;
;  相对路径约定
;    本脚本内的相对路径均相对「本文件所在目录」（installer/），
;    因此项目根为 ".."，安装内容来源为 "..\dist\app"。
;
;  复用到其它项目时只需改这一段
;    MyAppName / MyAppPublisher / MyAppId / MyAppExeName / DefaultDirName，
;    以及 [Files] 中与项目相关的行。
; ═══════════════════════════════════════════════════════════════════════════

; ── 版本号与开关：优先使用 build.py 生成的 build_meta.iss，其次用内置默认值 ──
;    （不通过 ISCC 命令行 /D 传宏：命令行宏无法区分数字与字符串）
#ifexist "build_meta.iss"
  #include "build_meta.iss"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "3.4"
#endif

; ── 构建期开关（手工编译时用以下默认值）──
#ifndef HasChineseLanguage
  #define HasChineseLanguage 1          ; 1 = 挂载简体中文语言文件
#endif
#ifndef IncludeLandingPage
  #define IncludeLandingPage 1          ; 1 = 随包安装 index.html 落地页
#endif
#ifndef ArchAllowed
  #define ArchAllowed "x64compatible"   ; Inno 6.3+ 语法；旧版改为 "x64"
#endif
#ifndef BundleMode
  #define BundleMode "onedir"           ; 仅作记录：onedir / onefile
#endif

; ── 应用元数据 ──
#define MyAppName "WinSweep"
#define MyAppExeName "WinSweep.exe"
#define MyAppPublisher "yohoten"
#define MyAppId "{{6D396EC1-6916-4CDF-8C8A-63ED8923773A}"
#define ProjectDir ".."
#define AppStageDir ProjectDir + "\dist\app"

; ═══════════════════════════════════════════════════════════════════════════
[Setup]
; AppId 是安装包的唯一身份：升级安装、卸载识别都依赖它，确定后不要再改
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
DisableWelcomePage=no

; 安装包输出
OutputDir={#ProjectDir}\dist\installer
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-setup
#ifexist "..\icon.ico"
SetupIconFile={#ProjectDir}\icon.ico
#endif
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; 权限与平台：程序需要管理员权限执行清理 / DISM / sfc 等操作
PrivilegesRequired=admin
ArchitecturesAllowed={#ArchAllowed}
ArchitecturesInstallIn64BitMode={#ArchAllowed}
MinVersion=10.0

; 安装期间自动关闭占用文件的旧实例（依赖 Windows 重启管理器）
CloseApplications=yes
RestartApplications=no

; 卸载入口显示
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

; 文件属性
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} 安装程序

; ═══════════════════════════════════════════════════════════════════════════
[Languages]
#if HasChineseLanguage == 1
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

; ═══════════════════════════════════════════════════════════════════════════
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; ═══════════════════════════════════════════════════════════════════════════
[Files]
; dist/app 已包含全部运行文件：exe 启动器、_internal 依赖、WinSweep.pyw、
; resources/（Optimization + Win11Debloat）、icon.ico、README.md，以及可选的 index.html。
; 安装内容与「免安装运行目录」完全一致，因此这里只需一行，
; 避免安装清单与源目录两处维护、遗漏文件。
Source: "{#AppStageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ═══════════════════════════════════════════════════════════════════════════
[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Comment: "{#MyAppName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

; ═══════════════════════════════════════════════════════════════════════════
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; ═══════════════════════════════════════════════════════════════════════════
[Registry]
; 记录安装位置，便于其它工具 / 脚本定位（卸载时一并清除）
Root: HKLM; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

; ═══════════════════════════════════════════════════════════════════════════
[UninstallDelete]
; 运行时生成的字节码缓存；data/ 目录在 [Code] 中按用户选择决定是否删除
Type: filesandordirs; Name: "{app}\__pycache__"

; ═══════════════════════════════════════════════════════════════════════════
[Code]
// 卸载时询问是否保留用户数据（data/ 保存字体缩放、当前视图、日志等偏好）
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    DataDir := ExpandConstant('{app}\data');
    if DirExists(DataDir) then
    begin
      if MsgBox('是否同时删除配置与日志？' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                '选择「否」将保留字体缩放、视图、日志等偏好设置；' + #13#10 +
                '重新安装后可继续沿用。',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
