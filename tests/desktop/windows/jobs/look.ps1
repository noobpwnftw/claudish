# G26: capture the foreground window with claudish.capture (PrintWindow) and save the PNG for the host.
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine')
Set-Location C:\claudish
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Set-Content C:\look.txt "INVOICE 4471`r`nCustomer: Brightwater Ltd`r`nAmount due: 1,250.00 EUR`r`nStatus: OVERDUE since 2026-09-30"
Start-Process notepad C:\look.txt
Start-Sleep 3
python -c "from claudish.capture import capture; d, w, h = capture(); open(r'\\host.lan\Data\results\look.png', 'wb').write(d); print('captured', w, h)"
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
