# Inicia o BoardHub para teste local no Windows (requer Docker Desktop em execução).
# Uso (PowerShell, na pasta do projeto):  .\scripts\windows\iniciar.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker não encontrado. Instale o Docker Desktop e abra-o antes de continuar."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "O Docker Desktop não está em execução. Abra-o, espere ficar 'Running' e tente de novo."
}

function Novo-Segredo([int]$bytes) {
    $b = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    ([Convert]::ToBase64String($b)).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

if (-not (Test-Path ".env")) {
    $linhas = @(
        "APP_ENV=development",
        "SECRET_KEY=$(Novo-Segredo 48)",
        "POSTGRES_DB=boardhub",
        "POSTGRES_USER=boardhub_app",
        "POSTGRES_PASSWORD=$(Novo-Segredo 24)",
        "FRONTEND_ORIGIN=http://localhost:8080",
        "COOKIE_SECURE=false"
    )
    # UTF-8 sem BOM, para o Compose ler corretamente.
    [System.IO.File]::WriteAllLines((Join-Path (Get-Location) ".env"), $linhas)
    Write-Host "Arquivo .env criado com segredos aleatórios (não o compartilhe nem o versione)."
}

docker compose up -d --build --wait
if ($LASTEXITCODE -ne 0) {
    Write-Host "Falha ao iniciar. Veja os registros com: docker compose logs backend"
    exit 1
}
Write-Host ""
Write-Host "BoardHub:        http://localhost:8080"
Write-Host "E-mails de teste: http://localhost:8025   (links de verificação de conta)"
Write-Host "Para parar:      .\scripts\windows\parar.ps1"
