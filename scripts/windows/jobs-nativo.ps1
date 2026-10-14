<#
.SYNOPSIS
    Rotina diária do BoardHub em modo nativo (`python -m app.jobs`, doc 13 §5; DT-020/P-22 g).

.DESCRIPTION
    Conclui exclusões de conta vencidas, apaga exportações expiradas e remove cadastros de menores
    sem confirmação. Sem agendamento, NADA disso acontece sozinho. Formas de uso:
      .\jobs-nativo.ps1                      executa uma vez agora (código de saída != 0 se falhar)
      .\jobs-nativo.ps1 -RegistrarTarefa     agenda no Agendador de Tarefas (diário, 03:30; só com
                                             você conectado, sem precisar de administrador)
      .\jobs-nativo.ps1 -RemoverTarefa       remove o agendamento
      .\jobs-nativo.ps1 -Laco                fica em primeiro plano e repete a cada 24 h
    O banco precisa estar no ar (iniciar-nativo.ps1).

.PARAMETER Hora
    Horário local do agendamento (HH:mm). Padrão 03:30.
#>
[CmdletBinding()]
param(
    [switch]$RegistrarTarefa,
    [switch]$RemoverTarefa,
    [switch]$Laco,
    [string]$Hora = '03:30'
)

. (Join-Path $PSScriptRoot '_nativo-comum.ps1')

$nomeTarefa = 'BoardHub-Jobs-Nativo'

function Invoke-NativoRotina {
    $null = Import-NativoEnv
    $python = Get-NativoPythonVenv
    if (-not $python) { throw 'Dependências não instaladas. Rode: .\scripts\windows\instalar-nativo.ps1' }
    $pgBin = Get-NativoPgBin
    if (-not $pgBin -or -not (Get-NativoPgSituacao $pgBin)) {
        throw 'O banco não está no ar. Rode: .\scripts\windows\iniciar-nativo.ps1'
    }
    Initialize-NativoPasta
    $registro = Join-Path $script:Logs 'jobs.log'
    $r = Invoke-NativoExe -Exe $python -Argumentos @('-m', 'app.jobs') -Diretorio $script:Backend -Etapa 'python -m app.jobs' -Tolerar
    # O módulo registra apenas contagens (sem dados pessoais); a saída vai ao arquivo.
    $carimbo = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -LiteralPath $registro -Encoding UTF8 -Value "[$carimbo] código de saída $($r.Codigo)"
    if ($r.Saida.Trim() -ne '') { Add-Content -LiteralPath $registro -Encoding UTF8 -Value $r.Saida.TrimEnd() }
    return $r.Codigo
}

if ($RemoverTarefa) {
    Unregister-ScheduledTask -TaskName $nomeTarefa -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tarefa '$nomeTarefa' removida (se existia)."
    exit 0
}

if ($RegistrarTarefa) {
    $scriptJobs = Join-Path $PSScriptRoot 'jobs-nativo.ps1'
    $acao = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptJobs`""
    $gatilho = New-ScheduledTaskTrigger -Daily -At $Hora
    $eu = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $eu -LogonType Interactive
    try {
        $null = Register-ScheduledTask -TaskName $nomeTarefa -Action $acao -Trigger $gatilho -Principal $principal -Force `
            -Description 'BoardHub (modo nativo de teste): rotina diária python -m app.jobs'
    } catch {
        Write-Host "Não foi possível registrar a tarefa: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'Alternativa: deixe uma janela aberta com  .\scripts\windows\jobs-nativo.ps1 -Laco' -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Tarefa '$nomeTarefa' registrada: todo dia às $Hora, com a sua sessão conectada." -ForegroundColor Green
    Write-Host 'Resultados em .native\logs\jobs.log. O banco precisa estar no ar nesse horário.'
    exit 0
}

if ($Laco) {
    Write-Host 'Rotina diária em laço (Ctrl+C para sair). Executa agora e depois a cada 24 h.'
    while ($true) {
        try {
            $codigo = Invoke-NativoRotina
            Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm') rotina concluída (código $codigo)."
        } catch {
            Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm') falha: $($_.Exception.Message)" -ForegroundColor Red
        }
        Start-Sleep -Seconds 86400
    }
}

$codigoFinal = Invoke-NativoRotina
Write-Host "Rotina diária concluída (código de saída $codigoFinal)."
exit $codigoFinal
