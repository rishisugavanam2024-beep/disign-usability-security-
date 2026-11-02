param(
    [string]$PythonExecutable = '',
    [string]$JavaExecutable = 'C:\Program Files\Java\jdk-21.0.11\bin\java.exe',
    [switch]$BaselineOnly
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $PythonExecutable) {
    $PythonExecutable = Join-Path $projectRoot '.local\python-connector\venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $PythonExecutable)) {
    throw 'Set -PythonExecutable to a Python environment with saferevoke 0.1.0a3 installed. See this connector README.'
}
$env:PYTHONDONTWRITEBYTECODE = '1'
$arguments = @('-B', (Join-Path $PSScriptRoot 'run_demo.py'), '--java', $JavaExecutable)
if ($BaselineOnly) { $arguments += '--baseline-only' }
& $PythonExecutable @arguments
if ($LASTEXITCODE -ne 0) { throw "External testing failed (exit $LASTEXITCODE). Do not present a partial report as complete." }
