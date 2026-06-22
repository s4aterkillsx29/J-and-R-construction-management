@echo off
cd /d "%~dp0"
echo Starting J&R Construction Manager Docker cloud test...
docker compose up --build
pause
