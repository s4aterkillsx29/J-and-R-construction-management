# J and R Construction Manager - Repair Optional Dependencies
$ErrorActionPreference = "Continue"
$InstallDir = Join-Path $env:LOCALAPPDATA "J_and_R_Construction_Manager"
$LogDir = Join-Path $InstallDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir ("repair_dependencies_" + (Get-Date -Format "yyyy-MM-dd_HHmmss") + ".log")
function Log($m){ $line="[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $m"; Add-Content -Path $LogPath -Value $line; Write-Host $line }
Log "Starting optional dependency repair."
$venvPy = Join-Path $InstallDir ".venv\Scripts\python.exe"
if(-not (Test-Path $venvPy)){
  Log "Private environment not found. Creating it now."
  $py = Get-Command python -ErrorAction SilentlyContinue
  if(-not $py){ $py = Get-Command py -ErrorAction SilentlyContinue }
  if(-not $py){ Log "Python not found. Install Python 3.11+ and rerun installer."; Start-Process "https://www.python.org/downloads/windows/"; exit 2 }
  if($py.Name -eq "py.exe"){ & py -3 -m venv (Join-Path $InstallDir ".venv") } else { & python -m venv (Join-Path $InstallDir ".venv") }
}
$req = Join-Path $InstallDir "requirements.txt"
if(-not (Test-Path $req)){ Log "requirements.txt not found."; exit 3 }
Log "Installing optional packages from requirements.txt. This may take a few minutes."
& $venvPy -m pip install --disable-pip-version-check --no-input --no-warn-script-location --default-timeout 120 -r $req *>> $LogPath
if($LASTEXITCODE -eq 0){ Log "Dependency repair complete."; exit 0 }
else { Log "Dependency repair ended with code $LASTEXITCODE. See log: $LogPath"; exit $LASTEXITCODE }
