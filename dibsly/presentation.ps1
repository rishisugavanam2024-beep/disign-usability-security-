param(
    [Parameter(Position=0)][ValidateSet('start','stop','proof','install-library','package','permissions','revoke','grant','restore','test','baseline')][string]$Action='start',
    [Parameter(Position=1)][string]$Username='freelancer.demo',
    [Parameter(Position=2)][string]$Permission='SUBMIT_PROPOSAL',
    [string]$JavaExecutable='C:\Program Files\Java\jdk-21.0.11\bin\java.exe'
)
$ErrorActionPreference='Stop'
$projectRoot=$PSScriptRoot
$runtime=Join-Path $projectRoot '.local\presentation'
$python=Join-Path $runtime 'python\Scripts\python.exe'
$jar=Join-Path $projectRoot 'target\dibsly-1.0.0.jar'
$pidFile=Join-Path $runtime 'server.pid'
function PresentationProcess {
    if (Test-Path -LiteralPath $pidFile) {
        $savedId=[int](Get-Content -LiteralPath $pidFile)
        $process=Get-CimInstance Win32_Process -Filter "ProcessId=$savedId" -ErrorAction SilentlyContinue
        if ($process -and ($process.Name -ne 'java.exe' -or $process.CommandLine -notlike '*-Ddibsly.presentation=true*')) {throw 'Saved PID is not the presentation server'}
        return $process
    }
}
switch ($Action) {
    'start' {
        if (-not (Test-Path -LiteralPath $jar)) {throw 'Build the independent Dibsly application first: .\mvnw.cmd verify'}
        $existing=PresentationProcess
        if ($existing) {Write-Output 'Presentation is already running at http://localhost:8093';break}
        New-Item -ItemType Directory -Force -Path $runtime | Out-Null
        Copy-Item -LiteralPath $jar -Destination (Join-Path $runtime 'dibsly.jar') -Force
        $env:APP_ENV='development';$env:DEMO_MODE='true';$env:SECURE_COOKIES='false';$env:PORT='8093'
        $env:DB_URL='jdbc:h2:file:'+(Join-Path $runtime 'data\dibsly').Replace('\','/')+';DB_CLOSE_DELAY=-1;MODE=MySQL'
        $env:DB_USER='sa';$env:DB_PASSWORD='';$env:ADMIN_USERNAME='admin';$env:ADMIN_PASSWORD='DibslyAdmin2026!'
        $process=Start-Process -FilePath $JavaExecutable -ArgumentList @('-Xms64m','-Xmx256m','-Ddibsly.presentation=true','-jar','dibsly.jar') -WorkingDirectory $runtime -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'stdout.log') -RedirectStandardError (Join-Path $runtime 'stderr.log') -PassThru
        $process.Id | Set-Content -LiteralPath $pidFile
        $ready=$false
        for($attempt=0;$attempt -lt 40;$attempt++) {
            if($process.HasExited){throw 'Presentation server exited. See .local/presentation/stderr.log'}
            try { $response=Invoke-WebRequest 'http://127.0.0.1:8093/health' -TimeoutSec 2 -UseBasicParsing;if($response.StatusCode -eq 200){$ready=$true;break} } catch {}
            Start-Sleep -Milliseconds 500
        }
        if(-not $ready){throw 'Server readiness timed out. See .local/presentation/stderr.log'}
        Write-Output 'Independent Dibsly site ready at http://localhost:8093'
        Write-Output 'No Python library was installed or loaded by this command.'
    }
    'stop' { $process=PresentationProcess;if($process){Stop-Process -Id $process.ProcessId;Wait-Process -Id $process.ProcessId -ErrorAction SilentlyContinue};if(Test-Path -LiteralPath $pidFile){Remove-Item -LiteralPath $pidFile};Write-Output 'Presentation server stopped; its saved projects remain.' }
    'proof' { & python (Join-Path $projectRoot 'tools\verify-library-artifact.py');if($LASTEXITCODE -ne 0){throw 'Independence verification failed'} }
    'install-library' {
        if (-not (Test-Path -LiteralPath $python)) { & python -m venv (Join-Path $runtime 'python');if($LASTEXITCODE -ne 0){throw 'Could not create demonstration Python environment'} }
        & $python -m pip install --index-url https://pypi.org/simple saferevoke==0.1.0a4
        if($LASTEXITCODE -ne 0){throw 'Library installation failed'}
        & $python -m pip check
        if($LASTEXITCODE -ne 0){throw 'Library dependency check failed'}
    }
    'package' {
        if (-not (Test-Path -LiteralPath $python)) {Write-Output 'SafeRevoke is not installed in the presentation environment yet.';break}
        & $python -m pip show saferevoke
    }
    {$_ -in 'permissions','revoke','grant','restore'} {
        if (-not (PresentationProcess)) {throw 'Start the dedicated presentation site first.'}
        & python (Join-Path $projectRoot 'integrations\saferevoke-python\manage_permissions.py') $Action $Username $Permission
        if($LASTEXITCODE -ne 0){throw 'Permission command failed'}
    }
    {$_ -in 'test','baseline'} {
        if (-not (Test-Path -LiteralPath $python)) {throw 'Install the external library first: .\presentation.ps1 install-library'}
        if($Action -eq 'baseline') { & (Join-Path $projectRoot 'integrations\saferevoke-python\run-demo.ps1') -PythonExecutable $python -JavaExecutable $JavaExecutable -BaselineOnly }
        else { & (Join-Path $projectRoot 'integrations\saferevoke-python\run-demo.ps1') -PythonExecutable $python -JavaExecutable $JavaExecutable }
    }
}
