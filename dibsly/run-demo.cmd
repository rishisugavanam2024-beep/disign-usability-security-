@echo off
setlocal
cd /d "%~dp0"
set APP_ENV=development
set DEMO_MODE=true
set SECURE_COOKIES=false
if not defined PORT set PORT=8092
if not defined ADMIN_USERNAME set ADMIN_USERNAME=admin
if not defined ADMIN_PASSWORD set ADMIN_PASSWORD=DibslyAdmin2026!
if not exist target\dibsly-1.0.0.jar (
  call mvnw.cmd -f reactor/pom.xml package
  if errorlevel 1 exit /b 1
)
java -Xms64m -Xmx256m -jar target\dibsly-1.0.0.jar
