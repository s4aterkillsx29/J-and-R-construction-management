param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$PrinterName = 'Phoswift A42'
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path $Path)) { throw "File not found: $Path" }

$ext = [IO.Path]::GetExtension($Path).ToLowerInvariant()
$printer = Get-Printer -Name $PrinterName -ErrorAction SilentlyContinue
if (-not $printer) {
    $names = (Get-Printer -ErrorAction SilentlyContinue).Name -join ', '
    throw "Printer '$PrinterName' not found. Available: $names"
}

switch ($ext) {
    '.txt' {
        Get-Content $Path -Raw | Out-Printer -Name $PrinterName
    }
    default {
        Start-Process -FilePath $Path -Verb Print -Wait
    }
}
Write-Output "Sent to $PrinterName : $Path"
