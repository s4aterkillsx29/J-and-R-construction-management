# Push local JRC changes to GitHub (run after each update session).
param(
    [string]$Message = "JRC update: black/lime UI, payments, secure install profiles",
    [string]$Branch = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not (Test-Path ".git")) {
    Write-Error "Not a git repository: $repo"
}

if (-not $Branch) {
    $Branch = (git branch --show-current).Trim()
    if (-not $Branch) { $Branch = "feature/v7.4-black-lime-secure" }
}

git add -A
$status = git status --porcelain
if (-not $status) {
    Write-Output "Nothing to commit."
    exit 0
}

git commit -m $Message
git push -u origin $Branch
Write-Output "Pushed to origin/$Branch"
