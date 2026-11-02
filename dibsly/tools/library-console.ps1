param(
    [string]$Subject = 'examiner:user:42',
    [string]$Permission = 'EXPORT_INVOICE',
    [string]$JavaExecutable = 'java.exe'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$library = Join-Path $projectRoot 'safe-revoke\target\safe-revoke-1.0.0.jar'
$driver = Join-Path $projectRoot '.tools\repository\com\h2database\h2\2.3.232\h2-2.3.232.jar'
if (-not (Test-Path -LiteralPath $driver)) {
    $driver = Join-Path $env:USERPROFILE '.m2\repository\com\h2database\h2\2.3.232\h2-2.3.232.jar'
}
if (-not (Test-Path -LiteralPath $library) -or -not (Test-Path -LiteralPath $driver)) {
    throw 'Build the reactor first: .\mvnw.cmd -f reactor/pom.xml verify'
}
$example = Join-Path $projectRoot 'safe-revoke\examples\LibraryConsole.java'
$reports = Join-Path $projectRoot '.local\library-demo'
if ($MyInvocation.ExpectingInput) {
    $input | & $JavaExecutable --class-path "$library;$driver" $example $Subject $Permission $reports
} else {
    & $JavaExecutable --class-path "$library;$driver" $example $Subject $Permission $reports
}
if ($LASTEXITCODE -ne 0) { throw "Library demo exited with code $LASTEXITCODE" }
