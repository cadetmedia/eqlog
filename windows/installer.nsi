Target amd64-unicode
Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!ifndef APP_VERSION
  !error "APP_VERSION is required"
!endif
!ifndef PAYLOAD_DIR
  !error "PAYLOAD_DIR is required"
!endif
!ifndef OUTPUT_DIR
  !error "OUTPUT_DIR is required"
!endif
!ifndef UNINSTALL_INCLUDE
  !error "UNINSTALL_INCLUDE is required"
!endif

Name "EQLog"
OutFile "${OUTPUT_DIR}/eqlog-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\EQLog"
InstallDirRegKey HKCU "Software\cadetmedia\EQLog" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
BrandingText "EQLog - EverQuest Legends Log Cleaner"
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "EQLog"
VIAddVersionKey /LANG=1033 "FileDescription" "EQLog Setup"
VIAddVersionKey /LANG=1033 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "CC0 1.0 Universal"
!define MUI_ICON "../assets/eqlog.ico"
!define MUI_UNICON "../assets/eqlog.ico"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "EQLog requires 64-bit Windows 10 or newer."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "EQLog requires Windows 10 or newer."
    Abort
  ${EndIf}
  SetShellVarContext current
FunctionEnd

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD_DIR}/*"
  WriteUninstaller "$INSTDIR\Uninstall EQLog.exe"
  CreateShortcut "$DESKTOP\EQLog.lnk" "$INSTDIR\EQLog.exe"
  CreateShortcut "$SMPROGRAMS\EQLog.lnk" "$INSTDIR\EQLog.exe"
  WriteRegStr HKCU "Software\cadetmedia\EQLog" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog" "DisplayName" "EQLog"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog" "DisplayIcon" "$INSTDIR\EQLog.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog" "UninstallString" '$\"$INSTDIR\Uninstall EQLog.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog" "QuietUninstallString" '$\"$INSTDIR\Uninstall EQLog.exe$\" /S'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog" "NoRepair" 1
SectionEnd

Function .onInstSuccess
  IfSilent done
  ExecShell "open" "$INSTDIR\EQLog.exe"
  done:
FunctionEnd

Function un.onInit
  SetShellVarContext current
FunctionEnd

Section "Uninstall"
  ; Generated explicit file paths: never recursively delete user logs or backups.
  !include "${UNINSTALL_INCLUDE}"
  Delete "$INSTDIR\Uninstall EQLog.exe"
  Delete "$DESKTOP\EQLog.lnk"
  Delete "$SMPROGRAMS\EQLog.lnk"
  DeleteRegKey HKCU "Software\cadetmedia\EQLog"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog"
  RMDir "$INSTDIR"
SectionEnd
