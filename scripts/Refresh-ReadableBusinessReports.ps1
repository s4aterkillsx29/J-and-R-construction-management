# Rebuild READABLE reports inside the ONE unified workspace.
param([string]$WorkspaceRoot = "")

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$WorkspaceName = "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"

function Resolve-WorkspaceRoot {
    param([string]$Override)
    if ($Override -and (Test-Path -LiteralPath $Override)) { return $Override }
    foreach ($p in @(
        $env:JRC_WORKSPACE_ROOT,
        $env:JRC_DROPBOX_BUSINESS_ROOT,
        "C:\Users\enrag\Dropbox\All Files\$WorkspaceName\$WorkspaceName"
    )) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    return $null
}

$root = Resolve-WorkspaceRoot -Override $WorkspaceRoot
if (-not $root) {
    Write-Error "Run Sync-JRCBusinessFolders.ps1 first."
}

$readable = Join-Path $root "00_START_HERE\READABLE"
New-Item -ItemType Directory -Force -Path $readable | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$lines = @(
    "J & R CONSTRUCTION — BUSINESS DASHBOARD (READABLE)",
    "Updated: $stamp",
    "Workspace: $root",
    "",
    "ONE folder for phone Cursor, office CSVs, quotes, and Manager.",
    ""
)

$regPath = Join-Path $root "08_Admin_Standards\JRC_JOB_RELATION_REGISTER.csv"
if (Test-Path -LiteralPath $regPath) {
    $lines += "ACTIVE JOBS"
    Import-Csv -LiteralPath $regPath | ForEach-Object {
        if ($_.Job_Code -and $_.Job_Code -notin @("JRC-ADM", "JRC-GEN")) {
            $lines += "  $($_.Job_Code) — $($_.Customer) — $($_.Address) — $($_.Status)"
        }
    }
    $lines += ""
}

$lines += @(
    "PHONE VERIFY: 00_START_HERE/JRC-315_LILY_FENCE_QUOTE_CURRENT.txt -> `$13,890",
    "After phone work: Sync-JRCBusinessFolders.ps1, this script, Office Records Sync, then tell desktop Cursor: log"
)

$out = Join-Path $readable "BUSINESS_DASHBOARD.txt"
$lines | Set-Content -Path $out -Encoding UTF8
Write-Host "Wrote $out"

$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:JRC_WORKSPACE_ROOT = $root
$env:JRC_DROPBOX_RECORDS = $root
Push-Location $RepoRoot
& $py -m app.office_records_sync
Pop-Location
