# Full log/sync pipeline (phone → Dropbox → PC refresh).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
Push-Location $RepoRoot
& $py -m app.workspace_sync
exit $LASTEXITCODE
