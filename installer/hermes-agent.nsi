; Hermes Remote Agent — Windows Installer
; Build: makensis /DSERVER_URL=wss://your-server.com/ws /DAUTH_TOKEN=xxx hermes-agent.nsi
; Output: hermes-agent-setup.exe (~6 MB, self-contained)

Unicode true
SetCompressor /SOLID lzma

!define PRODUCT_NAME "Hermes Remote Agent"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "AYin"
!define PRODUCT_WEB_SITE "https://github.com/AYin-Z/hermes-remote-agent"

; ── ldflags 方式：编译时注入默认值，安装时可覆盖 ──
!ifndef SERVER_URL
  !define SERVER_URL "ws://127.0.0.1:8085/ws"
!endif
!ifndef AUTH_TOKEN
  !define AUTH_TOKEN ""
!endif

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "hermes-agent-setup.exe"
InstallDir "$PROGRAMFILES64\HermesRemoteAgent"
RequestExecutionLevel admin
ShowInstDetails show
ShowUninstDetails show

; ── Pages ──
Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"

  ; Embed agent.exe — needs to be in same dir as .nsi when building
  File "agent.exe"

  ; Write config (server URL + token)
  FileOpen $0 "$INSTDIR\config.txt" w
  FileWrite $0 "SERVER_URL=${SERVER_URL}$\r$\n"
  FileWrite $0 "AUTH_TOKEN=${AUTH_TOKEN}$\r$\n"
  FileClose $0

  ; Register as Windows service
  ; /c: 服务崩溃时自动重启  /d: display name
  nsExec::ExecToLog 'sc create "HermesRemoteAgent" binPath= "\"$INSTDIR\agent.exe\" -server ${SERVER_URL} -token ${AUTH_TOKEN}" start= auto DisplayName= "Hermes Remote Agent"'
  Pop $0
  IntCmp $0 0 +3
    MessageBox MB_ICONSTOP "Failed to create service (error $0)"
    Abort

  ; Set service recovery: restart on failure
  nsExec::ExecToLog 'sc failure "HermesRemoteAgent" reset= 86400 actions= restart/5000/restart/10000/restart/30000'
  Pop $0

  ; Set service description
  nsExec::ExecToLog 'sc description "HermesRemoteAgent" "Hermes Remote Agent — secure remote management via WebSocket"'
  Pop $0

  ; Start the service
  nsExec::ExecToLog 'sc start "HermesRemoteAgent"'
  Pop $0

  ; Start Menu shortcuts
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" "$INSTDIR\uninstall.exe"

  ; Uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Registry for Add/Remove Programs
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "NoRepair" 1

  DetailPrint "Installation complete."
SectionEnd

Section "Uninstall"
  ; Stop and remove service
  nsExec::ExecToLog 'sc stop "HermesRemoteAgent"'
  Sleep 2000

  ; Check if stopped
  nsExec::ExecToLog 'sc query "HermesRemoteAgent" | findstr /C:"STOPPED"'
  Pop $0
  IntCmp $0 0 +2
    Sleep 3000

  nsExec::ExecToLog 'sc delete "HermesRemoteAgent"'
  Pop $0

  ; Remove files
  Delete "$INSTDIR\agent.exe"
  Delete "$INSTDIR\config.txt"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"

  ; Remove Start Menu
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

  ; Remove registry
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

  DetailPrint "Uninstallation complete."
SectionEnd
