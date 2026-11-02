param([string]$JavaExecutable = 'java.exe', [switch]$BackupDatabase)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $projectRoot '.local\preview'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
if (Test-Path -LiteralPath (Join-Path $runtime 'server.pid')) {
    $previousId = [int](Get-Content -LiteralPath (Join-Path $runtime 'server.pid'))
    $previous = Get-CimInstance Win32_Process -Filter "ProcessId=$previousId" -ErrorAction SilentlyContinue
    if ($previous) {
        if ($previous.Name -ne 'java.exe' -or $previous.CommandLine -notlike '*-jar dibsly.jar*') { throw 'Saved PID is not the Dibsly preview; refusing to stop it.' }
        Stop-Process -Id $previousId -Force
        Wait-Process -Id $previousId -ErrorAction SilentlyContinue
    }
}
if ($BackupDatabase -and (Test-Path -LiteralPath (Join-Path $runtime 'data\dibsly.mv.db'))) {
    $backupDirectory = Join-Path $projectRoot '.local\backups'
    New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
    $backupFile = Join-Path $backupDirectory ('dibsly-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.mv.db')
    Copy-Item -LiteralPath (Join-Path $runtime 'data\dibsly.mv.db') -Destination $backupFile
    Write-Output "Saved stopped-database backup: $backupFile"
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'target\dibsly-1.0.0.jar') -Destination (Join-Path $runtime 'dibsly.jar') -Force
$env:APP_ENV = 'development'
$env:DEMO_MODE = 'true'
$env:SECURE_COOKIES = 'false'
$env:PORT = '8092'
$env:ADMIN_USERNAME = 'admin'
$env:ADMIN_PASSWORD = 'DibslyAdmin2026!'
$previewProcess = Start-Process -FilePath $JavaExecutable -ArgumentList @('-Xms64m','-Xmx256m','-jar','dibsly.jar') -WorkingDirectory $runtime -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'stdout.log') -RedirectStandardError (Join-Path $runtime 'stderr.log') -PassThru
$previewProcess.Id | Set-Content -LiteralPath (Join-Path $runtime 'server.pid')
Write-Output "Started isolated packaged Dibsly preview, PID $($previewProcess.Id), at http://localhost:8092"
