# Funções comuns do MODO NATIVO (sem Docker) — DT-025. Não execute diretamente:
# os scripts *-nativo.ps1 fazem `. (Join-Path $PSScriptRoot '_nativo-comum.ps1')`.
# Compatível com Windows PowerShell 5.1 (Windows Server 2019). Só para TESTES; nunca para produção.

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
    Write-Verbose 'Não foi possível habilitar TLS 1.2 explicitamente.'
}

$script:Raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:Nativo = Join-Path $script:Raiz '.native'
$script:Ferramentas = Join-Path $script:Nativo 'tools'
$script:Dados = Join-Path $script:Nativo 'data'
$script:PgDados = Join-Path $script:Dados 'pg'
$script:Logs = Join-Path $script:Nativo 'logs'
$script:Run = Join-Path $script:Nativo 'run'
$script:ArquivoEnv = Join-Path $script:Nativo '.env'
$script:Backend = Join-Path $script:Raiz 'backend'
$script:FrontendDist = Join-Path (Join-Path $script:Raiz 'frontend') 'dist'
$script:ArquivoEmails = Join-Path $script:Dados 'emails.jsonl'

# uv e Python ficam dentro de .native (apagar a pasta desfaz tudo).
$env:UV_PYTHON_INSTALL_DIR = Join-Path $script:Nativo 'python'
$env:UV_CACHE_DIR = Join-Path $script:Nativo 'uv-cache'
$env:UV_LINK_MODE = 'copy'

# ---------- Saída ----------

function Write-Passo {
    param([string]$Mensagem)
    Write-Host "==> $Mensagem" -ForegroundColor Cyan
}

function Write-Aviso {
    param([string]$Mensagem)
    Write-Host "AVISO: $Mensagem" -ForegroundColor Yellow
}

function Write-Ok {
    param([string]$Mensagem)
    Write-Host "  ok  $Mensagem" -ForegroundColor Green
}

# ---------- Pastas, segredos e configuração ----------

function Initialize-NativoPasta {
    foreach ($pasta in @($script:Nativo, $script:Ferramentas, $script:Dados, $script:Logs, $script:Run)) {
        if (-not (Test-Path -LiteralPath $pasta)) {
            $null = New-Item -ItemType Directory -Path $pasta
        }
    }
}

function Get-NativoSegredo {
    param([int]$Bytes = 24)
    $b = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($b) } finally { $rng.Dispose() }
    ([Convert]::ToBase64String($b)).Replace('+', '-').Replace('/', '_').TrimEnd('=')
}

function Get-NativoEnv {
    $valores = [ordered]@{}
    if (Test-Path -LiteralPath $script:ArquivoEnv) {
        foreach ($linha in @(Get-Content -LiteralPath $script:ArquivoEnv -Encoding UTF8)) {
            if ($linha -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $valores[$Matches[1]] = $Matches[2]
            }
        }
    }
    return $valores
}

function Protect-NativoArquivo {
    param([string]$Caminho)
    try {
        $eu = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $null = & icacls.exe $Caminho /inheritance:r /grant:r "${eu}:(R,W)" 2>&1
    } catch {
        Write-Verbose "Não foi possível restringir as permissões de $Caminho."
    }
}

function Save-NativoEnv {
    param([System.Collections.IDictionary]$Valores)
    Initialize-NativoPasta
    $linhas = @('# Gerado por instalar-nativo.ps1 (DT-025). Contém segredos: não compartilhe nem versione.')
    foreach ($chave in $Valores.Keys) { $linhas += "$chave=$($Valores[$chave])" }
    [System.IO.File]::WriteAllLines($script:ArquivoEnv, $linhas, (New-Object System.Text.UTF8Encoding($false)))
    Protect-NativoArquivo $script:ArquivoEnv
}

# Exporta a configuração para o ambiente do processo (herdado pelos filhos). Chaves NATIVO_* são só
# dos scripts e não vão para o backend.
function Import-NativoEnv {
    $valores = Get-NativoEnv
    if ($valores.Count -eq 0) {
        throw 'Configuração não encontrada. Rode primeiro: .\scripts\windows\instalar-nativo.ps1'
    }
    foreach ($chave in $valores.Keys) {
        if (-not $chave.StartsWith('NATIVO_')) {
            [Environment]::SetEnvironmentVariable($chave, [string]$valores[$chave], 'Process')
        }
    }
    return $valores
}

# ---------- Download, hash e arquivos ----------

function Save-NativoArquivo {
    param([string]$Url, [string]$Destino)
    $tentativa = 0
    while ($true) {
        $tentativa++
        try {
            Invoke-WebRequest -Uri $Url -OutFile $Destino -UseBasicParsing
            return
        } catch {
            if ($tentativa -ge 3) { throw "Falha ao baixar ${Url}: $($_.Exception.Message)" }
            Start-Sleep -Seconds (3 * $tentativa)
        }
    }
}

function Get-NativoTexto {
    param([string]$Url)
    $conteudo = (Invoke-WebRequest -Uri $Url -UseBasicParsing).Content
    if ($conteudo -is [byte[]]) { return [System.Text.Encoding]::UTF8.GetString($conteudo) }
    return [string]$conteudo
}

function Assert-NativoSha256 {
    param([string]$Arquivo, [string]$Esperado)
    $real = (Get-FileHash -LiteralPath $Arquivo -Algorithm SHA256).Hash
    if ($real -ne $Esperado.Trim().ToUpperInvariant()) {
        Remove-Item -LiteralPath $Arquivo -Force -ErrorAction SilentlyContinue
        throw "SHA-256 diferente do esperado para $(Split-Path -Leaf $Arquivo) (esperado $Esperado, obtido $real). Arquivo descartado."
    }
}

# Procura num arquivo de checksums ("<hash>  <nome>", ou só o hash) a linha cujo nome casa com
# $PadraoNome (regex; vazio = qualquer). Devolve @{ Hash; Nome } ou $null.
function Get-NativoHashDeLista {
    param([string]$Texto, [string]$PadraoNome = '')
    foreach ($linha in ($Texto -split "`r?`n")) {
        if ($linha -match '^\s*([0-9a-fA-F]{64})(?:\s+\*?(\S+))?\s*$') {
            $hash = $Matches[1].ToUpperInvariant()
            $nome = ''
            if ($Matches.ContainsKey(2)) { $nome = $Matches[2] }
            if ($PadraoNome -eq '' -or $nome -match $PadraoNome) {
                return [pscustomobject]@{ Hash = $hash; Nome = $nome }
            }
        }
    }
    return $null
}

function Expand-NativoZip {
    param([string]$Zip, [string]$Destino)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path -LiteralPath $Destino) { Remove-Item -LiteralPath $Destino -Recurse -Force }
    [System.IO.Compression.ZipFile]::ExtractToDirectory($Zip, $Destino)
}

function Get-NativoTemporario {
    $caminho = Join-Path ([System.IO.Path]::GetTempPath()) ('boardhub-' + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $caminho
    return $caminho
}

# ---------- Execução de programas ----------

function ConvertTo-NativoArg {
    param([string]$Valor)
    if ($Valor -ne '' -and $Valor -notmatch '[\s"]') { return $Valor }
    $esc = $Valor -replace '(\\*)"', '$1$1\"'
    $esc = $esc -replace '(\\+)$', '$1$1'
    return '"' + $esc + '"'
}

# Executa e espera. Lê a saída sem travar quando o programa deixa um filho vivo (ex.: pg_ctl start).
function Invoke-NativoExe {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Argumentos = @(),
        [string]$Etapa = '',
        [string]$Diretorio = '',
        [int]$TempoMaximoSegundos = 1800,
        [switch]$Tolerar
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.Arguments = (@($Argumentos | ForEach-Object { ConvertTo-NativoArg $_ })) -join ' '
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    if ($Diretorio -ne '') { $psi.WorkingDirectory = $Diretorio }
    $proc = [System.Diagnostics.Process]::Start($psi)
    $tarefaOut = $proc.StandardOutput.ReadToEndAsync()
    $tarefaErr = $proc.StandardError.ReadToEndAsync()
    if (-not $proc.WaitForExit($TempoMaximoSegundos * 1000)) {
        try { $proc.Kill() } catch { Write-Verbose 'Processo já encerrado.' }
        throw "Tempo esgotado em: $Etapa"
    }
    $null = $tarefaOut.Wait(5000)
    $null = $tarefaErr.Wait(5000)
    $saida = ''
    if ($tarefaOut.IsCompleted) { $saida += $tarefaOut.Result }
    if ($tarefaErr.IsCompleted) { $saida += $tarefaErr.Result }
    $codigo = $proc.ExitCode
    if ($codigo -ne 0 -and -not $Tolerar) {
        $linhas = @($saida -split "`r?`n" | Where-Object { $_ -ne '' })
        $final = ($linhas | Select-Object -Last 25) -join [Environment]::NewLine
        throw "Falha em '$Etapa' (código $codigo)." + [Environment]::NewLine + $final
    }
    [pscustomobject]@{ Codigo = $codigo; Saida = $saida }
}

# Inicia em segundo plano com a saída em arquivos; devolve o processo.
function Invoke-NativoSegundoPlano {
    param(
        [string]$Exe,
        [string[]]$Argumentos,
        [string]$Diretorio,
        [string]$LogBase
    )
    $argLinha = (@($Argumentos | ForEach-Object { ConvertTo-NativoArg $_ })) -join ' '
    Start-Process -FilePath $Exe -ArgumentList $argLinha -WorkingDirectory $Diretorio `
        -RedirectStandardOutput "$LogBase.log" -RedirectStandardError "$LogBase.err.log" `
        -WindowStyle Hidden -PassThru
}

function Save-NativoPid {
    param([string]$Nome, [int]$Id)
    Initialize-NativoPasta
    Set-Content -LiteralPath (Join-Path $script:Run "$Nome.pid") -Value $Id -Encoding ASCII
}

# Só devolve o processo se o PID guardado ainda é um programa desta instalação (evita matar outro).
function Get-NativoProcesso {
    param([string]$Nome)
    $arquivo = Join-Path $script:Run "$Nome.pid"
    if (-not (Test-Path -LiteralPath $arquivo)) { return $null }
    $texto = (Get-Content -LiteralPath $arquivo -Encoding ASCII | Select-Object -First 1)
    $id = 0
    if (-not [int]::TryParse([string]$texto, [ref]$id)) { return $null }
    $proc = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($null -eq $proc) { return $null }
    try {
        $caminho = $proc.Path
    } catch {
        return $null
    }
    if ([string]::IsNullOrEmpty($caminho) -or -not $caminho.StartsWith($script:Raiz, [StringComparison]::OrdinalIgnoreCase)) {
        return $null
    }
    return $proc
}

function Close-NativoProcesso {
    param([string]$Nome)
    $proc = Get-NativoProcesso $Nome
    if ($null -ne $proc) {
        # /T encerra a árvore (o python do venv é um lançador que cria o interpretador filho).
        $null = Invoke-NativoExe -Exe (Join-Path $env:windir 'System32\taskkill.exe') `
            -Argumentos @('/PID', [string]$proc.Id, '/T', '/F') -Etapa "encerrar $Nome" -Tolerar
        Write-Ok "$Nome encerrado"
    }
    Remove-Item -LiteralPath (Join-Path $script:Run "$Nome.pid") -Force -ErrorAction SilentlyContinue
}

function Test-NativoPortaLivre {
    param([int]$Porta)
    $escuta = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Porta)
    try {
        $escuta.Start()
        return $true
    } catch {
        return $false
    } finally {
        try { $escuta.Stop() } catch { Write-Verbose 'Listener já parado.' }
    }
}

function Wait-NativoHttp {
    param([string]$Url, [int]$TempoSegundos = 90)
    $limite = (Get-Date).AddSeconds($TempoSegundos)
    while ((Get-Date) -lt $limite) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { return $true }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

# ---------- Ferramentas ----------

function Get-NativoUvExe {
    $local = Join-Path $script:Ferramentas 'uv\uv.exe'
    if (Test-Path -LiteralPath $local) { return $local }
    $cmd = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }
    return $null
}

function Get-NativoPythonVenv {
    $caminho = Join-Path $script:Backend '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $caminho) { return $caminho }
    return $null
}

# Pasta bin do PostgreSQL 17: a portátil de .native, a indicada no .env ou a instalada no sistema.
function Get-NativoPgBin {
    $portatil = Join-Path $script:Ferramentas 'pgsql\bin'
    $env_ = Get-NativoEnv
    $candidatos = @($portatil)
    if ($env_.Contains('NATIVO_PG_BIN')) { $candidatos = @($env_['NATIVO_PG_BIN']) + $candidatos }
    $candidatos += (Join-Path ${env:ProgramFiles} 'PostgreSQL\17\bin')
    foreach ($c in $candidatos) {
        if ($c -and (Test-Path -LiteralPath (Join-Path $c 'pg_ctl.exe'))) { return $c }
    }
    return $null
}

function Get-NativoPgSituacao {
    param([string]$PgBin)
    $r = Invoke-NativoExe -Exe (Join-Path $PgBin 'pg_ctl.exe') -Argumentos @('status', '-D', $script:PgDados) `
        -Etapa 'status do PostgreSQL' -Tolerar
    return ($r.Codigo -eq 0)
}

function Invoke-NativoPgIniciar {
    param([string]$PgBin)
    if (Get-NativoPgSituacao $PgBin) { return }
    Initialize-NativoPasta
    $porta = '5433'
    $cfg = Get-NativoEnv
    if ($cfg.Contains('DB_PORT')) { $porta = [string]$cfg['DB_PORT'] }
    # Só loopback (127.0.0.1): o banco nunca fica exposto na rede.
    $opcoes = "-p $porta -c listen_addresses=127.0.0.1"
    $null = Invoke-NativoExe -Exe (Join-Path $PgBin 'pg_ctl.exe') `
        -Argumentos @('start', '-D', $script:PgDados, '-l', (Join-Path $script:Logs 'postgres.log'), '-o', $opcoes, '-w', '-t', '90') `
        -Etapa 'iniciar o PostgreSQL (veja .native\logs\postgres.log)' -TempoMaximoSegundos 150
}

function Invoke-NativoPgParar {
    param([string]$PgBin)
    if (-not (Get-NativoPgSituacao $PgBin)) { return }
    $null = Invoke-NativoExe -Exe (Join-Path $PgBin 'pg_ctl.exe') `
        -Argumentos @('stop', '-D', $script:PgDados, '-m', 'fast', '-w', '-t', '60') -Etapa 'parar o PostgreSQL' `
        -TempoMaximoSegundos 120
}

function Test-NativoAdministrador {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
