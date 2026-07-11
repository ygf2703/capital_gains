param(
    [string]$ConfigPath = ".\config\msix.settings.json",
    [switch]$SkipExeBuild,
    [switch]$SkipSigning
)

$ErrorActionPreference = "Stop"

function Get-AppVersion {
    $versionLine = Get-Content ".\capital_gains_app\__init__.py" | Select-String "__version__"
    if (-not $versionLine) {
        throw "Could not determine application version."
    }

    $version = ($versionLine.Line -split '"')[1]
    if (-not $version) {
        throw "Could not parse application version."
    }

    $parts = $version.Split(".")
    while ($parts.Count -lt 4) {
        $parts += "0"
    }
    return ($parts[0..3] -join ".")
}

function Find-WindowsSdkTool([string]$toolName) {
    $fromPath = Get-Command $toolName -ErrorAction SilentlyContinue
    if ($fromPath) {
        return $fromPath.Source
    }

    $kitsRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (-not (Test-Path $kitsRoot)) {
        return $null
    }

    $candidates = @()
    $versionDirs = Get-ChildItem $kitsRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } |
        Sort-Object Name -Descending

    foreach ($dir in $versionDirs) {
        $candidates += Join-Path $dir.FullName "x64\$toolName"
    }
    $candidates += Join-Path $kitsRoot "x64\$toolName"

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Require-Value([string]$value, [string]$fieldName) {
    if (-not $value -or $value -match "^REPLACE_") {
        throw "Field '$fieldName' in msix settings is missing or still contains a placeholder."
    }
}

function Resolve-ConfigValue($value, [string]$fallback) {
    $text = [string]$value
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $fallback
    }
    return $text
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path $ConfigPath)) {
    throw "Missing MSIX config file at '$ConfigPath'. Copy config\msix.settings.example.json to config\msix.settings.json and fill the Store values."
}

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
Require-Value $config.identityName "identityName"
Require-Value $config.publisher "publisher"
Require-Value $config.publisherDisplayName "publisherDisplayName"
Require-Value $config.displayName "displayName"
Require-Value $config.shortDisplayName "shortDisplayName"
Require-Value $config.description "description"

$makeAppx = Find-WindowsSdkTool "makeappx.exe"
if (-not $makeAppx) {
    throw "Could not locate makeappx.exe. Install the Windows 10/11 SDK."
}

if (-not $SkipExeBuild) {
    powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
}

$version = Get-AppVersion
$manifestTemplatePath = Join-Path $root "msix\AppxManifest.template.xml"
$manifestText = Get-Content $manifestTemplatePath -Raw

$replacements = @{
    "{{IdentityName}}" = [string]$config.identityName
    "{{Publisher}}" = [string]$config.publisher
    "{{PublisherDisplayName}}" = [string]$config.publisherDisplayName
    "{{DisplayName}}" = [string]$config.displayName
    "{{ShortDisplayName}}" = [string]$config.shortDisplayName
    "{{Description}}" = [string]$config.description
    "{{Language}}" = (Resolve-ConfigValue $config.language "he-IL")
    "{{MinVersion}}" = (Resolve-ConfigValue $config.minVersion "10.0.17763.0")
    "{{MaxVersionTested}}" = (Resolve-ConfigValue $config.maxVersionTested "10.0.26100.0")
    "{{Version}}" = $version
}

foreach ($pair in $replacements.GetEnumerator()) {
    $manifestText = $manifestText.Replace($pair.Key, $pair.Value)
}

$stageRoot = Join-Path $root ".msixbuild"
$packageRoot = Join-Path $stageRoot "package"
$releaseRoot = Join-Path $root "release\msix"
$packageName = "CapitalGains_$version.msix"
$packagePath = Join-Path $releaseRoot $packageName

if (Test-Path $packageRoot) {
    Remove-Item $packageRoot -Recurse -Force
}
if (Test-Path $packagePath) {
    Remove-Item $packagePath -Force
}

New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null

Copy-Item ".\dist\CapitalGainsFIFO.exe" $packageRoot
Copy-Item ".\assets" (Join-Path $packageRoot "assets") -Recurse
$manifestText | Set-Content -Path (Join-Path $packageRoot "AppxManifest.xml") -Encoding UTF8

& $makeAppx pack /d $packageRoot /p $packagePath /o

$signingEnabled = $false
if ($config.signing -and $config.signing.enabled) {
    $signingEnabled = $true
}

if ($signingEnabled -and -not $SkipSigning) {
    $signTool = Find-WindowsSdkTool "signtool.exe"
    if (-not $signTool) {
        throw "Could not locate signtool.exe. Install the Windows 10/11 SDK."
    }

    $certificatePath = [string]$config.signing.certificatePath
    $certificatePassword = [string]$config.signing.certificatePassword
    if (-not $certificatePath -or -not (Test-Path $certificatePath)) {
        throw "MSIX signing is enabled, but the certificatePath is missing or invalid."
    }

    & $signTool sign /fd SHA256 /f $certificatePath /p $certificatePassword $packagePath
    Write-Host "Built and signed $packagePath"
} else {
    Write-Host "Built unsigned MSIX package at $packagePath"
    Write-Host "If you are submitting through the Store, make sure the package identity matches Partner Center and complete signing/association as needed."
}
