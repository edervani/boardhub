<#
.SYNOPSIS
    Para o BoardHub em modo nativo (backend, Mailpit e PostgreSQL). Os dados são mantidos.

.PARAMETER ManterBanco
    Deixa o PostgreSQL rodando.

.PARAMETER ApagarDados
    Apaga o banco (.native\data\pg) e os e-mails de teste. Pede confirmação, exceto com -Sim.
    A configuração (.native\.env) e as ferramentas baixadas são mantidas.

.PARAMETER Sim
    Confirma -ApagarDados sem perguntar.
#>
[CmdletBinding()]
param(
    [switch]$ManterBanco,
    [switch]$ApagarDados,
    [switch]$Sim
)

. (Join-Path $PSScriptRoot '_nativo-comum.ps1')

Close-NativoProcesso 'backend'
Close-NativoProcesso 'mailpit'

$pgBin = Get-NativoPgBin
if ($pgBin -and (Test-Path -LiteralPath (Join-Path $script:PgDados 'PG_VERSION'))) {
    if (-not $ManterBanco -or $ApagarDados) {
        Invoke-NativoPgParar $pgBin
        Write-Ok 'PostgreSQL parado'
    }
}

if ($ApagarDados) {
    $confirmado = $Sim
    if (-not $confirmado) {
        $resposta = Read-Host 'Apagar TODOS os dados de teste (banco e e-mails)? Digite SIM para confirmar'
        $confirmado = ($resposta -ceq 'SIM')
    }
    if (-not $confirmado) {
        Write-Host 'Nada foi apagado.'
        exit 0
    }
    # Só apaga dentro de .native\data (nunca outro caminho).
    foreach ($alvo in @($script:PgDados, $script:ArquivoEmails)) {
        if ($alvo.StartsWith($script:Dados, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $alvo)) {
            Remove-Item -LiteralPath $alvo -Recurse -Force
        }
    }
    Write-Host 'Dados apagados. Rode instalar-nativo.ps1 para recriar o banco.' -ForegroundColor Yellow
}
