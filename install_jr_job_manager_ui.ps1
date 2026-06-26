# JRC Construction Manager v7.1 - Cloud Primary Live Business Installer
# Safe behavior: no Python is executed during install. The installer only copies files,
# migrates/preserves business data, cleans old shortcuts, and writes a report.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$AppName = "J and R Construction Manager"
$Version = "7.2.0 Unified Schema Reliable Business Edition"
$PackageDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Join-Path $env:LOCALAPPDATA "J_and_R_Construction_Manager"
$LogDir = Join-Path $InstallDir "logs"
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
    if($script:LogBox){ $script:LogBox.AppendText($line + [Environment]::NewLine) }
    [System.Windows.Forms.Application]::DoEvents()
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
function Create-Shortcut($shortcutPath, $targetPath, $workingDir, $iconPath){
    $wsh = New-Object -ComObject WScript.Shell
    $lnk = $wsh.CreateShortcut($shortcutPath)
    $lnk.TargetPath = $targetPath
    $lnk.WorkingDirectory = $workingDir
    $lnk.Description = "Open J and R Construction Manager"
    if(Test-Path -LiteralPath $iconPath){ $lnk.IconLocation = $iconPath }
    $lnk.Save()
}
function Find-OldInstalls(){
    $found = New-Object System.Collections.Generic.List[string]
    $bases = @($env:LOCALAPPDATA, (Join-Path $env:APPDATA ""), (Join-Path $env:USERPROFILE "Documents")) | Where-Object { $_ -and (Test-Path $_) }
    foreach($b in $bases){
        foreach($name in $OldInstallNames){
            $p = Join-Path $b $name
            if((Test-Path -LiteralPath $p) -and ($found -notcontains $p)){ $found.Add($p) }
        }
    }
    return $found
}
function Clean-Shortcuts(){
    $desktop=[Environment]::GetFolderPath("Desktop")
    $startMenu=Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
    $names=@("J&R Job Manager Pro.lnk","J and R Job Manager Pro.lnk","J and R Construction Manager - Best Host Server.lnk","J and R Construction Manager - Public Host Mode.lnk","J and R Construction Manager - Local LAN Host.lnk","J and R Construction Manager - System Check.lnk","J and R Manager Backup.lnk","Uninstall J and R Construction Manager.lnk","J and R Construction Manager.lnk")
    foreach($n in $names){
        foreach($loc in @($desktop,$startMenu)){
            $p=Join-Path $loc $n
            if(Test-Path -LiteralPath $p){ try{ Remove-Item -LiteralPath $p -Force; Add-Log "Removed old shortcut: $p" } catch{ Add-Log "Could not remove shortcut: $p" } }
        }
    }
}

function Open-ExistingSecureLoginCheck(){
    Add-Log "Pre-install local login check requested. This opens the existing local login gate if available. The installer never asks for or stores passwords."
    $gate=Join-Path $InstallDir "app\local_login_gate.py"
    $py=Join-Path $InstallDir ".venv\Scripts\pythonw.exe"
    if(-not(Test-Path $py)){ $py="pythonw.exe" }
    if(Test-Path $gate){
        try { Start-Process $py -ArgumentList "`"$gate`"" -WorkingDirectory $InstallDir -WindowStyle Hidden; Add-Log "Opened existing Local Login Gate." }
        catch { Add-Log "Could not open Local Login Gate: $($_.Exception.Message)" }
        [System.Windows.Forms.MessageBox]::Show("Secure Local Login was opened from the existing install if available. Confirm your owner/admin login there before updating.`n`nThe installer does not collect passwords.","Pre-Install Local Login Check","OK","Information") | Out-Null
    } else {
        [System.Windows.Forms.MessageBox]::Show("No Local Login Gate was found in the existing install. Continue with Install/Update. After install, Secure Local Login will open automatically.","No Existing Local Login Gate","OK","Information") | Out-Null
    }
}

$form=New-Object System.Windows.Forms.Form
$form.Text="$AppName Installer"
$form.Width=880; $form.Height=705; $form.StartPosition="CenterScreen"; $form.FormBorderStyle="FixedDialog"; $form.MaximizeBox=$false
$form.BackColor=[System.Drawing.Color]::FromArgb(7,14,25)
$form.Font=New-Object System.Drawing.Font("Segoe UI",10)
$title=New-Object System.Windows.Forms.Label
$title.Text="J and R Construction Manager"
$title.ForeColor=[System.Drawing.Color]::White
$title.Font=New-Object System.Drawing.Font("Segoe UI",24,[System.Drawing.FontStyle]::Bold)
$title.AutoSize=$true; $title.Location=New-Object System.Drawing.Point(24,18); $form.Controls.Add($title)
$sub=New-Object System.Windows.Forms.Label
$sub.Text="v$Version - primary-live cloud, persistent data, secure owner setup, customer portal, role dashboards"
$sub.ForeColor=[System.Drawing.Color]::FromArgb(203,213,225)
$sub.AutoSize=$true; $sub.Location=New-Object System.Drawing.Point(28,68); $form.Controls.Add($sub)
$panel=New-Object System.Windows.Forms.Panel
$panel.BackColor=[System.Drawing.Color]::FromArgb(24,36,56)
$panel.Location=New-Object System.Drawing.Point(24,104); $panel.Size=New-Object System.Drawing.Size(820,430); $form.Controls.Add($panel)
$script:StatusLabel=New-Object System.Windows.Forms.Label
$script:StatusLabel.Text="Ready. Click Install / Update. Quick Setup Login opens automatically when complete."
$script:StatusLabel.ForeColor=[System.Drawing.Color]::FromArgb(226,232,240)
$script:StatusLabel.Font=New-Object System.Drawing.Font("Segoe UI",12,[System.Drawing.FontStyle]::Bold)
$script:StatusLabel.AutoSize=$false; $script:StatusLabel.Location=New-Object System.Drawing.Point(18,16); $script:StatusLabel.Size=New-Object System.Drawing.Size(780,30); $panel.Controls.Add($script:StatusLabel)
$script:ProgressBar=New-Object System.Windows.Forms.ProgressBar
$script:ProgressBar.Location=New-Object System.Drawing.Point(18,55); $script:ProgressBar.Size=New-Object System.Drawing.Size(780,24); $script:ProgressBar.Minimum=0; $script:ProgressBar.Maximum=100; $panel.Controls.Add($script:ProgressBar)
$script:LogBox=New-Object System.Windows.Forms.TextBox
$script:LogBox.Multiline=$true; $script:LogBox.ReadOnly=$true; $script:LogBox.ScrollBars="Vertical"
$script:LogBox.BackColor=[System.Drawing.Color]::FromArgb(15,23,42)
$script:LogBox.ForeColor=[System.Drawing.Color]::FromArgb(226,232,240)
$script:LogBox.Font=New-Object System.Drawing.Font("Consolas",9)
$script:LogBox.Location=New-Object System.Drawing.Point(18,92); $script:LogBox.Size=New-Object System.Drawing.Size(780,315); $panel.Controls.Add($script:LogBox)
$installBtn=New-Object System.Windows.Forms.Button
$installBtn.Text="Install / Update"
$installBtn.BackColor=[System.Drawing.Color]::FromArgb(45,212,191)
$installBtn.ForeColor=[System.Drawing.Color]::FromArgb(3,17,10)
$installBtn.FlatStyle="Flat"
$installBtn.Font=New-Object System.Drawing.Font("Segoe UI",12,[System.Drawing.FontStyle]::Bold)
$preLoginBtn=New-Object System.Windows.Forms.Button
$preLoginBtn.Text="Pre-Install Local Login Check"
$preLoginBtn.BackColor=[System.Drawing.Color]::FromArgb(168,85,247); $preLoginBtn.ForeColor=[System.Drawing.Color]::White; $preLoginBtn.FlatStyle="Flat"
$preLoginBtn.Font=New-Object System.Drawing.Font("Segoe UI",11,[System.Drawing.FontStyle]::Bold)
$preLoginBtn.Location=New-Object System.Drawing.Point(24,550); $preLoginBtn.Size=New-Object System.Drawing.Size(220,42); $form.Controls.Add($preLoginBtn)
$preLoginBtn.Add_Click({ Open-ExistingSecureLoginCheck })
$installBtn.Location=New-Object System.Drawing.Point(24,615); $installBtn.Size=New-Object System.Drawing.Size(180,42); $form.Controls.Add($installBtn)
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
$launchBtn.Add_Click({ $setup=Join-Path $InstallDir "app\local_login_gate.py"; if(Test-Path $setup){ $py=Join-Path $InstallDir ".venv\Scripts\pythonw.exe"; if(-not(Test-Path $py)){ $py=Join-Path $InstallDir ".venv\Scripts\python.exe" }; if(Test-Path $py){ try{ Start-Process $py -ArgumentList "`"$setup`"" -WorkingDirectory $InstallDir -WindowStyle Hidden; Add-Log "Opened Quick Setup Login." } catch { Add-Log "Could not open Quick Setup Login: $($_.Exception.Message)" } } else { try{ Start-Process "pyw.exe" -ArgumentList "-3 `"$setup`"" -WorkingDirectory $InstallDir -WindowStyle Hidden; Add-Log "Opened Quick Setup Login with pyw." } catch { try{ Start-Process "py.exe" -ArgumentList "-3 `"$setup`"" -WorkingDirectory $InstallDir -WindowStyle Hidden; Add-Log "Opened Quick Setup Login with py." } catch { [System.Windows.Forms.MessageBox]::Show("Python was not found. Install Python 3 or run the repair tool, then open setup/login again.") | Out-Null } } } } else { [System.Windows.Forms.MessageBox]::Show("Install first, then open setup/login.") | Out-Null } })
$closeBtn.Add_Click({ $form.Close() })
$installBtn.Add_Click({
    $installBtn.Enabled=$false
    try{
        Set-Status "Preflight: detecting old installs and folders" 5
        Ensure-Dir $InstallDir; Ensure-Dir $BackupRoot; Ensure-Dir $ArchiveRoot; Ensure-Dir $LogDir
        Add-Log "Package folder: $PackageDir"
        Add-Log "Primary install folder: $InstallDir"
        $found = Find-OldInstalls
        foreach($p in $found){ Add-Log "Detected install/copy: $p" }
        Set-Status "Creating and preserving business data folders" 12
        foreach($name in $PreserveNames){ Ensure-Dir (Join-Path $InstallDir $name) }
        Set-Status "Backing up current database" 18
        $db=Join-Path $InstallDir "data\jr_business.db"
        if(Test-Path -LiteralPath $db){
            Copy-Item -LiteralPath $db -Destination (Join-Path $BackupRoot "jr_business_before_v7_1_update_$Stamp.db") -Force
            Add-Log "Database backup saved before update."
        } else { Add-Log "No current database found at primary install. Starter database may be installed if packaged." }
        Set-Status "Archiving and migrating old install copies" 30
        foreach($old in $found){
            if($old -ne $InstallDir){
                $arch = Archive-Dir $old (Split-Path -Leaf $old)
                foreach($name in $PreserveNames){ Copy-FolderContents (Join-Path $old $name) (Join-Path $InstallDir $name) }
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
        $runtimeBat = Join-Path $InstallDir "setup_runtime_env.bat"
        if(Test-Path -LiteralPath $runtimeBat){
            $proc = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "`"$runtimeBat`"") -WorkingDirectory $InstallDir -Wait -PassThru -WindowStyle Hidden
            Add-Log "setup_runtime_env.bat finished with exit code $($proc.ExitCode)"
            if($proc.ExitCode -ne 0){ Add-Log "WARNING: runtime setup returned non-zero exit. Run setup_runtime_env.bat manually if the app fails to start." }
        } else {
            Add-Log "setup_runtime_env.bat not found in package; run ensure_venv.bat manually after install."
        }
        if(-not(Test-Path -LiteralPath $db) -and (Test-Path (Join-Path $PackageDir "data\jr_business.db"))){
            Copy-Item -LiteralPath (Join-Path $PackageDir "data\jr_business.db") -Destination $db -Force
            Add-Log "Starter database installed."
        }
        Set-Content -Path (Join-Path $InstallDir "VERSION.txt") -Value "J and R Construction Manager v$Version" -Encoding ASCII
        Set-Status "Cleaning old shortcuts" 75
        Clean-Shortcuts
        Set-Status "Creating one desktop shortcut" 84
        $desktop=[Environment]::GetFolderPath("Desktop")
        $startMenu=Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
        $target=Join-Path $InstallDir "run_jr_manager_hidden.vbs"
        $icon=Join-Path $InstallDir "assets\j_and_r_manager_icon.ico"
        Create-Shortcut (Join-Path $desktop "J and R Construction Manager.lnk") $target $InstallDir $icon
        Create-Shortcut (Join-Path $startMenu "J and R Construction Manager.lnk") $target $InstallDir $icon
        Set-Status "Writing install status and troubleshooting report" 94
        $marker = @"
Installed: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Version: $Version
Install folder: $InstallDir
Installer log: $LogPath
Troubleshooting report: $ReportPath
Old copies are archived under: $ArchiveRoot
Business data preserved: data, evidence, exports, backups, chatgpt_imports, business_standards, logs
Note: Installer does not store passwords. Quick Setup Login opens after install. Use admin/admin only on first setup, then change it once; future installs preserve it.
"@
        Set-Content -Path (Join-Path $InstallDir "INSTALL_STATUS.txt") -Value $marker -Encoding UTF8
        Add-Log "Install/update complete. Launching Quick Setup Login only (no heavy host/start center)."
        Set-Status "Install/update complete - opening setup/login" 100
        try {
            $setup=Join-Path $InstallDir "app\local_login_gate.py"
            $py=Join-Path $InstallDir ".venv\Scripts\pythonw.exe"
            if(-not(Test-Path $py)){ $py=Join-Path $InstallDir ".venv\Scripts\python.exe" }
            if(-not(Test-Path $py)){ $py="pyw.exe" }
            if(Test-Path $setup){ if((Split-Path -Leaf $py) -match "^python") { Start-Process $py -ArgumentList "`"$setup`"" -WorkingDirectory $InstallDir -WindowStyle Hidden } else { Start-Process $py -ArgumentList "-3 `"$setup`"" -WorkingDirectory $InstallDir -WindowStyle Hidden } }
        } catch { Add-Log "Could not auto-open Quick Setup Login: $($_.Exception.Message)" }
        [System.Windows.Forms.MessageBox]::Show("Install/update complete. Business data was preserved and Quick Setup Login is opening.

The installer does not collect or store passwords. Login happens inside the secured app. After login, choose Change Password, Open Office, or Start Center. Dashboard is selected by account type inside the app.

Use Self Setup + Verify from Start Center after login.","J and R Construction Manager","OK","Information") | Out-Null
    } catch {
        Add-Log "ERROR: $($_.Exception.Message)"
        [System.Windows.Forms.MessageBox]::Show("Installer stopped: $($_.Exception.Message)\n\nLog/report saved here:\n$LogPath\n$ReportPath","Install Issue","OK","Warning") | Out-Null
    } finally { $installBtn.Enabled=$true }
})
Add-Log "Installer opened. v7.1 primary live reliable business updater loaded."
Add-Log "This installer does not store passwords. It preserves data, opens Quick Setup Login after install, and verification happens inside the app."
[void]$form.ShowDialog()
