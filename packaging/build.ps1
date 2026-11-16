# Builds, in dist\:
#   EdifierR990BT.exe        portable app (single file)
#   EdifierR990BT-Setup.exe  per-user installer (Inno Setup, app as a folder)
#   edifier-cli.exe          command-line tool
# Run from the repository root:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Set $env:BUILD_CLI_ONLY=true to build (and test) only edifier-cli.exe, which
# is much faster for iterating on the command-line tool.
$ErrorActionPreference = "Stop"
# Set $env:PYTHON to use a specific interpreter (CI uses "python").
$py = if ($env:PYTHON) { $env:PYTHON } else { "py" }
function Invoke-Checked { & $args[0] @($args | Select-Object -Skip 1); if ($LASTEXITCODE -ne 0) { throw "Failed: $args" } }

Invoke-Checked $py -m pip install -r requirements.txt pyinstaller==6.11.1

$cliOnly = $env:BUILD_CLI_ONLY -eq 'true'
if ($cliOnly) { Write-Host "CLI-only build (fast)" }

$common = @("--noconfirm", "--icon", "assets\icon.ico",
            "--collect-all", "bleak", "--collect-all", "winrt",
            "--paths", ".")

# The command-line tool is always built first (it is what most iterations need).
Invoke-Checked $py -m PyInstaller @common --onefile --console --name edifier-cli packaging\cli.py
& dist\edifier-cli.exe --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "edifier-cli.exe --help failed" }

if ($cliOnly) {
  Write-Host "Build OK (edifier-cli only)"
  return
}

$app = @("--windowed", "--name", "EdifierR990BT", "--hidden-import", "pystray._win32", "--collect-submodules", "qrcode")
Invoke-Checked $py -m PyInstaller @common @app --onefile packaging\app.py
Invoke-Checked $py -m PyInstaller @common @app --onedir --distpath build\onedir --workpath build\onedir-work packaging\app.py

# Installer. Inno Setup is preinstalled on GitHub's Windows runners; otherwise install it.
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
  choco install innosetup -y --no-progress | Out-Null
  $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
}
$version = (& $py -c "import edifier_ctl; print(edifier_ctl.__version__)").Trim()
Invoke-Checked $iscc /Q "/DAppVersion=$version" "/DSourceDir=..\build\onedir\EdifierR990BT" packaging\installer.iss

# The app exe has no console, so check its exit code explicitly.
# Never use -Wait here: it also waits for child processes, and a failing
# windowed exe sits on an error dialog forever.
function Invoke-App([string[]]$arguments, [int]$seconds = 60, [string]$exe = "dist\EdifierR990BT.exe") {
  $p = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru
  if (-not $p.WaitForExit($seconds * 1000)) {
    Get-Process EdifierR990BT -ErrorAction SilentlyContinue | Stop-Process -Force
    throw "EdifierR990BT.exe $arguments did not finish in $seconds s"
  }
  return $p.ExitCode
}
$code = Invoke-App @("--self-test")
if ($code -ne 0) { throw "Self-test failed with exit code $code" }
# An update restarts the app as a new process: check that the new copy still
# starts Tk after the old one has exited and removed its temporary files.
$marker = Join-Path $env:RUNNER_TEMP "restart-ok.txt"
if (-not $env:RUNNER_TEMP) { $marker = Join-Path $env:TEMP "restart-ok.txt" }
Remove-Item $marker -ErrorAction SilentlyContinue
Invoke-App @("--self-test-restart", "`"$marker`"") 30 | Out-Null
for ($i = 0; $i -lt 40 -and -not (Test-Path $marker); $i++) { Start-Sleep -Milliseconds 500 }
if (-not (Test-Path $marker)) {
  Get-Process EdifierR990BT -ErrorAction SilentlyContinue | Stop-Process -Force
  throw "Restarted copy failed to start"
}
Write-Host "restart OK"

# Toggle the per-user startup entry on the build machine and check it round-trips.
Invoke-Checked $py -c "from edifier_ctl import autostart as a; assert a.set_enabled(True) and a.is_enabled(); assert not a.set_enabled(False) and not a.is_enabled(); print('autostart OK')"
# Installer: silent install into a temporary folder, run the installed app's
# self-test, then uninstall silently.
$dir = Join-Path ($(if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP })) "r990bt-install-test"
$code = Invoke-App @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$dir`"") 180 "dist\EdifierR990BT-Setup.exe"
if ($code -ne 0) { throw "Installer failed with exit code $code" }
if (-not (Test-Path "$dir\unins000.exe")) { throw "Installer did not create the uninstaller" }
$code = Invoke-App @("--self-test") 60 "$dir\EdifierR990BT.exe"
if ($code -ne 0) { throw "Installed app self-test failed with exit code $code" }
$code = Invoke-App @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") 120 "$dir\unins000.exe"
for ($i = 0; $i -lt 30 -and (Test-Path "$dir\EdifierR990BT.exe"); $i++) { Start-Sleep -Milliseconds 500 }
if (Test-Path "$dir\EdifierR990BT.exe") { throw "Uninstaller left the app behind" }
Write-Host "installer OK"

Write-Host "Build OK"
