# Safe uninstaller for J and R Construction Manager
$ErrorActionPreference = "Stop"
$AppName = "J and R Construction Manager"
$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "============================================================" -ForegroundColor DarkGray
Write-Host " UNINSTALL J AND R CONSTRUCTION MANAGER" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor DarkGray
Write-Host "This removes program files and shortcuts only."
Write-Host "It will NOT delete your Dropbox folder or Dropbox cloud files." -ForegroundColor Green
Write-Host "A local safety backup of the database/exports/evidence will be created first."
$answer = Read-Host "Type UNINSTALL to continue"
if($answer -ne "UNINSTALL"){ Write-Host "Canceled."; exit 0 }
$desktop=[Environment]::GetFolderPath("Desktop")
$startMenu=Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
foreach($lnk in @("J and R Construction Manager.lnk","J and R Manager Backup.lnk","Uninstall J and R Construction Manager.lnk")){
  $p=Join-Path $desktop $lnk; if(Test-Path $p){ Remove-Item $p -Force }
}
$p=Join-Path $startMenu "J and R Construction Manager.lnk"; if(Test-Path $p){ Remove-Item $p -Force }
$stamp=Get-Date -Format "yyyy-MM-dd_HHmmss"
$backup=Join-Path ([Environment]::GetFolderPath("Desktop")) "J_and_R_Manager_Local_Backup_Before_Uninstall_$stamp.zip"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$temp=Join-Path $env:TEMP "JRC_Uninstall_Backup_$stamp"
New-Item -ItemType Directory -Force -Path $temp | Out-Null
foreach($d in @("data","exports","evidence","chatgpt_imports")){
  $src=Join-Path $InstallDir $d
  if(Test-Path $src){ Copy-Item $src (Join-Path $temp $d) -Recurse -Force }
}
[System.IO.Compression.ZipFile]::CreateFromDirectory($temp,$backup)
Remove-Item $temp -Recurse -Force
Write-Host "Local backup created: $backup" -ForegroundColor Green
# Keep backup outside install folder, then remove install folder.
Set-Location $env:USERPROFILE
Remove-Item $InstallDir -Recurse -Force
Write-Host "Program removed. Dropbox files were not touched." -ForegroundColor Green
