# Builds dist\EdifierR990BT.exe (app) and dist\edifier-cli.exe (command line).
# Run from the repository root:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
# Set $env:PYTHON to use a specific interpreter (CI uses "python").
$py = if ($env:PYTHON) { $env:PYTHON } else { "py" }
function Invoke-Checked { & $args[0] @($args | Select-Object -Skip 1); if ($LASTEXITCODE -ne 0) { throw "Failed: $args" } }

Invoke-Checked $py -m pip install -r requirements.txt pyinstaller==6.11.1

$common = @("--noconfirm", "--onefile", "--icon", "assets\icon.ico",
            "--collect-all", "bleak", "--collect-all", "winrt",
            "--paths", ".")

Invoke-Checked $py -m PyInstaller @common --windowed --name EdifierR990BT --hidden-import pystray._win32 --collect-submodules qrcode packaging\app.py
Invoke-Checked $py -m PyInstaller @common --console --name edifier-cli packaging\cli.py

# The app exe has no console, so check its exit code explicitly.
$p = Start-Process -FilePath "dist\EdifierR990BT.exe" -ArgumentList "--self-test" -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "Self-test failed with exit code $($p.ExitCode)" }
# An update restarts the app as a new process: check that the new copy still
# starts Tk after the old one has exited and removed its temporary files.
$marker = Join-Path $env:RUNNER_TEMP "restart-ok.txt"
if (-not $env:RUNNER_TEMP) { $marker = Join-Path $env:TEMP "restart-ok.txt" }
Remove-Item $marker -ErrorAction SilentlyContinue
Start-Process -FilePath "dist\EdifierR990BT.exe" -ArgumentList "--self-test-restart", "`"$marker`"" -Wait
for ($i = 0; $i -lt 40 -and -not (Test-Path $marker); $i++) { Start-Sleep -Milliseconds 500 }
if (-not (Test-Path $marker)) { throw "Restarted copy failed to start" }
Write-Host "restart OK"

# Toggle the per-user startup entry on the build machine and check it round-trips.
Invoke-Checked $py -c "from edifier_ctl import autostart as a; assert a.set_enabled(True) and a.is_enabled(); assert not a.set_enabled(False) and not a.is_enabled(); print('autostart OK')"
& dist\edifier-cli.exe --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "edifier-cli.exe --help failed" }
Write-Host "Build OK"
