$ErrorActionPreference = "Stop"
$PackageDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File (Join-Path $PackageDir "install_jr_job_manager_ui.ps1")
