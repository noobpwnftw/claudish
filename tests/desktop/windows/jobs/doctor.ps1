$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine")
Set-Location C:\claudish
python -m claudish doctor
"exit=$LASTEXITCODE"
