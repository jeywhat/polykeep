param(
    [string] $SmbRoot = "\\192.168.1.50\3d\storage",
    [string] $BaseUrl = "http://192.168.1.50:8000"
)

$ErrorActionPreference = "Stop"
$appDir = Join-Path $env:LOCALAPPDATA "PolyKeep"
$configPath = Join-Path $appDir "config.json"
$helperPath = Join-Path $PSScriptRoot "polykeep-helper.ps1"
$command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$helperPath`" `"%1`""

New-Item -ItemType Directory -Path $appDir -Force | Out-Null
New-Item -Path "HKCU:\Software\Classes\polykeep" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Classes\polykeep" -Name "(Default)" -Value "URL:PolyKeep Protocol"
New-ItemProperty -Path "HKCU:\Software\Classes\polykeep" -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null
New-Item -Path "HKCU:\Software\Classes\polykeep\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Classes\polykeep\shell\open\command" -Name "(Default)" -Value $command

$existing = $null
if (Test-Path -LiteralPath $configPath) {
    try { $existing = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json } catch { }
}
$config = [ordered]@{
    smbRoot = if ($existing.smbRoot) { $existing.smbRoot } else { $SmbRoot }
    baseUrl = if ($existing.baseUrl) { $existing.baseUrl } else { $BaseUrl }
    bambuStudioPath = if ($existing.bambuStudioPath) { $existing.bambuStudioPath } else { "" }
}
$config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8

$knownBambu = Join-Path ${env:ProgramFiles} "Bambu Studio\bambu-studio.exe"
$detected = if ($config.bambuStudioPath -and (Test-Path -LiteralPath $config.bambuStudioPath)) {
    $config.bambuStudioPath
} elseif (Test-Path -LiteralPath $knownBambu) {
    $knownBambu
} else {
    $registryPath = $null
    foreach ($root in @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )) {
        foreach ($entry in @(Get-ItemProperty $root -ErrorAction SilentlyContinue)) {
            if ([string]$entry.DisplayName -match "Bambu Studio" -and $entry.InstallLocation) {
                $candidate = Join-Path $entry.InstallLocation "bambu-studio.exe"
                if (Test-Path -LiteralPath $candidate) { $registryPath = $candidate; break }
            }
        }
        if ($registryPath) { break }
    }
    if ($registryPath) { $registryPath } else { "non détecté (le gestionnaire par défaut sera utilisé)" }
}
Write-Host "Protocole polykeep installé. Bambu Studio : $detected"
