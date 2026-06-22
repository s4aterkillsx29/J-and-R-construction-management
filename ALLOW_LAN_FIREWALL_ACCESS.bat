@echo off
setlocal
TITLE J and R Construction Manager - Allow LAN Firewall Access
ECHO ======================================================
ECHO J and R Construction Manager - LAN/Mobile Firewall Fix
ECHO ======================================================
ECHO.
ECHO This adds an inbound Windows Firewall rule for TCP port 8765.
ECHO It allows phones/devices on your trusted private Wi-Fi/VPN to reach the shared host.
ECHO.
ECHO Run only on Jacob's host computer. Windows may ask for Administrator approval.
ECHO.
pause
netsh advfirewall firewall add rule name="J and R Construction Manager Shared Host 8765" dir=in action=allow protocol=TCP localport=8765 profile=private
ECHO.
ECHO If the command succeeded, restart the shared host and test from your phone:
ECHO http://YOUR-LAN-IP:8765/connect
ECHO.
pause
