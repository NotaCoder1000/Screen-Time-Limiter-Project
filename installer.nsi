; ============================================================
;  Screen Limiter - NSIS Installer Script
;  installer.nsi
;
;  Compile with:
;    & "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
;
;  Requires:
;    - NSIS 3.x  (https://nsis.sourceforge.io)
;    - The dist\ScreenLimiter\ folder produced by build.py
; ============================================================

!define APP_NAME      "Screen Limiter"
!define APP_VERSION   "1.1.0"
!define APP_PUBLISHER "You"
!define APP_URL       "https://github.com"
!define SERVICE_NAME  "ScreenLimiterSvc"
!define INSTALL_DIR   "$PROGRAMFILES64\ScreenLimiter"
!define STARTMENU_DIR "$SMPROGRAMS\Screen Limiter"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScreenLimiter"
!define REGKEY_RUN    "Software\Microsoft\Windows\CurrentVersion\Run"
!define DIST_DIR      "dist\ScreenLimiter"

; ------------------------------------------------------------
; General settings
; ------------------------------------------------------------
Name              "${APP_NAME} ${APP_VERSION}"
OutFile           "ScreenLimiter-Setup.exe"
InstallDir        "${INSTALL_DIR}"
InstallDirRegKey  HKLM "${UNINSTALL_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor     /SOLID lzma

Unicode true

; ------------------------------------------------------------
; Modern UI
; ------------------------------------------------------------
!include "MUI2.nsh"
!include "LogicLib.nsh"

!define MUI_ABORTWARNING

; Installer pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ------------------------------------------------------------
; Version info (visible in exe Properties > Details)
; ------------------------------------------------------------
VIProductVersion              "${APP_VERSION}.0"
VIAddVersionKey "ProductName"     "${APP_NAME}"
VIAddVersionKey "ProductVersion"  "${APP_VERSION}"
VIAddVersionKey "CompanyName"     "${APP_PUBLISHER}"
VIAddVersionKey "FileDescription" "${APP_NAME} Setup"
VIAddVersionKey "FileVersion"     "${APP_VERSION}"
VIAddVersionKey "LegalCopyright"  "2025 ${APP_PUBLISHER}"

; ============================================================
; INSTALLER SECTION
; ============================================================

Section "Screen Limiter" SecMain
    SectionIn RO

    SetOutPath "$INSTDIR"

    ; Copy all bundled exes
    File "${DIST_DIR}\enforcer.exe"
    File "${DIST_DIR}\popup.exe"
    File "${DIST_DIR}\tray.exe"
    File "${DIST_DIR}\main.exe"

    ; Stop and remove any existing service or task from older installs
    ExecWait 'sc stop "${SERVICE_NAME}"'
    ExecWait 'sc delete "${SERVICE_NAME}"'
    ExecWait 'schtasks /Delete /TN "ScreenLimiterMonitor" /F'
    Sleep 1500

    ; Register enforcer.exe as a scheduled task running at logon with elevated privileges.
    ; enforcer.exe is NOT a Windows Service (no ServiceMain/SCM handshake), so
    ; Task Scheduler with /RL HIGHEST runs it elevated without the SCM 30-second timeout.
    ExecWait 'schtasks /Create /TN "ScreenLimiterMonitor" /TR "\"$INSTDIR\enforcer.exe\"" /SC ONLOGON /RL HIGHEST /IT /F'
    ExecWait 'schtasks /Run /TN "ScreenLimiterMonitor"'

    ; Add tray to startup for current user
    WriteRegStr HKCU "${REGKEY_RUN}" "ScreenLimiterTray" '"$INSTDIR\tray.exe"'

    ; Create Start Menu shortcuts
    CreateDirectory "${STARTMENU_DIR}"
    CreateShortcut "${STARTMENU_DIR}\Screen Limiter.lnk" "$INSTDIR\main.exe"
    CreateShortcut "${STARTMENU_DIR}\Uninstall.lnk"      "$INSTDIR\Uninstall.exe"

    ; Write Add/Remove Programs registry entry
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "DisplayName"          "${APP_NAME}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "DisplayVersion"        "${APP_VERSION}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "Publisher"             "${APP_PUBLISHER}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "URLInfoAbout"          "${APP_URL}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "InstallLocation"       "$INSTDIR"
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "UninstallString"       '"$INSTDIR\Uninstall.exe"'
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "QuietUninstallString"  '"$INSTDIR\Uninstall.exe" /S'
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "DisplayIcon"           "$INSTDIR\tray.exe"
    WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoModify"              1
    WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoRepair"              1

    ; Write the uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Open combined UI on first run (/firstrun skips the Admin tab password gate)
    Exec '"$INSTDIR\main.exe" /firstrun'

    ; Launch the tray icon
    Exec '"$INSTDIR\tray.exe"'

SectionEnd

; ============================================================
; UNINSTALLER SECTION
; ============================================================

Section "Uninstall"

    ; Stop the monitor process and remove the scheduled task
    ExecWait 'taskkill /F /IM enforcer.exe'
    ExecWait 'schtasks /Delete /TN "ScreenLimiterMonitor" /F'
    ; Also clean up any old Windows Service entry from previous installs
    ExecWait 'sc stop "${SERVICE_NAME}"'
    ExecWait 'sc delete "${SERVICE_NAME}"'
    Sleep 500

    ; Kill any running components
    ExecWait 'taskkill /F /IM tray.exe'
    ExecWait 'taskkill /F /IM main.exe'
    ExecWait 'taskkill /F /IM popup.exe'

    ; Remove startup registry entry
    DeleteRegValue HKCU "${REGKEY_RUN}" "ScreenLimiterTray"

    ; Remove Add/Remove Programs registry entry
    DeleteRegKey HKLM "${UNINSTALL_KEY}"

    ; Remove Start Menu folder
    RMDir /r "${STARTMENU_DIR}"

    ; Delete AppData folder (config, assignments, logs)
    RMDir /r "$APPDATA\ScreenLimiter"

    ; Delete installed files and folder
    Delete "$INSTDIR\enforcer.exe"
    Delete "$INSTDIR\popup.exe"
    Delete "$INSTDIR\tray.exe"
    Delete "$INSTDIR\main.exe"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"

    MessageBox MB_OK "Screen Limiter has been completely uninstalled."

SectionEnd

; ============================================================
; CALLBACKS
; ============================================================

Function .onInit
    ; If already installed, offer to uninstall first
    ReadRegStr $0 HKLM "${UNINSTALL_KEY}" "UninstallString"
    ${If} $0 != ""
        MessageBox MB_YESNO|MB_ICONQUESTION "Screen Limiter is already installed.$\n$\nUninstall the existing version first?" IDYES do_uninstall IDNO skip_uninstall
        do_uninstall:
            ExecWait '"$0" /S'
            Sleep 2000
        skip_uninstall:
    ${EndIf}
FunctionEnd
