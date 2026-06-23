# J&R Local Server Health + Repair

This official repo tool is for fixing and testing local access problems before using the J&R Construction Manager from Windows, LAN, or an iPhone.

It checks the failures reported during field testing:

- login page fail
- API health fail
- mobile ping fail
- LAN phone test fail
- Windows Firewall needs attention
- server not running

## Start without a command prompt

Double-click:

```text
Launch_JRC_Server_Health.vbs
```

## What it does

The health tool provides a professional windowed UI with buttons to:

1. Start a known-good local health API server.
2. Test the login page.
3. Test `/api/health`.
4. Test `/api/mobile/ping`.
5. Test LAN phone access using your computer LAN IP.
6. Show the Windows Firewall command needed to allow LAN access.
7. Stop the health server.

## Default ports

- Health tool server: `8765`
- Local-only URL: `http://127.0.0.1:8765/login`
- LAN/iPhone URL: `http://YOUR-PC-LAN-IP:8765/login`

## Safety

This tool is a local/LAN diagnostic server. It is not a public cloud deployment and should not be exposed directly to the internet.
