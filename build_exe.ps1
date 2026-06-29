$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$workPath = Join-Path $env:TEMP "stocks_pyinstaller_work"
New-Item -ItemType Directory -Force -Path $workPath | Out-Null
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --workpath $workPath --distpath .\dist CapitalGainsFIFO.spec

Write-Host "Built dist\CapitalGainsFIFO.exe"
