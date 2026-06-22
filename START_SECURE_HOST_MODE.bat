@echo off
set JRC_PUBLIC_HOST_MODE=1
set JRC_SESSION_TIMEOUT_MINUTES=60
set JRC_PORT=8765
echo WARNING: Use this only behind HTTPS, VPN, or a secure tunnel. Do not expose an unprotected laptop port.
echo Starting J and R Construction Manager in secured host mode...
call run_jr_manager.bat
