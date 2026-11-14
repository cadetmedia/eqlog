# Windows installer

[Download EQLog v0.1.0 for Windows x64](https://github.com/cadetmedia/eqlog/raw/refs/heads/main/downloads/eqlog-Setup-0.1.0.exe)

See the [installation and cleanup directions](../README.md#download-for-windows).
If GitHub opens the binary file page, use **Download raw file**.
Repository access is required if this repository is private.

This is the unsigned NSIS 3.11 package built with CPython 3.12.10 x64 and
PyInstaller 6.16.0. The bundled app and install/uninstall sequence were exercised
under Wine 10, including cumulative backups and preservation of user-created
backups during uninstall. Native Windows validation is still pending.

The matching checksum is in `eqlog-Setup-0.1.0.exe.sha256`. To calculate the
installer's checksum in PowerShell:

```powershell
Get-FileHash .\eqlog-Setup-0.1.0.exe -Algorithm SHA256
```

Expected SHA-256:

```text
91948199352ce166497f5e0d17018a583badabda5b7c059863bfa7b61f3820b9
```
