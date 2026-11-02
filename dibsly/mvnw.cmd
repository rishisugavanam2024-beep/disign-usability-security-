@echo off
setlocal
if not defined MAVEN_OPTS set MAVEN_OPTS=-Xmx256m
if exist "%~dp0.tools\apache-maven-3.9.11\bin\mvn.cmd" (
  call "%~dp0.tools\apache-maven-3.9.11\bin\mvn.cmd" "-Dmaven.repo.local=%~dp0.tools\repository" %*
  exit /b
)
where mvn.cmd >nul 2>nul
if errorlevel 1 (
  echo Install Java 21 and Maven 3.9+, or use Docker Compose to build Dibsly.
  exit /b 1
)
call mvn.cmd %*
