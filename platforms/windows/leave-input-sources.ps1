# At uninstall, run by the uninstaller (elevated, maybe as the administrator who approved it): cd_AI
# leaves the input sources of each account that installed it, as that account, before its text
# service is unregistered. Each such account has a claudish-<user> logon task (claudish service);
# a one-shot task runs as it while it is signed in.
param([string]$Python, [string]$Tip)
foreach ($task in Get-ScheduledTask -TaskName 'claudish-*' -ErrorAction SilentlyContinue) {
    $user = $task.Principal.UserId
    if (-not $user) { continue }
    $name = 'cd_AI-leave-' + ($task.TaskName -replace '^claudish-', '')
    $code = 'import ctypes; ctypes.windll.input.InstallLayoutOrTip(''' + $Tip + ''', 1)'
    try {
        $action = New-ScheduledTaskAction -Execute $Python -Argument ('-c "' + $code + '"')
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive
        Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Force | Out-Null
        Start-ScheduledTask -TaskName $name
        Start-Sleep -Milliseconds 500
        for ($i = 0; $i -lt 25 -and (Get-ScheduledTask -TaskName $name).State -eq 'Running'; $i++) {
            Start-Sleep -Milliseconds 200
        }
    } catch {}  # signed out: Windows drops a removed text service from its list at sign-in
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
