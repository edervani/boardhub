# Para o BoardHub local. Os dados do banco são mantidos; use -Apagar para removê-los.
param([switch]$Apagar)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
if ($Apagar) { docker compose down --volumes } else { docker compose down }
