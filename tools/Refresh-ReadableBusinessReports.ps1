# Wrapper for PC Cursor workspace (tools/) — calls scripts/ implementation.
$script = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\scripts\Refresh-ReadableBusinessReports.ps1"
& powershell -NoProfile -ExecutionPolicy Bypass -File $script @args
