# Utilitarios do CI no Windows (Windows PowerShell 5.1): publicam a saida das falhas como anotacao,
# legivel pela API do GitHub mesmo sem acesso ao log completo (equivalente PowerShell de run.sh).
# Uso:  . "$env:GITHUB_WORKSPACE\scripts\ci\ci-win.ps1"; Invoke-Passo 'rotulo' { comando }

function ConvertTo-Anotacao {
    param([string[]]$Linhas, [int]$Ultimas = 60)
    $texto = (@($Linhas | Select-Object -Last $Ultimas) -join "`n")
    return $texto.Replace('%', '%25').Replace("`r", '').Replace("`n", '%0A')
}

function Write-Anotacao {
    param([string]$Titulo, [string[]]$Linhas, [string]$Nivel = 'error', [int]$Ultimas = 60)
    Write-Host "::$Nivel title=$Titulo::$(ConvertTo-Anotacao $Linhas $Ultimas)"
}

function Invoke-Passo {
    param([string]$Rotulo, [scriptblock]$Comando)
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = 0
    $coletadas = New-Object System.Collections.ArrayList
    $codigo = 0
    try {
        & $Comando *>&1 | ForEach-Object {
            $linha = $_.ToString()
            [void]$coletadas.Add($linha)
            $linha
        }
        $codigo = $LASTEXITCODE
    } catch {
        [void]$coletadas.Add("EXCECAO: $($_.Exception.Message)")
        $codigo = 1
    }
    if ($codigo -ne 0) {
        Write-Anotacao $Rotulo $coletadas
        exit $codigo
    }
}
