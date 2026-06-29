# Seeds owner emergency mastery key into data\local_secrets.env (gitignored).
# Run once on Owner Master PC after install or update.
param(
    [string]$InstallDir = "",
    [string]$Password = "ivygrows1"
)
if (-not $InstallDir) {
    $resolvePs1 = Join-Path $PSScriptRoot "Resolve-InstallDir.ps1"
    if (Test-Path -LiteralPath $resolvePs1) {
        $InstallDir = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $resolvePs1 -Profile "OwnerMaster").Trim()
    }
}
if (-not $InstallDir) {
    $InstallDir = Join-Path ([Environment]::GetFolderPath("Desktop")) "J and R Construction Manager"
}
$py = Join-Path $InstallDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "py" }
$code = @"
from pathlib import Path
from app.emergency_access import seed_mastery_key_on_install
p = seed_mastery_key_on_install(Path(r'$InstallDir'), r'$Password')
print('Wrote', p)
"@
Push-Location $InstallDir
try {
    if ($py -eq "py") { & py -3 -c $code } else { & $py -c $code }
} finally { Pop-Location }
