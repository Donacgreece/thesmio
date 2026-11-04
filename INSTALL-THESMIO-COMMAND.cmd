@echo off
setlocal
set "THESMIO_INSTALL_SCRIPT=%~dp0push-thesmio.ps1"
if not exist "%THESMIO_INSTALL_SCRIPT%" (
  echo ERROR: push-thesmio.ps1 must be next to this installer.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $bin=Join-Path $env:LOCALAPPDATA 'Thesmio\bin'; New-Item -ItemType Directory -Force -Path $bin | Out-Null; $script=Join-Path $bin 'push-thesmio.ps1'; Copy-Item -LiteralPath $env:THESMIO_INSTALL_SCRIPT -Destination $script -Force; $launcher='@echo off' + [Environment]::NewLine + 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%%~dp0push-thesmio.ps1" %%*'; [IO.File]::WriteAllText((Join-Path $bin 'thesmio.cmd'), $launcher); $path=[Environment]::GetEnvironmentVariable('Path','User'); if (($path -split ';') -notcontains $bin) { [Environment]::SetEnvironmentVariable('Path', (($path.TrimEnd(';') + ';' + $bin).TrimStart(';')), 'User') }; Write-Host 'Installed. Open a NEW PowerShell window and run: thesmio' -ForegroundColor Green"
if errorlevel 1 (
 echo Installation failed.
 pause
 exit /b 1
)
pause
