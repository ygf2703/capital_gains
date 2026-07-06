$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$versionLine = Get-Content ".\capital_gains_app\__init__.py" | Select-String "__version__"
if (-not $versionLine) {
    throw "Could not determine application version."
}

$version = ($versionLine.Line -split '"')[1]
if (-not $version) {
    throw "Could not parse application version."
}

powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1

$releaseRoot = Join-Path $root "release"
$releaseName = "CapitalGains-$version-win64"
$releaseDir = Join-Path $releaseRoot $releaseName
$zipPath = Join-Path $releaseRoot "$releaseName.zip"

if (Test-Path $releaseDir) {
    Remove-Item $releaseDir -Recurse -Force
}
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
Copy-Item ".\dist\CapitalGainsFIFO.exe" $releaseDir
Copy-Item ".\README.md" $releaseDir

$notes = @"
Capital Gains $version

קובץ ההפעלה:
- CapitalGainsFIFO.exe

לפני התחברות עם Google:
- יש להציב google_client_secret.json לפי ההנחיות ב-README.md
"@

$notes | Set-Content -Path (Join-Path $releaseDir "RELEASE_NOTES.txt") -Encoding UTF8

Compress-Archive -Path "$releaseDir\*" -DestinationPath $zipPath

Write-Host "Packaged $zipPath"
