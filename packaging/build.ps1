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
# Never use -Wait here: it also waits for child processes, and a failing
# windowed exe sits on an error dialog forever.
function Invoke-App([string[]]$arguments, [int]$seconds = 60) {
  $p = Start-Process -FilePath "dist\EdifierR990BT.exe" -ArgumentList $arguments -PassThru
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
& dist\edifier-cli.exe --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "edifier-cli.exe --help failed" }
Write-Host "Build OK"
