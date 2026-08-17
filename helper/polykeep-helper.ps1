param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $ProtocolUrl
)

$ErrorActionPreference = "Stop"
$appDir = Join-Path $env:LOCALAPPDATA "PolyKeep"
$logPath = Join-Path $appDir "helper.log"
$configPath = Join-Path $appDir "config.json"

function Write-HelperLog([string] $Message) {
    New-Item -ItemType Directory -Path $appDir -Force | Out-Null
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format o) $Message"
}

function Show-HelperError([string] $Message) {
    Write-HelperLog "ECHEC $Message"
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($Message, "PolyKeep", "OK", "Error") | Out-Null
    exit 1
}

function Get-QueryParameters([Uri] $Uri) {
    $values = @{}
    $query = $Uri.Query.TrimStart("?")
    if ([string]::IsNullOrWhiteSpace($query)) { return $values }
    foreach ($part in $query -split "&") {
        if ([string]::IsNullOrWhiteSpace($part) -or $part -notmatch "^([^=]+)=(.*)$") {
            throw "Paramètre d'URL invalide."
        }
        $key = [Uri]::UnescapeDataString($Matches[1])
        $value = [Uri]::UnescapeDataString($Matches[2].Replace("+", " "))
        if ($values.ContainsKey($key)) { throw "Paramètre répété : $key" }
        $values[$key] = $value
    }
    return $values
}

function Get-Config() {
    if (Test-Path -LiteralPath $configPath) {
        try { return Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json } catch { }
    }
    return [pscustomobject]@{ smbRoot = ""; baseUrl = ""; bambuStudioPath = "" }
}

function Find-BambuStudio([object] $Config) {
    $candidates = @()
    if ($Config.bambuStudioPath) { $candidates += [string]$Config.bambuStudioPath }
    $uninstallRoots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($root in $uninstallRoots) {
        foreach ($entry in @(Get-ItemProperty $root -ErrorAction SilentlyContinue)) {
            if ([string]$entry.DisplayName -match "Bambu Studio") {
                if ($entry.InstallLocation) { $candidates += (Join-Path $entry.InstallLocation "bambu-studio.exe") }
                if ($entry.DisplayIcon) { $candidates += ([string]$entry.DisplayIcon -replace ',\d+$', '') }
            }
        }
    }
    $candidates += (Join-Path ${env:ProgramFiles} "Bambu Studio\bambu-studio.exe")
    $candidates += (Join-Path ${env:LOCALAPPDATA} "Programs\Bambu Studio\bambu-studio.exe")
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
    }
    return $null
}

try {
    $uri = [Uri]$ProtocolUrl
    if ($uri.Scheme -ne "polykeep" -or $uri.Host -ne "open") { throw "URL polykeep invalide." }
    $params = Get-QueryParameters $uri
    $keys = @($params.Keys)
    if ($keys.Count -ne 2 -or !$params.ContainsKey("id") -or !$params.ContainsKey("host")) {
        throw "L'URL doit contenir uniquement id et host."
    }
    [int]$id = 0
    if (![int]::TryParse($params.id, [ref]$id) -or $id -le 0) { throw "Identifiant de fichier invalide." }
    $hostUri = [Uri]$params.host
    if ($hostUri.Scheme -notin @("http", "https") -or !$hostUri.Host -or $hostUri.UserInfo) {
        throw "Adresse du serveur invalide : HTTP ou HTTPS uniquement."
    }
    $config = Get-Config
    try {
        $info = Invoke-RestMethod -Uri "$($hostUri.AbsoluteUri.TrimEnd('/'))/api/files/$id/open-info" -Method Get -TimeoutSec 10
    } catch {
        throw "Impossible de joindre le NAS ou de récupérer le fichier (délai : 10 secondes). $($_.Exception.Message)"
    }
    $openPath = [string]$info.open_path
    $openMode = [string]$info.open_mode
    if (!$openPath -and $info.smb_unc_path) {
        $openPath = [string]$info.smb_unc_path
        $openMode = "smb"
    }
    if (!$openPath -and $openMode -eq "smb" -and $config.smbRoot) {
        $openPath = "{0}\{1}" -f ([string]$config.smbRoot).TrimEnd('\', '/'), ([string]$info.rel_path).Replace('/', '\').TrimStart('\')
    }
    if (!$openPath) {
        throw "Aucun chemin d'ouverture disponible. Configurez T3D_SMB_ROOT ou T3D_OPEN_MODE=local."
    }
    if ($openMode -eq "smb" -or $openPath.StartsWith('\\')) {
        if (!$openPath.StartsWith('\\') -or $openPath -match '(^|\\)\.\.([\\]|$)') { throw "Chemin SMB invalide." }
    } elseif ($openPath -match '^(https?|polykeep):' -or $openPath -match '(^|[\\/])\.\.([\\/]|$)') {
        throw "Chemin local invalide."
    }
    if (!(Test-Path -LiteralPath $openPath -PathType Leaf)) { throw "Fichier introuvable : $openPath" }

    $bambu = Find-BambuStudio $config
    if ($bambu) {
        Start-Process -FilePath $bambu -ArgumentList @($openPath)
        Write-HelperLog "SUCCES id=$id mode=$openMode bambu=$bambu path=$openPath"
    } else {
        Invoke-Item -LiteralPath $openPath
        Write-HelperLog "SUCCES id=$id mode=$openMode gestionnaire-defaut path=$openPath"
    }
} catch {
    Show-HelperError $_.Exception.Message
}
