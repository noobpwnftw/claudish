# Diagnostic: TSF host and per-user profile state for Claudish.
"ctfmon: $((Get-Process ctfmon -ErrorAction SilentlyContinue | ForEach-Object Id) -join ',')"
"TextInputHost: $((Get-Process TextInputHost -ErrorAction SilentlyContinue | ForEach-Object Id) -join ',')"
$tip = '{35F67E9D-A54D-4177-9697-8B0AB71A9E04}'
"HKLM TIP description: $((Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\CTF\TIP\$tip" -ErrorAction SilentlyContinue).'(default)')"
"HKLM profile:"; Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\CTF\TIP\$tip\LanguageProfile\0x00000409\{EF97D106-1721-4466-A6B1-764987694B3C}" -ErrorAction SilentlyContinue | Format-List Description, Enable, IconFile
"HKCU profile:"; Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\CTF\TIP\$tip\LanguageProfile\0x00000409\{EF97D106-1721-4466-A6B1-764987694B3C}" -ErrorAction SilentlyContinue | Format-List *
"InprocServer32:"; Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\CLSID\$tip\InprocServer32" -ErrorAction SilentlyContinue | Format-List '(default)', ThreadingModel
"Categories:"; Get-ChildItem "HKLM:\SOFTWARE\Microsoft\CTF\TIP\$tip\Category\Category" -ErrorAction SilentlyContinue | ForEach-Object PSChildName
