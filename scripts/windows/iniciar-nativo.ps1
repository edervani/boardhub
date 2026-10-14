<#
.SYNOPSIS
    Inicia o BoardHub em MODO NATIVO (sem Docker) para TESTES (DT-025).

.DESCRIPTION
    Sobe o PostgreSQL portátil (só 127.0.0.1), aplica as migrações e inicia o backend (uvicorn), que
    também serve o frontend construído (SERVE_FRONTEND_DIR) na MESMA origem de /api — sem nginx.
    Cookies sem `Secure` (HTTP em localhost), CORS e WebSocket aceitam só http://localhost:<porta>.
    Acesse sempre por "localhost" (não por 127.0.0.1 nem pelo nome da máquina).
    Execute antes: .\scripts\windows\instalar-nativo.ps1

.PARAMETER Porta
    Porta do site nesta execução (padrão: a gravada na instalação, 8080).

.PARAMETER Mailpit
    Inicia o Mailpit (instalado com instalar-nativo.ps1 -Mailpit): e-mails em http://localhost:8025.
    Sem esta chave, os e-mails são gravados em .native\data\emails.jsonl (emails-nativo.ps1).

.PARAMETER SemEspera
    Não espera o site responder (útil em automação que faz a própria verificação).
#>
[CmdletBinding()]
param(
    [int]$Porta = 0,
    [switch]$Mailpit,
    [switch]$SemEspera
)

. (Join-Path $PSScriptRoot '_nativo-comum.ps1')

$config = Import-NativoEnv
if ($Porta -le 0) { $Porta = [int]$config['NATIVO_PORT'] }
$env:FRONTEND_ORIGIN = "http://localhost:$Porta"

$python = Get-NativoPythonVenv
if (-not $python) { throw 'Dependências não instaladas. Rode: .\scripts\windows\instalar-nativo.ps1' }
$pgBin = Get-NativoPgBin
if (-not $pgBin -or -not (Test-Path -LiteralPath (Join-Path $script:PgDados 'PG_VERSION'))) {
    throw 'PostgreSQL não instalado. Rode: .\scripts\windows\instalar-nativo.ps1'
}
if (-not (Test-Path -LiteralPath (Join-Path $script:FrontendDist 'index.html'))) {
    throw 'frontend\dist não existe. Extraia o pacote boardhub-windows-nativo.zip na pasta do projeto ou rode instalar-nativo.ps1 -ConstruirFrontend.'
}

if ($null -ne (Get-NativoProcesso 'backend')) {
    Write-Aviso 'O backend já está em execução. Use .\scripts\windows\parar-nativo.ps1 antes de iniciar de novo.'
    exit 0
}
if (-not (Test-NativoPortaLivre $Porta)) {
    throw "A porta $Porta já está em uso. Use -Porta com outro número (ou pare o outro programa)."
}

Initialize-NativoPasta
Write-Passo 'Iniciando o PostgreSQL'
Invoke-NativoPgIniciar $pgBin

Write-Passo 'Aplicando migrações'
$null = Invoke-NativoExe -Exe $python -Argumentos @('-m', 'alembic', 'upgrade', 'head') -Diretorio $script:Backend -Etapa 'alembic upgrade head'

$urlEmails = "arquivo $script:ArquivoEmails (use .\scripts\windows\emails-nativo.ps1)"
if ($Mailpit) {
    $mailpitExe = Join-Path $script:Ferramentas 'mailpit\mailpit.exe'
    if (-not (Test-Path -LiteralPath $mailpitExe)) {
        Write-Aviso 'Mailpit não instalado (rode instalar-nativo.ps1 -Mailpit); usando e-mails em arquivo.'
    } elseif ($null -eq (Get-NativoProcesso 'mailpit')) {
        Write-Passo 'Iniciando o Mailpit'
        $env:MAIL_BACKEND = 'smtp'
        $env:SMTP_HOST = '127.0.0.1'
        $env:SMTP_PORT = '1025'
        $m = Invoke-NativoSegundoPlano -Exe $mailpitExe -Argumentos @('--listen', '127.0.0.1:8025', '--smtp', '127.0.0.1:1025') `
            -Diretorio $script:Nativo -LogBase (Join-Path $script:Logs 'mailpit')
        Save-NativoPid 'mailpit' $m.Id
        $urlEmails = 'http://localhost:8025'
    }
}

Write-Passo "Iniciando o backend em http://localhost:$Porta"
$proc = Invoke-NativoSegundoPlano -Exe $python `
    -Argumentos @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', [string]$Porta, '--no-access-log') `
    -Diretorio $script:Backend -LogBase (Join-Path $script:Logs 'backend')
Save-NativoPid 'backend' $proc.Id

if (-not $SemEspera) {
    if (-not (Wait-NativoHttp "http://127.0.0.1:$Porta/api/v1/health/ready" 90)) {
        Write-Host 'O backend não ficou pronto em 90 s. Últimas linhas do registro:' -ForegroundColor Red
        foreach ($arq in 'backend.err.log', 'backend.log') {
            $caminho = Join-Path $script:Logs $arq
            if (Test-Path -LiteralPath $caminho) { Get-Content -LiteralPath $caminho -Tail 30 }
        }
        throw 'Falha ao iniciar o backend (veja .native\logs).'
    }
}

Write-Host ''
Write-Host "BoardHub:         http://localhost:$Porta" -ForegroundColor Green
Write-Host "E-mails de teste: $urlEmails"
Write-Host 'Registros:        .native\logs   |   Parar: .\scripts\windows\parar-nativo.ps1'
Write-Host 'Lembrete: modo SOMENTE PARA TESTES; use contas e e-mails fictícios (@example.test).'
Write-Host 'Se você encerrar sua sessão do Windows, os processos são encerrados; rode este script de novo.'
