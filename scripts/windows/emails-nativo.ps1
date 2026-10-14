<#
.SYNOPSIS
    Mostra os e-mails de teste gravados pelo modo nativo (MAIL_BACKEND=file), com os links.

.DESCRIPTION
    O arquivo .native\data\emails.jsonl existe só em testes locais e contém links de verificação:
    não o compartilhe. Aceita -Quantidade (padrão 5) e -Para (filtra por destinatário).
#>
[CmdletBinding()]
param(
    [int]$Quantidade = 5,
    [string]$Para = ''
)

. (Join-Path $PSScriptRoot '_nativo-comum.ps1')

if (-not (Test-Path -LiteralPath $script:ArquivoEmails)) {
    Write-Host 'Nenhum e-mail gravado ainda.'
    exit 0
}
$mensagens = @()
foreach ($linha in @(Get-Content -LiteralPath $script:ArquivoEmails -Encoding UTF8)) {
    if ($linha.Trim() -eq '') { continue }
    $m = $linha | ConvertFrom-Json
    if ($Para -eq '' -or $m.to -eq $Para) { $mensagens += $m }
}
foreach ($m in @($mensagens | Select-Object -Last $Quantidade)) {
    Write-Host "--- $($m.ts)  para: $($m.to)  assunto: $($m.subject)" -ForegroundColor Cyan
    Write-Host $m.body
}
