@echo off
set JRC_PUBLIC_HOST_MODE=0
set JRC_SESSION_TIMEOUT_MINUTES=240
set JRC_PORT=8765
echo Starting J and R Construction Manager in LOCAL/LAN host mode...
call run_jr_manager.bat
