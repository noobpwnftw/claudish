@echo off
rem Runs once at first logon (dockur OEM hook). Installs a job runner for the Claudish desktop tests.
copy /y C:\OEM\agent.ps1 C:\agent.ps1
schtasks /create /tn ClaudishAgent /sc onlogon /rl highest /f /tr "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\agent.ps1"
start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\agent.ps1
