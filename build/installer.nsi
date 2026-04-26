; TaxIQ Windows Installer — NSIS script
; Requires NSIS 3.x  (https://nsis.sourceforge.io)
;
; Produces: TaxIQ-Setup.exe
; Installs to: C:\Program Files\TaxIQ  (or user-chosen dir)
; Creates: Start Menu shortcut, Desktop shortcut, uninstaller

Unicode True

!define APP_NAME    "TaxIQ"
!define APP_VERSION "1.0.0"
!define APP_EXE     "TaxIQ.exe"
!define COMPANY     "TaxIQ"
!define REG_KEY     "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\dist\TaxIQ-Setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${REG_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUnInstDetails show

;------------------------------------------------------------------
; Pages
;------------------------------------------------------------------
!include "MUI2.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "..\build\icon.ico"
!define MUI_UNICON "..\build\icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch TaxIQ now"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

;------------------------------------------------------------------
; Installer sections
;------------------------------------------------------------------
Section "MainSection" SEC01
    SetOutPath "$INSTDIR"
    ; Copy entire PyInstaller dist/TaxIQ directory
    File /r "..\dist\TaxIQ\*.*"

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
        "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0

    ; Desktop shortcut
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" \
        "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0

    ; Registry entries for Add/Remove Programs
    WriteRegStr   HKLM "${REG_KEY}" "DisplayName"      "${APP_NAME} ${APP_VERSION}"
    WriteRegStr   HKLM "${REG_KEY}" "DisplayVersion"   "${APP_VERSION}"
    WriteRegStr   HKLM "${REG_KEY}" "Publisher"        "${COMPANY}"
    WriteRegStr   HKLM "${REG_KEY}" "InstallLocation"  "$INSTDIR"
    WriteRegStr   HKLM "${REG_KEY}" "UninstallString"  '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKLM "${REG_KEY}" "NoModify"         1
    WriteRegDWORD HKLM "${REG_KEY}" "NoRepair"         1

    ; Estimate install size (KB)
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${REG_KEY}" "EstimatedSize" "$0"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

;------------------------------------------------------------------
; Uninstaller
;------------------------------------------------------------------
Section "Uninstall"
    ; Kill any running instance
    ExecWait 'taskkill /F /IM "${APP_EXE}"' $0

    ; Remove files
    RMDir /r "$INSTDIR"

    ; Remove shortcuts
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    RMDir  "$SMPROGRAMS\${APP_NAME}"

    ; Remove registry entries
    DeleteRegKey HKLM "${REG_KEY}"
SectionEnd

;------------------------------------------------------------------
; Helper macro — GetSize
;------------------------------------------------------------------
!include "FileFunc.nsh"
!insertmacro GetSize
