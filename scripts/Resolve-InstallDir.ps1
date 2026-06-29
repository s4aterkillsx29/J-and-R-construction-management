# Returns the active JRC install directory (Desktop owner folder first).
param(
    [string]$Hint = "",
    [string]$Profile = "OwnerMaster"
)

function Get-JrcDesktopPath {
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        return [Environment]::GetFolderPath("Desktop")
    } catch {
        $home = $env:USERPROFILE
        foreach ($sub in @("OneDrive\Desktop", "Desktop")) {
            $p = Join-Path $home $sub
            if (Test-Path -LiteralPath $p) { return $p }
        }
        return Join-Path $home "Desktop"
    }
}

function Get-OwnerInstallDir {
    return Join-Path (Get-JrcDesktopPath) "J and R Construction Manager"
}

function Get-WorkerInstallDir {
    return Join-Path $env:LOCALAPPDATA "J_and_R_Construction_Manager"
}

function Resolve-JrcInstallDir([string]$HintPath, [string]$InstallProfile) {
    $candidates = @()
    if ($HintPath) { $candidates += $HintPath }
    if ($InstallProfile -eq "OwnerMaster") {
        $candidates += (Get-OwnerInstallDir)
    } else {
        $candidates += (Get-WorkerInstallDir)
    }
    $candidates += (Get-OwnerInstallDir)
    $candidates += (Get-WorkerInstallDir)
    foreach ($dir in $candidates | Select-Object -Unique) {
        if ($dir -and (Test-Path -LiteralPath (Join-Path $dir "app\network_server.py"))) {
            return $dir
        }
    }
    if ($InstallProfile -eq "OwnerMaster") { return (Get-OwnerInstallDir) }
    return (Get-WorkerInstallDir)
}

if ($Profile -eq "OwnerMaster") {
    Resolve-JrcInstallDir -HintPath $Hint -InstallProfile "OwnerMaster"
} else {
    Resolve-JrcInstallDir -HintPath $Hint -InstallProfile "WorkerClient"
}
