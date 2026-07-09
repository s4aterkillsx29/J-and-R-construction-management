# Rebuild 00_START_HERE/READABLE reports from dropbox-records office CSVs.
param(
    [string]$BusinessRoot = "",
    [string]$DropboxRecords = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Resolve-BusinessRoot {
    param([string]$Override)
    if ($Override -and (Test-Path -LiteralPath $Override)) { return $Override }
    foreach ($p in @(
        $env:JRC_DROPBOX_BUSINESS_ROOT,
        "C:\Users\enrag\Dropbox\All Files\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22",
        (Join-Path $env:USERPROFILE "Dropbox\All Files\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22")
    )) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    return $null
}

function Resolve-DropboxRecords {
    param([string]$Override)
    if ($Override -and (Test-Path -LiteralPath $Override)) { return $Override }
    foreach ($p in @(
        $env:JRC_DROPBOX_RECORDS,
        "c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records",
        (Join-Path $env:USERPROFILE "Dropbox\dropbox-records")
    )) {
        $reg = Join-Path $p "08_Admin_Standards\JRC_JOB_RELATION_REGISTER.csv"
        if (Test-Path -LiteralPath $reg) { return $p }
    }
    return $null
}

$root = Resolve-BusinessRoot -Override $BusinessRoot
if (-not $root) {
    Write-Error "Business root not found. Run Sync-JRCBusinessFolders.ps1 first or set JRC_DROPBOX_BUSINESS_ROOT."
}

$records = Resolve-DropboxRecords -Override $DropboxRecords
$readable = Join-Path $root "00_START_HERE\READABLE"
New-Item -ItemType Directory -Force -Path $readable | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$lines = @(
    "J & R CONSTRUCTION — BUSINESS DASHBOARD (READABLE)",
    "Updated: $stamp",
    "",
    "Source: Dropbox office records (not GitHub)",
    ""
)

if ($records) {
    $regPath = Join-Path $records "08_Admin_Standards\JRC_JOB_RELATION_REGISTER.csv"
    if (Test-Path -LiteralPath $regPath) {
        $lines += "--------------------------------------------------------------------------------"
        $lines += "JOB REGISTER (from office CSV)"
        $lines += "--------------------------------------------------------------------------------"
        $rows = Import-Csv -LiteralPath $regPath
        foreach ($row in $rows) {
            $code = $row.Job_Code
            if (-not $code -or $code -in @("JRC-ADM", "JRC-GEN")) { continue }
            $cust = $row.Customer
            $addr = $row.Address
            $status = $row.Status
            $lines += "  $code — $cust — $addr — $status"
        }
        $lines += ""
    }

    $payroll = Join-Path $records "05_Helper_Pay_Workers\Payroll_Helper_Register.csv"
    if (Test-Path -LiteralPath $payroll) {
        $lines += "--------------------------------------------------------------------------------"
        $lines += "PAYROLL REGISTER (latest rows)"
        $lines += "--------------------------------------------------------------------------------"
        $prows = Import-Csv -LiteralPath $payroll | Select-Object -Last 8
        foreach ($p in $prows) {
            $lines += "  $($p.Worker) — $($p.Job) — $($p.Amount) — $($p.'Date/Timing')"
        }
        $lines += ""
    }
} else {
    $lines += "(dropbox-records not found — run Sync-JRCBusinessFolders.ps1 on office PC)"
    $lines += ""
}

$lines += @(
    "--------------------------------------------------------------------------------",
    "PHONE CURSOR QUICK CHECK",
    "--------------------------------------------------------------------------------",
    "  00_START_HERE/JRC-315_LILY_FENCE_QUOTE_CURRENT.txt  ->  `$10,440 fence quote (251 LF)",
    "  00_START_HERE/PHONE_CURSOR_DROPBOX_WORKSPACE.txt     ->  full phone setup",
    "",
    "After phone session on desktop:",
    "  1. This script (Refresh-ReadableBusinessReports.ps1)",
    "  2. Sync-JRCBusinessFolders.ps1",
    "  3. Construction Manager -> Office Records Sync",
    "  4. Tell desktop Cursor: log"
)

$out = Join-Path $readable "BUSINESS_DASHBOARD.txt"
$lines | Set-Content -Path $out -Encoding UTF8

Write-Host "=== Refresh-ReadableBusinessReports ===" -ForegroundColor Cyan
Write-Host "Wrote: $out"
Write-Host "Jobs listed: $(($lines | Select-String '—').Count)"

# Optional: run office sync via Python if install present
$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
if ($records) {
    $env:JRC_DROPBOX_RECORDS = $records
    Write-Host "Running office records sync..."
    Push-Location $RepoRoot
    try {
        & $py -m app.office_records_sync 2>&1 | ForEach-Object { Write-Host $_ }
    } finally {
        Pop-Location
    }
}
