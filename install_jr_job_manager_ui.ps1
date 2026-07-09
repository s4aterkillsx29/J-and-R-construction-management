# JRC Construction Manager v7.7 - Installer with UI, progress bar, and pre-install auth verification.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$AppName = "J and R Construction Manager"
$Version = "7.11.0 Unified Dashboard & Access Control Edition"
$PackageDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:AuthVerified = $false
$script:AuthInfo = $null
function Get-JrcDesktopPath {
    try {
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
function Get-OwnerInstallDir { Join-Path (Get-JrcDesktopPath) "J and R Construction Manager" }
function Get-WorkerInstallDir { Join-Path $env:LOCALAPPDATA "J_and_R_Construction_Manager" }
# Owner Master PC: program + business data live on Desktop (visible local folder).
# Worker/Remote: lightweight client in AppData only.
$InstallDir = Get-OwnerInstallDir
$LogDir = Join-Path $PackageDir "logs"
$BackupRoot = Join-Path $InstallDir "backups"
$ArchiveRoot = Join-Path $BackupRoot "archived_old_installs"
$PreserveNames = @("data","exports","evidence","chatgpt_imports","backups","logs","business_standards","file_sources","uploads")
$OldInstallNames = @("J_and_R_Construction_Manager","JR_Job_Manager_Pro","J_R_Job_Manager_Pro","J_and_R_Job_Manager_Pro","JRC_Job_Manager","JR_Construction_Manager")
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ArchiveRoot | Out-Null
$Stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$LogPath = Join-Path $LogDir ("install_v7_1_" + $Stamp + ".log")
$ReportPath = Join-Path $LogDir ("update_troubleshooting_report_v7_1_" + $Stamp + ".txt")
function Add-Log($msg){
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
    Add-Content -Path $ReportPath -Value $line -Encoding UTF8
    if($script:InstallJournalPath -and (Test-Path (Split-Path $script:InstallJournalPath -Parent))){
        Add-Content -Path $script:InstallJournalPath -Value $line -Encoding UTF8
    }
    if($script:LogBox){ $script:LogBox.AppendText($line + [Environment]::NewLine) }
    [System.Windows.Forms.Application]::DoEvents()
}
function Write-SetupJournal($InstallRoot, $Category, $Level, $Message){
    if(-not $InstallRoot){ return }
    $py = Get-InstallerPython $PackageDir
    $wd = if(Test-Path (Join-Path $PackageDir "app\install_setup_log.py")){ $PackageDir } else { $InstallRoot }
    try {
        & $py -m app.install_setup_log --install-dir $InstallRoot --log $Category $Level $Message 2>$null | Out-Null
    } catch { Add-Log "Setup journal note failed: $($_.Exception.Message)" }
}
function Mark-SetupStep($InstallRoot, $Step, $Status){
    if(-not $InstallRoot){ return }
    $py = Get-InstallerPython $PackageDir
    $wd = if(Test-Path (Join-Path $PackageDir "app\install_setup_log.py")){ $PackageDir } else { $InstallRoot }
    try {
        & $py -m app.install_setup_log --install-dir $InstallRoot --step $Step $Status 2>$null | Out-Null
    } catch { }
}
function Write-SetupReport($InstallRoot){
    if(-not $InstallRoot){ return $null }
    $py = Get-InstallerPython $PackageDir
    $wd = if(Test-Path (Join-Path $PackageDir "app\install_setup_log.py")){ $PackageDir } else { $InstallRoot }
    try {
        & $py -m app.install_setup_log --install-dir $InstallRoot --write-report 2>$null | Out-Null
        return (Join-Path $InstallRoot "INSTALL_SETUP_REPORT.txt")
    } catch { Add-Log "Could not write setup report: $($_.Exception.Message)"; return $null }
}
function Invoke-PostSetupWizard($InstallRoot, [string]$Profile){
    $py = Get-InstallerPython $InstallRoot
    if(-not(Test-Path (Join-Path $InstallRoot "app\install_post_setup_wizard.py"))){
        $py = Get-InstallerPython $PackageDir
        $InstallRoot = $PackageDir
    }
    try {
        Start-Process $py -ArgumentList @("-m","app.install_post_setup_wizard","--install-dir",$InstallRoot,"--profile",$Profile) -WorkingDirectory $InstallRoot -WindowStyle Normal | Out-Null
        Add-Log "Opened post-install setup wizard."
        return $true
    } catch {
        Add-Log "Post-install wizard could not open: $($_.Exception.Message)"
        return $false
    }
}
function Update-InstallButtonState {
    if($ownerRadio.Checked){
        if($script:AuthVerified){
            $installBtn.Enabled = $true
            $installBtn.Text = "Install / Update"
            $installBtn.BackColor = [System.Drawing.Color]::FromArgb(132,204,22)
        } else {
            $installBtn.Enabled = $false
            $installBtn.Text = "Install (verify login first)"
            $installBtn.BackColor = [System.Drawing.Color]::FromArgb(75,85,99)
        }
    } else {
        $installBtn.Enabled = $true
        $installBtn.Text = "Install Worker Client"
        $installBtn.BackColor = [System.Drawing.Color]::FromArgb(132,204,22)
    }
}
function Set-Status($msg, $pct){
    if($script:StatusLabel){ $script:StatusLabel.Text = $msg }
    if($script:ProgressBar){ $script:ProgressBar.Value = [Math]::Max(0,[Math]::Min(100,$pct)) }
    Add-Log $msg
}
function Ensure-Dir($path){ if(-not(Test-Path -LiteralPath $path)){ New-Item -ItemType Directory -Force -Path $path | Out-Null } }
function Safe-Remove($path){
    if(Test-Path -LiteralPath $path){
        try { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop; Add-Log "Removed old program item: $path" }
        catch { Add-Log "Could not remove old item: $path -- $($_.Exception.Message)" }
    }
}
function Copy-FolderContents($src,$dst){
    if(Test-Path -LiteralPath $src){
        Ensure-Dir $dst
        try { Copy-Item -LiteralPath (Join-Path $src '*') -Destination $dst -Recurse -Force -ErrorAction SilentlyContinue; Add-Log "Migrated/preserved data from $src to $dst" }
        catch { Add-Log "Could not migrate some data from $src -- $($_.Exception.Message)" }
    }
}
function Archive-Dir($src,$label){
    if(Test-Path -LiteralPath $src){
        $safeLabel = ($label -replace '[^A-Za-z0-9_\-]','_')
        $dst = Join-Path $ArchiveRoot ($safeLabel + '_' + $Stamp)
        try { Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force -ErrorAction Stop; Add-Log "Archived old install/copy: $src -> $dst"; return $dst }
        catch { Add-Log "Could not archive $src -- $($_.Exception.Message)"; return $null }
    }
    return $null
}
function Create-Shortcut($shortcutPath, $targetPath, $workingDir, $iconPath, $description){
    $wsh = New-Object -ComObject WScript.Shell
    $lnk = $wsh.CreateShortcut($shortcutPath)
    $lnk.TargetPath = $targetPath
    $lnk.WorkingDirectory = $workingDir
    if($description){ $lnk.Description = $description } else { $lnk.Description = "J and R Construction Manager" }
    if(Test-Path -LiteralPath $iconPath){ $lnk.IconLocation = "$iconPath,0" }
    $lnk.Save()
    Add-Log "Shortcut created: $shortcutPath"
}
function Ensure-ShortcutIcons(){
    $icon = Join-Path $PackageDir "assets\jrc_manager_app.ico"
    if(Test-Path -LiteralPath $icon){ return }
    $gen = Join-Path $PackageDir "scripts\generate_shortcut_icons.py"
    if(-not(Test-Path -LiteralPath $gen)){ Add-Log "Icon generator not found; shortcuts will use default Windows icons."; return }
    $py = Join-Path $PackageDir ".venv\Scripts\python.exe"
    try {
        if(Test-Path -LiteralPath $py){ & $py $gen | Out-Null } else { py -3 $gen | Out-Null }
        Add-Log "Generated modern shortcut icons for Windows 11."
    } catch { Add-Log "Could not generate icons: $($_.Exception.Message)" }
}
function Find-OldInstalls(){
    $found = New-Object System.Collections.Generic.List[string]
    $bases = @(Get-JrcDesktopPath, $env:LOCALAPPDATA, (Join-Path $env:APPDATA ""), (Join-Path $env:USERPROFILE "Documents")) | Where-Object { $_ -and (Test-Path $_) }
    $names = $OldInstallNames
    foreach($b in $bases){
        foreach($name in $names){
            $p = Join-Path $b $name
            $norm = (Resolve-Path -LiteralPath $p -ErrorAction SilentlyContinue).Path
            $cur = (Resolve-Path -LiteralPath $InstallDir -ErrorAction SilentlyContinue).Path
            if((Test-Path -LiteralPath $p) -and ($found -notcontains $p) -and ($norm -ne $cur)){
                $found.Add($p)
            }
        }
    }
    return $found
}
function Clean-Shortcuts(){
    $desktop=[Environment]::GetFolderPath("Desktop")
    $startMenu=Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
    $names=@("J&R Job Manager Pro.lnk","J and R Job Manager Pro.lnk","J and R Construction Manager - Best Host Server.lnk","J and R Construction Manager - Public Host Mode.lnk","J and R Construction Manager - Local LAN Host.lnk","J and R Construction Manager - System Check.lnk","J and R Manager Backup.lnk","Uninstall J and R Construction Manager.lnk","JRC System Check.lnk","JRC Shared Host.lnk","JRC Local Program Folder.lnk","JRC Program Folder.lnk","J and R Construction Manager - Network Server.lnk","J and R Construction Manager - Open Browser.lnk")
    foreach($n in $names){
        foreach($loc in @($desktop,$startMenu)){
            $p=Join-Path $loc $n
            if(Test-Path -LiteralPath $p){ try{ Remove-Item -LiteralPath $p -Force; Add-Log "Removed old shortcut: $p" } catch{ Add-Log "Could not remove shortcut: $p" } }
        }
    }
}

function Get-ResolvedInstallDir([bool]$OwnerMaster){
    if($OwnerMaster){ return Get-OwnerInstallDir }
    return Get-WorkerInstallDir
}
function Get-InstallerPython($BaseDir){
    foreach($rel in @(".venv\Scripts\python.exe",".venv\Scripts\pythonw.exe")){
        $p = Join-Path $BaseDir $rel
        if(Test-Path -LiteralPath $p){ return $p }
    }
    foreach($rel in @((Join-Path $PackageDir ".venv\Scripts\python.exe"), "py.exe", "python.exe")){
        if(Test-Path -LiteralPath $rel){ return $rel }
    }
    return "py.exe"
}
function Read-InstallAuth($BaseDir){
    $path = Join-Path $BaseDir "data\install_auth.json"
    if(-not(Test-Path -LiteralPath $path)){ return $null }
    try { return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}
function Invoke-InstallerAuth([bool]$OwnerMaster){
    $target = Get-ResolvedInstallDir $OwnerMaster
    Ensure-Dir $target
    Ensure-Dir (Join-Path $target "data")
    $profile = if($OwnerMaster){ "OwnerMaster" } else { "WorkerClient" }
    $py = Get-InstallerPython $PackageDir
    $wd = if(Test-Path (Join-Path $PackageDir "app\installer_auth.py")){ $PackageDir } else { $target }
    Add-Log "Running installer authentication for profile $profile on $target"
    $args = @("-m","app.installer_auth","--install-dir",$target,"--profile",$profile)
    try {
        $proc = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $wd -Wait -PassThru -WindowStyle Normal
        Add-Log "Installer auth finished with exit code $($proc.ExitCode)"
        if($proc.ExitCode -ne 0){ return $false }
    } catch {
        Add-Log "Installer auth failed: $($_.Exception.Message)"
        return $false
    }
    $auth = Read-InstallAuth $target
    if($auth -and $auth.verified){
        $script:AuthVerified = $true
        $script:AuthInfo = $auth
        if($OwnerMaster -and $auth.role -ne "admin"){
            Add-Log "Owner install requires admin role; got $($auth.role)"
            $script:AuthVerified = $false
            return $false
        }
        Add-Log "Auth verified for $($auth.username) role=$($auth.role)"
        $script:StatusLabel.Text = "Step 2 complete — Verified: $($auth.username) ($($auth.role)). Install / Update runs automatically."
        Write-SetupJournal $target "Auth" "INFO" "Verified $($auth.username) role=$($auth.role)"
        Mark-SetupStep $target "verify_login" "ok"
        Update-InstallButtonState
        return $true
    }
    return $false
}
function Launch-LoginGateVisible($BaseDir){
    $setup = Join-Path $BaseDir "app\local_login_gate.py"
    if(-not(Test-Path -LiteralPath $setup)){ return $false }
    $py = Join-Path $BaseDir ".venv\Scripts\pythonw.exe"
    if(-not(Test-Path $py)){ $py = Join-Path $BaseDir ".venv\Scripts\python.exe" }
    if(-not(Test-Path $py)){ $py = Get-InstallerPython $BaseDir }
    try {
        if((Split-Path -Leaf $py) -match "^python"){
            Start-Process $py -ArgumentList "-m","app.local_login_gate" -WorkingDirectory $BaseDir -WindowStyle Normal | Out-Null
        } else {
            Start-Process $py -ArgumentList "-3","-m","app.local_login_gate" -WorkingDirectory $BaseDir -WindowStyle Normal | Out-Null
        }
        Add-Log "Opened Secure Local Login (visible window)."
        return $true
    } catch {
        Add-Log "Could not open Secure Local Login: $($_.Exception.Message)"
        return $false
    }
}

function Open-ExistingSecureLoginCheck(){
    $target = Get-ResolvedInstallDir $ownerRadio.Checked
    Mark-SetupStep $target "choose_profile" $(if($ownerRadio.Checked){"ok"}else{"ok"})
    Write-SetupJournal $target "Installer" "INFO" $(if($ownerRadio.Checked){"Owner Master profile selected"}else{"Worker client profile selected"})
    if(Invoke-InstallerAuth $ownerRadio.Checked){
        if($ownerRadio.Checked){
            [System.Windows.Forms.MessageBox]::Show(
                "Step 2 complete — login verified.`n`nUser: $($script:AuthInfo.username)`nRole: $($script:AuthInfo.role)`n`nInstall / Update (Step 3) starts automatically now.",
                "Authentication Verified","OK","Information") | Out-Null
            $script:StatusLabel.Text = "Step 3 — Install / Update running automatically after verification..."
            $installBtn.PerformClick()
        } else {
            [System.Windows.Forms.MessageBox]::Show(
                "Worker client profile selected.`n`nClick Install Worker Client when ready.`n`nCustomers never use this installer — they use Jacob's web link only.",
                "Worker Client","OK","Information") | Out-Null
        }
    } else {
        [System.Windows.Forms.MessageBox]::Show(
            "Step 2 not finished.`n`nOwner PC: verify admin login OR create first owner.`n`nWorker PC: click Install Worker Client (no local login needed).`n`nCustomers: do not install — use web link from Jacob.",
            "Authentication Required","OK","Warning") | Out-Null
    }
}

$form=New-Object System.Windows.Forms.Form
$form.Text="$AppName Installer"
$form.Width=880; $form.Height=735; $form.StartPosition="CenterScreen"; $form.FormBorderStyle="FixedDialog"; $form.MaximizeBox=$false
$form.BackColor=[System.Drawing.Color]::FromArgb(0,0,0)
$form.Font=New-Object System.Drawing.Font("Segoe UI",10)
$title=New-Object System.Windows.Forms.Label
$title.Text="J and R Construction Manager"
$title.ForeColor=[System.Drawing.Color]::FromArgb(163,230,53)
$title.Font=New-Object System.Drawing.Font("Segoe UI",24,[System.Drawing.FontStyle]::Bold)
$title.AutoSize=$true; $title.Location=New-Object System.Drawing.Point(24,18); $form.Controls.Add($title)
$sub=New-Object System.Windows.Forms.Label
$sub.Text="v$Version - black/lime secure install | owner master PC or worker client (no business data on worker PCs)"
$sub.ForeColor=[System.Drawing.Color]::FromArgb(163,163,163)
$sub.AutoSize=$true; $sub.Location=New-Object System.Drawing.Point(28,68); $form.Controls.Add($sub)
$profileLabel=New-Object System.Windows.Forms.Label
$profileLabel.Text="Install profile:"
$profileLabel.ForeColor=[System.Drawing.Color]::FromArgb(132,204,22)
$profileLabel.AutoSize=$true; $profileLabel.Location=New-Object System.Drawing.Point(28,92); $form.Controls.Add($profileLabel)
$ownerRadio=New-Object System.Windows.Forms.RadioButton
$ownerRadio.Text="Owner Master PC (Desktop local folder — full business data)"
$ownerRadio.ForeColor=[System.Drawing.Color]::White; $ownerRadio.Checked=$true
$ownerRadio.AutoSize=$true; $ownerRadio.Location=New-Object System.Drawing.Point(130,90); $form.Controls.Add($ownerRadio)
$workerRadio=New-Object System.Windows.Forms.RadioButton
$workerRadio.Text="Worker / Remote Client (app only — NO business files copied to this PC)"
$workerRadio.ForeColor=[System.Drawing.Color]::FromArgb(200,200,200)
$workerRadio.AutoSize=$true; $workerRadio.Location=New-Object System.Drawing.Point(130,112); $form.Controls.Add($workerRadio)
$customerNote=New-Object System.Windows.Forms.Label
$customerNote.Text="Customers / remote users: do NOT run this installer — Jacob shares a browser link (/register or /mobile) after the host is running."
$customerNote.ForeColor=[System.Drawing.Color]::FromArgb(250,204,21)
$customerNote.Font=New-Object System.Drawing.Font("Segoe UI",9,[System.Drawing.FontStyle]::Bold)
$customerNote.AutoSize=$false; $customerNote.Size=New-Object System.Drawing.Size(820,34)
$customerNote.Location=New-Object System.Drawing.Point(28,132); $form.Controls.Add($customerNote)
$stepGuide=New-Object System.Windows.Forms.Label
$stepGuide.Text="Step 1: Choose profile   |   Step 2: Verify Login → auto Install/Update (Owner)   |   Step 4: Setup wizard"
$stepGuide.ForeColor=[System.Drawing.Color]::FromArgb(163,230,53)
$stepGuide.AutoSize=$true; $stepGuide.Location=New-Object System.Drawing.Point(28,168); $form.Controls.Add($stepGuide)
$panel=New-Object System.Windows.Forms.Panel
$panel.BackColor=[System.Drawing.Color]::FromArgb(17,17,17)
$panel.Location=New-Object System.Drawing.Point(24,188); $panel.Size=New-Object System.Drawing.Size(820,346); $form.Controls.Add($panel)
$script:StatusLabel=New-Object System.Windows.Forms.Label
$script:StatusLabel.Text="Step 1: Choose Owner or Worker profile. Step 2: Verify Login (Owner only)."
$script:StatusLabel.ForeColor=[System.Drawing.Color]::FromArgb(226,232,240)
$script:StatusLabel.Font=New-Object System.Drawing.Font("Segoe UI",12,[System.Drawing.FontStyle]::Bold)
$script:StatusLabel.AutoSize=$false; $script:StatusLabel.Location=New-Object System.Drawing.Point(18,16); $script:StatusLabel.Size=New-Object System.Drawing.Size(780,30); $panel.Controls.Add($script:StatusLabel)
$script:ProgressBar=New-Object System.Windows.Forms.ProgressBar
$script:ProgressBar.Location=New-Object System.Drawing.Point(18,55); $script:ProgressBar.Size=New-Object System.Drawing.Size(780,24); $script:ProgressBar.Minimum=0; $script:ProgressBar.Maximum=100; $panel.Controls.Add($script:ProgressBar)
$script:LogBox=New-Object System.Windows.Forms.TextBox
$script:LogBox.Multiline=$true; $script:LogBox.ReadOnly=$true; $script:LogBox.ScrollBars="Vertical"
$script:LogBox.BackColor=[System.Drawing.Color]::FromArgb(10,10,10)
$script:LogBox.ForeColor=[System.Drawing.Color]::FromArgb(163,230,53)
$script:LogBox.Font=New-Object System.Drawing.Font("Consolas",9)
$script:LogBox.Location=New-Object System.Drawing.Point(18,92); $script:LogBox.Size=New-Object System.Drawing.Size(780,265); $panel.Controls.Add($script:LogBox)
$installBtn=New-Object System.Windows.Forms.Button
$installBtn.Text="Install / Update"
$installBtn.BackColor=[System.Drawing.Color]::FromArgb(132,204,22)
$installBtn.ForeColor=[System.Drawing.Color]::Black
$installBtn.FlatStyle="Flat"
$installBtn.Font=New-Object System.Drawing.Font("Segoe UI",12,[System.Drawing.FontStyle]::Bold)
$preLoginBtn=New-Object System.Windows.Forms.Button
$preLoginBtn.Text="Step 2 — Verify Login / Create Owner"
$preLoginBtn.BackColor=[System.Drawing.Color]::FromArgb(168,85,247); $preLoginBtn.ForeColor=[System.Drawing.Color]::White; $preLoginBtn.FlatStyle="Flat"
$preLoginBtn.Font=New-Object System.Drawing.Font("Segoe UI",11,[System.Drawing.FontStyle]::Bold)
$preLoginBtn.Location=New-Object System.Drawing.Point(24,550); $preLoginBtn.Size=New-Object System.Drawing.Size(280,42); $form.Controls.Add($preLoginBtn)
$preLoginBtn.Add_Click({ Open-ExistingSecureLoginCheck })
$ownerRadio.Add_CheckedChanged({ Update-InstallButtonState })
$workerRadio.Add_CheckedChanged({ Update-InstallButtonState })
$installBtn.Location=New-Object System.Drawing.Point(24,615); $installBtn.Size=New-Object System.Drawing.Size(200,42); $form.Controls.Add($installBtn)
$openBtn=New-Object System.Windows.Forms.Button
$openBtn.Text="Open Install Folder"
$openBtn.BackColor=[System.Drawing.Color]::FromArgb(51,65,85); $openBtn.ForeColor=[System.Drawing.Color]::White; $openBtn.FlatStyle="Flat"
$openBtn.Location=New-Object System.Drawing.Point(220,615); $openBtn.Size=New-Object System.Drawing.Size(180,42); $form.Controls.Add($openBtn)
$reportBtn=New-Object System.Windows.Forms.Button
$reportBtn.Text="Open Report"
$reportBtn.BackColor=[System.Drawing.Color]::FromArgb(96,165,250); $reportBtn.ForeColor=[System.Drawing.Color]::FromArgb(3,17,30); $reportBtn.FlatStyle="Flat"
$reportBtn.Location=New-Object System.Drawing.Point(416,615); $reportBtn.Size=New-Object System.Drawing.Size(140,42); $form.Controls.Add($reportBtn)
$launchBtn=New-Object System.Windows.Forms.Button
$launchBtn.Text="Open Setup/Login"
$launchBtn.BackColor=[System.Drawing.Color]::FromArgb(37,99,235); $launchBtn.ForeColor=[System.Drawing.Color]::White; $launchBtn.FlatStyle="Flat"
$launchBtn.Location=New-Object System.Drawing.Point(572,615); $launchBtn.Size=New-Object System.Drawing.Size(140,42); $form.Controls.Add($launchBtn)
$closeBtn=New-Object System.Windows.Forms.Button
$closeBtn.Text="Close"
$closeBtn.BackColor=[System.Drawing.Color]::FromArgb(71,85,105); $closeBtn.ForeColor=[System.Drawing.Color]::White; $closeBtn.FlatStyle="Flat"
$closeBtn.Location=New-Object System.Drawing.Point(724,615); $closeBtn.Size=New-Object System.Drawing.Size(120,42); $form.Controls.Add($closeBtn)
$openBtn.Add_Click({ if(Test-Path $InstallDir){ Start-Process explorer.exe $InstallDir } })
$reportBtn.Add_Click({ if(Test-Path $ReportPath){ Start-Process notepad.exe $ReportPath } else { [System.Windows.Forms.MessageBox]::Show("No report yet. Run Install / Update first.") | Out-Null } })
$launchBtn.Add_Click({ $dir = Get-ResolvedInstallDir $ownerRadio.Checked; if(Launch-LoginGateVisible $dir){ } else { [System.Windows.Forms.MessageBox]::Show("Install first or verify login from the package folder, then open setup/login again.") | Out-Null } })
$closeBtn.Add_Click({ $form.Close() })
$installBtn.Add_Click({
    $installBtn.Enabled=$false
    try{
        $isOwnerMaster = $ownerRadio.Checked
        if($isOwnerMaster){
            $InstallDir = Get-OwnerInstallDir
            Add-Log "Install profile: Owner Master PC — local folder on Desktop: $InstallDir"
            if(-not $script:AuthVerified){
                if(-not (Invoke-InstallerAuth $true)){
                    [System.Windows.Forms.MessageBox]::Show("Owner Master PC install requires verified admin login first.`n`nClick Verify Login / Create Owner, then Install / Update.","Authentication Required","OK","Warning") | Out-Null
                    return
                }
            }
        } else {
            $InstallDir = Get-WorkerInstallDir
            Add-Log "Install profile: Worker/Remote Client — NO business database or files on this PC."
            if(-not $script:AuthVerified){ Invoke-InstallerAuth $false | Out-Null }
        }
        $LogDir = Join-Path $InstallDir "logs"
        $BackupRoot = Join-Path $InstallDir "backups"
        $ArchiveRoot = Join-Path $BackupRoot "archived_old_installs"
        Ensure-Dir $LogDir; Ensure-Dir $BackupRoot; Ensure-Dir $ArchiveRoot
        $script:InstallJournalPath = Join-Path $LogDir "install_setup_journal.log"
        Write-SetupJournal $InstallDir "Installer" "INFO" "Install/update started"
        Mark-SetupStep $InstallDir "choose_profile" "ok"
        Mark-SetupStep $InstallDir "install_files" "in_progress"
        $legacyAppData = Get-WorkerInstallDir
        if($isOwnerMaster -and $InstallDir -ne $legacyAppData -and (Test-Path -LiteralPath $legacyAppData)){
            Add-Log "Migrating prior AppData install to Desktop local folder..."
            foreach($name in $PreserveNames){ Copy-FolderContents (Join-Path $legacyAppData $name) (Join-Path $InstallDir $name) }
        }
        Set-Status "Preflight: detecting old installs and folders" 5
        Ensure-Dir $InstallDir; Ensure-Dir $BackupRoot; Ensure-Dir $ArchiveRoot; Ensure-Dir $LogDir
        Add-Log "Package folder: $PackageDir"
        Add-Log "Primary install folder: $InstallDir"
        $found = Find-OldInstalls
        foreach($p in $found){ Add-Log "Detected install/copy: $p" }
        Set-Status "Creating and preserving business data folders" 12
        if($isOwnerMaster){ foreach($name in $PreserveNames){ Ensure-Dir (Join-Path $InstallDir $name) } }
        else { Ensure-Dir (Join-Path $InstallDir "data"); Ensure-Dir (Join-Path $InstallDir "logs") }
        Set-Status "Backing up current database" 18
        $db=Join-Path $InstallDir "data\jr_business.db"
        if($isOwnerMaster -and (Test-Path -LiteralPath $db)){
            Copy-Item -LiteralPath $db -Destination (Join-Path $BackupRoot "jr_business_before_v7_1_update_$Stamp.db") -Force
            Add-Log "Database backup saved before update."
        } else { Add-Log $(if($isOwnerMaster){"No current database found at primary install. Starter database may be installed if packaged."}else{"Worker client: skipping local database backup."}) }
        Set-Status "Archiving and migrating old install copies" 30
        foreach($old in $found){
            if($old -ne $InstallDir){
                $arch = Archive-Dir $old (Split-Path -Leaf $old)
                if($isOwnerMaster){ foreach($name in $PreserveNames){ Copy-FolderContents (Join-Path $old $name) (Join-Path $InstallDir $name) } }
                try { Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction Stop; Add-Log "Removed old install folder after archive/migration: $old" }
                catch { Add-Log "Could not remove old folder $old -- $($_.Exception.Message)" }
            }
        }
        Set-Status "Archiving old program code inside current install" 42
        $codeArchive = Join-Path $ArchiveRoot ("current_program_code_before_v7_1_" + $Stamp)
        Ensure-Dir $codeArchive
        Get-ChildItem -Path $InstallDir -Force | Where-Object { $PreserveNames -notcontains $_.Name } | ForEach-Object {
            try { Move-Item -LiteralPath $_.FullName -Destination (Join-Path $codeArchive $_.Name) -Force -ErrorAction Stop; Add-Log "Archived old current item: $($_.Name)" }
            catch { Add-Log "Could not archive current item $($_.FullName) -- $($_.Exception.Message)" }
        }
        Set-Status "Copying latest program files" 58
        Get-ChildItem -Path $PackageDir -Force | Where-Object { $PreserveNames -notcontains $_.Name } | ForEach-Object {
            $dst=Join-Path $InstallDir $_.Name
            Safe-Remove $dst
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Recurse -Force
            Add-Log "Copied latest item: $($_.Name)"
        }
        Set-Status "Setting up Python runtime (venv + Flask, ReportLab, etc.)" 68
        Mark-SetupStep $InstallDir "runtime_setup" "in_progress"
        $runtimeBat = Join-Path $InstallDir "setup_runtime_env.bat"
        if(Test-Path -LiteralPath $runtimeBat){
            $proc = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "`"$runtimeBat`"") -WorkingDirectory $InstallDir -Wait -PassThru -WindowStyle Hidden
            Add-Log "setup_runtime_env.bat finished with exit code $($proc.ExitCode)"
            if($proc.ExitCode -ne 0){ Add-Log "WARNING: runtime setup returned non-zero exit. Run setup_runtime_env.bat manually if the app fails to start."; Mark-SetupStep $InstallDir "runtime_setup" "warn" }
            else { Mark-SetupStep $InstallDir "runtime_setup" "ok" }
        } else {
            Add-Log "setup_runtime_env.bat not found in package; run ensure_venv.bat manually after install."
        }
        if(-not(Test-Path -LiteralPath $db) -and $isOwnerMaster -and (Test-Path (Join-Path $PackageDir "data\jr_business.db"))){
            Copy-Item -LiteralPath (Join-Path $PackageDir "data\jr_business.db") -Destination $db -Force
            Add-Log "Starter database installed."
        }
        $profilePath = Join-Path $InstallDir "data\install_profile.json"
        $auth = Read-InstallAuth $InstallDir
        if($isOwnerMaster){
            @{
                profile = "OwnerMaster"
                allow_local_business_data = $true
                installed_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
                verified_user = $(if($auth){$auth.username}else{$null})
                verified_role = $(if($auth){$auth.role}else{"admin"})
                verified_at = $(if($auth){$auth.verified_at}else{(Get-Date -Format "yyyy-MM-dd HH:mm:ss")})
                note = "Master owner PC — full business data on this machine."
            } | ConvertTo-Json | Set-Content -Path $profilePath -Encoding UTF8
            foreach($sub in @("sessions_archive","state_memory","live_backup")){ Ensure-Dir (Join-Path $InstallDir "data\$sub") }
            Add-Log "Master storage folders created: sessions_archive, state_memory, live_backup"
            $pySeed = Join-Path $InstallDir ".venv\Scripts\python.exe"
            if(Test-Path -LiteralPath $pySeed){
                try {
                    & $pySeed -c "from pathlib import Path; from app.emergency_access import seed_mastery_key_on_install; seed_mastery_key_on_install(Path(r'$InstallDir'), 'ivygrows1')" 2>&1 | ForEach-Object { Add-Log $_ }
                    Add-Log "Owner emergency mastery key configured (data\local_secrets.env — not committed to git)."
                    Write-SetupJournal $InstallDir "EmergencyAccess" "INFO" "Owner emergency mastery key seeded on Owner Master PC."
                    Mark-SetupStep $InstallDir "emergency_access" "ok"
                    & $pySeed "$InstallDir\app\emergency_access_check.py" "$InstallDir" 2>&1 | ForEach-Object { Add-Log $_ }
                } catch { Add-Log "Could not seed emergency mastery key: $($_.Exception.Message)"; Mark-SetupStep $InstallDir "emergency_access" "error" }
            } else { Add-Log "Python venv not ready; run install again to seed owner emergency mastery key."; Mark-SetupStep $InstallDir "emergency_access" "warn" }
        } else {
            @{ profile = "WorkerClient"; allow_local_business_data = $false; installed_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss"); note = "Remote client — connect via host/cloud only. No business files stored without admin permission." } | ConvertTo-Json | Set-Content -Path $profilePath -Encoding UTF8
            if(Test-Path -LiteralPath $db){ Remove-Item -LiteralPath $db -Force -ErrorAction SilentlyContinue; Add-Log "Removed local business database from worker client install." }
        }
        Set-Content -Path (Join-Path $InstallDir "VERSION.txt") -Value "J and R Construction Manager v$Version" -Encoding ASCII
        Set-Content -Path (Join-Path $InstallDir "INSTALLER_SOURCE.txt") -Value $PackageDir -Encoding ASCII
        Set-Status "Preparing modern shortcut icons" 72
        Ensure-ShortcutIcons
        Set-Status "Cleaning old shortcuts" 75
        Clean-Shortcuts
        Set-Status "Creating desktop and Start Menu shortcuts for this user" 84
        $ensurePs1 = Join-Path $PackageDir "scripts\Ensure-DesktopShortcuts.ps1"
        if(Test-Path -LiteralPath $ensurePs1){
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $ensurePs1 -InstallDir $InstallDir -PackageDir $PackageDir -Quiet
            Add-Log "Desktop shortcuts ensured for user $env:USERNAME."
        } else {
            Add-Log "WARNING: Ensure-DesktopShortcuts.ps1 missing; shortcuts were not created automatically."
        }
        Mark-SetupStep $InstallDir "install_files" "ok"
        Set-Status "Initialize database, pipelines, and system check" 88
        $pyCheck = Join-Path $InstallDir ".venv\Scripts\python.exe"
        if(Test-Path -LiteralPath $pyCheck){
            try {
                & $pyCheck -m app.initialize_install 2>&1 | ForEach-Object { Add-Log $_ }
                Mark-SetupStep $InstallDir "db_initialize" "ok"
            } catch { Add-Log "initialize_install: $($_.Exception.Message)"; Mark-SetupStep $InstallDir "db_initialize" "warn" }
            try {
                & $pyCheck -m app.system_check 2>&1 | ForEach-Object { Add-Log $_ }
                Mark-SetupStep $InstallDir "system_check" "ok"
            } catch { Add-Log "system_check: $($_.Exception.Message)"; Mark-SetupStep $InstallDir "system_check" "warn" }
            try {
                & $pyCheck -m app.densus_jrc_admin 2>&1 | Out-Null
            } catch { }
            $densusAdmin = Join-Path $InstallDir "data\densus_admin"
            New-Item -ItemType Directory -Force -Path $densusAdmin,"$densusAdmin\snapshots","$densusAdmin\session_actions" | Out-Null
            Add-Log "Densus admin monitoring folder ready (separate from business data): $densusAdmin"
        }
        Set-Status "Writing install status and troubleshooting report" 94
        $marker = @"
Installed: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Version: $Version
Install folder: $InstallDir
Installer log: $LogPath
Troubleshooting report: $ReportPath
Old copies are archived under: $ArchiveRoot
Business data preserved: data, evidence, exports, backups, chatgpt_imports, business_standards, logs
Note: Installer verifies login before Owner Master installs. Default first-setup login is ivygrows / ivygrows on this PC only — change it immediately after setup.
Setup journal: $(Join-Path $InstallDir 'logs\install_setup_journal.log')
Setup report: $(Join-Path $InstallDir 'INSTALL_SETUP_REPORT.txt')
"@
        Set-Content -Path (Join-Path $InstallDir "INSTALL_LOCATION.txt") -Value $InstallDir -Encoding ASCII
        Set-Content -Path (Join-Path $InstallDir "INSTALL_STATUS.txt") -Value $marker -Encoding UTF8
        $setupReport = Write-SetupReport $InstallDir
        Add-Log "Install/update complete. Opening Secure Local Login and setup wizard."
        Set-Status "Step 4 — Setup wizard and login" 100
        Mark-SetupStep $InstallDir "post_login" "started"
        if($isOwnerMaster){ Launch-LoginGateVisible $InstallDir | Out-Null }
        $prof = if($isOwnerMaster){"OwnerMaster"}else{"WorkerClient"}
        Invoke-PostSetupWizard $InstallDir $prof | Out-Null
        $reportMsg = if($setupReport){"`nSetup report:`n$setupReport"}else{""}
        [System.Windows.Forms.MessageBox]::Show(
            "Install complete (Step 3 done). Step 4 setup wizard is opening now.`n`nVerified user: $(if($auth){$auth.username}else{'owner'})`nRole: $(if($auth){$auth.role}else{'admin'})$reportMsg`n`nCustomers never install this program — share web links only.",
            "J and R Construction Manager","OK","Information") | Out-Null
    } catch {
        Add-Log "ERROR: $($_.Exception.Message)"
        [System.Windows.Forms.MessageBox]::Show("Installer stopped: $($_.Exception.Message)\n\nLog/report saved here:\n$LogPath\n$ReportPath","Install Issue","OK","Warning") | Out-Null
    } finally { Update-InstallButtonState }
})
# Restore prior auth if reinstalling same folder
$existingTarget = Get-ResolvedInstallDir $true
$existingAuth = Read-InstallAuth $existingTarget
if($existingAuth -and $existingAuth.verified){
    $script:AuthVerified = $true
    $script:AuthInfo = $existingAuth
    Add-Log "Previous verified login found for $($existingAuth.username) — Step 2 already complete."
}
Update-InstallButtonState
Add-Log "Installer opened. Foolproof setup: Step 1 profile → Step 2 verify login → Step 3 install → Step 4 wizard."
[void]$form.ShowDialog()
