# Full log/sync — standards both ways, office CSVs, dashboard, sync log.
# Run on PC after phone field work. Desktop Cursor: say "log" or "sync".
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
Push-Location $RepoRoot
& $py -m app.workspace_sync
$code = $LASTEXITCODE
Pop-Location
exit $code
