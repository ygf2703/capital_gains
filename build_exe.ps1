$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonLauncher) {
        py -m venv .venv
    } elseif ($pythonCommand) {
        python -m venv .venv
    } else {
        throw "Python 3.12+ was not found. Install Python and make py or python available in PATH."
    }
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$workPath = Join-Path $env:TEMP "capital_gains_pyinstaller_work"
New-Item -ItemType Directory -Force -Path $workPath | Out-Null
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --workpath $workPath --distpath .\dist CapitalGainsFIFO.spec

Write-Host "Built dist\CapitalGainsFIFO.exe"
