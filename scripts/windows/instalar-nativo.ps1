<#
.SYNOPSIS
    Instala o BoardHub em MODO NATIVO (sem Docker) para TESTES no Windows (DT-025).

.DESCRIPTION
    Pensado para Windows Server 2019 / Windows PowerShell 5.1, sem administrador e sem virtualização.
    Tudo fica dentro da pasta .native\ do projeto (apagá-la desfaz a instalação):
      - uv (baixado do GitHub; SHA-256 verificado) -> instala Python 3.13 e as dependências
        (`uv sync --locked`);
      - PostgreSQL 17 portátil (zip de binários da EDB), cluster próprio, só em 127.0.0.1;
      - banco e usuário da aplicação com senhas ALEATÓRIAS, gravadas em .native\.env (ignorado pelo git);
      - migrações (`alembic upgrade head`);
      - opcional: Node 24 portátil (-ConstruirFrontend) e Mailpit (-Mailpit).
    Idempotente: pode ser executado de novo. Não use em produção.

.PARAMETER SomenteVerificar
    Não instala nada: informa o que está pronto e o que falta (código de saída 1 se faltar algo).

.PARAMETER ConstruirFrontend
    Constrói o frontend com Node 24 (usa o do PATH se for 24; senão baixa o portátil). Sem esta chave,
    é preciso ter frontend\dist (pacote boardhub-windows-nativo.zip do CI).

.PARAMETER Mailpit
    Baixa também o Mailpit (caixa de e-mails de teste com interface web). Sem ele, os e-mails vão
    para .native\data\emails.jsonl (veja emails-nativo.ps1).

.PARAMETER UsarPostgresDe
    Pasta \bin de um PostgreSQL 17 já instalado (alternativa offline ao download).

.PARAMETER PostgresZip
    Zip de binários do PostgreSQL já baixado (alternativa offline). Veja também -PostgresZipUrl.

.PARAMETER PostgresSha256
    Se informado, o zip do PostgreSQL só é aceito com este SHA-256.

.PARAMETER PostgresPortatil
    Força o PostgreSQL portátil mesmo que haja um PostgreSQL 17 instalado no sistema.

.PARAMETER InstalarRuntimeVC
    Se faltar o Visual C++ Runtime, baixa (assinatura Microsoft verificada) e o instala; pede elevação.

.EXAMPLE
    .\scripts\windows\instalar-nativo.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\instalar-nativo.ps1 -Mailpit
#>
[CmdletBinding()]
param(
    [switch]$SomenteVerificar,
    [switch]$ConstruirFrontend,
    [switch]$Mailpit,
    [int]$Porta = 8080,
    [int]$PortaBanco = 5433,
    [string]$UsarPostgresDe = '',
    [string]$PostgresZip = '',
    [string]$PostgresZipUrl = '',
    [string]$PostgresSha256 = '',
    [switch]$PostgresPortatil,
    [string]$UvZip = '',
    [string]$MailpitZip = '',
    [string]$NodeZip = '',
    [switch]$InstalarRuntimeVC
)

. (Join-Path $PSScriptRoot '_nativo-comum.ps1')

$script:PortaExplicita = $PSBoundParameters.ContainsKey('Porta')
$script:PortaBancoExplicita = $PSBoundParameters.ContainsKey('PortaBanco')

$script:Itens = New-Object System.Collections.ArrayList

function Add-NativoItem {
    param([string]$Nome, [bool]$Ok, [string]$Detalhe, [bool]$Obrigatorio = $true)
    $null = $script:Itens.Add([pscustomobject]@{ Nome = $Nome; Ok = $Ok; Detalhe = $Detalhe; Obrigatorio = $Obrigatorio })
}

function Test-NativoRuntimeVC {
    $sistema = Join-Path $env:windir 'System32'
    (Test-Path -LiteralPath (Join-Path $sistema 'vcruntime140.dll')) -and (Test-Path -LiteralPath (Join-Path $sistema 'vcruntime140_1.dll'))
}

function Get-NativoNodeDir {
    $cmd = Get-Command node.exe -ErrorAction SilentlyContinue
    $candidatos = @()
    if ($null -ne $cmd) { $candidatos += (Split-Path -Parent $cmd.Source) }
    $candidatos += (Join-Path $script:Ferramentas 'node')
    foreach ($dir in $candidatos) {
        $exe = Join-Path $dir 'node.exe'
        if (Test-Path -LiteralPath $exe) {
            $r = Invoke-NativoExe -Exe $exe -Argumentos @('--version') -Etapa 'versão do Node' -Tolerar
            if ($r.Saida -match '^v24\.') { return $dir }
        }
    }
    return $null
}

function Get-NativoDiagnostico {
    $script:Itens.Clear()
    $versaoOk = ($PSVersionTable.PSVersion -ge [version]'5.1')
    Add-NativoItem 'Windows PowerShell 5.1 ou superior' $versaoOk "versão $($PSVersionTable.PSVersion)"
    Add-NativoItem 'Windows de 64 bits' ([Environment]::Is64BitOperatingSystem) ''
    Add-NativoItem 'Visual C++ Runtime (vcruntime140)' (Test-NativoRuntimeVC) 'necessário ao Python e ao PostgreSQL; use -InstalarRuntimeVC'

    $uv = Get-NativoUvExe
    Add-NativoItem 'uv' ($null -ne $uv) $(if ($uv) { $uv } else { 'será baixado do GitHub' })

    $pythonOk = $false
    if ($uv) {
        $r = Invoke-NativoExe -Exe $uv -Argumentos @('python', 'find', '3.13') -Etapa 'localizar Python 3.13' -Tolerar
        $pythonOk = ($r.Codigo -eq 0)
    }
    Add-NativoItem 'Python 3.13' $pythonOk 'instalado pelo uv dentro de .native\python'

    $venv = Get-NativoPythonVenv
    $depsOk = $false
    if ($venv) {
        $r = Invoke-NativoExe -Exe $venv -Argumentos @('-c', 'import fastapi, uvicorn, psycopg, alembic, argon2, chess') `
            -Etapa 'verificar dependências' -Tolerar
        $depsOk = ($r.Codigo -eq 0)
    }
    Add-NativoItem 'Dependências do backend (uv sync --locked)' $depsOk 'backend\.venv'

    $pgBin = Get-NativoPgBin
    $detalhe = 'PostgreSQL 17 portátil será baixado'
    if ($pgBin) { $detalhe = $pgBin }
    Add-NativoItem 'PostgreSQL 17' ($null -ne $pgBin) $detalhe
    Add-NativoItem 'Cluster do banco inicializado' (Test-Path -LiteralPath (Join-Path $script:PgDados 'PG_VERSION')) '.native\data\pg'
    Add-NativoItem 'Configuração local (.native\.env)' (Test-Path -LiteralPath $script:ArquivoEnv) 'segredos aleatórios'
    Add-NativoItem 'Frontend construído (frontend\dist)' (Test-Path -LiteralPath (Join-Path $script:FrontendDist 'index.html')) `
        'use o pacote do CI ou -ConstruirFrontend'
    if ($ConstruirFrontend) {
        $nodeDir = Get-NativoNodeDir
        Add-NativoItem 'Node.js 24' ($null -ne $nodeDir) 'portátil em .native\tools\node'
    }
    if ($Mailpit) {
        Add-NativoItem 'Mailpit' (Test-Path -LiteralPath (Join-Path $script:Ferramentas 'mailpit\mailpit.exe')) '.native\tools\mailpit' $false
    }
}

function Show-NativoDiagnostico {
    $faltando = 0
    foreach ($item in $script:Itens) {
        if ($item.Ok) {
            Write-Ok $item.Nome
        } else {
            if ($item.Obrigatorio) { $faltando++ }
            Write-Host "  FALTA  $($item.Nome)  ($($item.Detalhe))" -ForegroundColor Yellow
        }
    }
    return $faltando
}

# ---------- Etapas de instalação ----------

function Install-NativoRuntimeVC {
    if (Test-NativoRuntimeVC) { return }
    $mensagem = 'Falta o "Visual C++ Redistributable 2015-2022 (x64)". Baixe em https://aka.ms/vs/17/release/vc_redist.x64.exe e instale (exige administrador), ou rode este script com -InstalarRuntimeVC.'
    if (-not $InstalarRuntimeVC) { throw $mensagem }
    Write-Passo 'Instalando o Visual C++ Runtime (assinatura Microsoft verificada)'
    $tmp = Get-NativoTemporario
    try {
        $exe = Join-Path $tmp 'vc_redist.x64.exe'
        Save-NativoArquivo 'https://aka.ms/vs/17/release/vc_redist.x64.exe' $exe
        $assinatura = Get-AuthenticodeSignature -FilePath $exe
        if ($assinatura.Status -ne 'Valid' -or $assinatura.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
            throw 'Assinatura do vc_redist.x64.exe não é uma assinatura válida da Microsoft; instalação cancelada.'
        }
        $p = Start-Process -FilePath $exe -ArgumentList '/install', '/quiet', '/norestart' -Verb RunAs -Wait -PassThru
        if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "O instalador do Visual C++ terminou com código $($p.ExitCode)." }
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-NativoRuntimeVC)) { throw 'O Visual C++ Runtime continua ausente. Reinicie o Windows e rode de novo.' }
}

function Install-NativoUv {
    if (Get-NativoUvExe) { return }
    Write-Passo 'Instalando uv (gerenciador de Python e dependências)'
    $tmp = Get-NativoTemporario
    try {
        $zip = Join-Path $tmp 'uv.zip'
        if ($UvZip) {
            Copy-Item -LiteralPath $UvZip -Destination $zip
        } else {
            $url = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip'
            Save-NativoArquivo $url $zip
            $item = Get-NativoHashDeLista (Get-NativoTexto "$url.sha256")
            if ($null -eq $item) { throw 'Não foi possível ler o SHA-256 publicado do uv; instalação cancelada.' }
            Assert-NativoSha256 $zip $item.Hash
            Write-Ok "uv baixado e SHA-256 conferido ($($item.Hash.Substring(0, 12))...)"
        }
        $extraido = Join-Path $tmp 'x'
        Expand-NativoZip $zip $extraido
        $destino = Join-Path $script:Ferramentas 'uv'
        $null = New-Item -ItemType Directory -Force -Path $destino
        foreach ($exe in @(Get-ChildItem -LiteralPath $extraido -Recurse -Filter '*.exe')) {
            Copy-Item -LiteralPath $exe.FullName -Destination $destino -Force
        }
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (Get-NativoUvExe)) { throw 'uv.exe não foi encontrado após a extração.' }
}

function Install-NativoPythonEDependencia {
    $uv = Get-NativoUvExe
    $r = Invoke-NativoExe -Exe $uv -Argumentos @('python', 'find', '3.13') -Etapa 'localizar Python 3.13' -Tolerar
    if ($r.Codigo -ne 0) {
        Write-Passo 'Instalando Python 3.13 (uv, em .native\python)'
        $null = Invoke-NativoExe -Exe $uv -Argumentos @('python', 'install', '3.13') -Etapa 'uv python install 3.13'
    }
    Write-Passo 'Instalando dependências do backend (uv sync --locked)'
    $null = Invoke-NativoExe -Exe $uv -Argumentos @('sync', '--locked', '--no-dev', '--python', '3.13') `
        -Diretorio $script:Backend -Etapa 'uv sync --locked'
}

function Resolve-NativoPostgresUrl {
    for ($menor = 14; $menor -ge 0; $menor--) {
        foreach ($build in 5, 4, 3, 2, 1) {
            $url = "https://get.enterprisedb.com/postgresql/postgresql-17.$menor-$build-windows-x64-binaries.zip"
            try {
                $r = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing
                if ($r.StatusCode -eq 200) { return $url }
            } catch {
                Write-Verbose "Indisponível: $url"
            }
        }
    }
    throw 'Não foi possível descobrir o zip de binários do PostgreSQL 17. Baixe-o manualmente (EDB: "PostgreSQL binaries") e use -PostgresZip, ou informe -PostgresZipUrl / -UsarPostgresDe.'
}

function Install-NativoPgPortatil {
    $portatil = Join-Path $script:Ferramentas 'pgsql\bin'
    if (Test-Path -LiteralPath (Join-Path $portatil 'pg_ctl.exe')) { return }
    if ($UsarPostgresDe) {
        if (-not (Test-Path -LiteralPath (Join-Path $UsarPostgresDe 'pg_ctl.exe'))) {
            throw "pg_ctl.exe não encontrado em $UsarPostgresDe"
        }
        return
    }
    if (-not $PostgresPortatil -and (Get-NativoPgBin)) { return }

    Write-Passo 'Instalando PostgreSQL 17 portátil (zip de binários da EDB)'
    $tmp = Get-NativoTemporario
    try {
        $zip = $PostgresZip
        if (-not $zip) {
            $url = $PostgresZipUrl
            if (-not $url) { $url = Resolve-NativoPostgresUrl }
            Write-Host "  baixando $url (centenas de MB; pode demorar)"
            $zip = Join-Path $tmp 'postgres.zip'
            Save-NativoArquivo $url $zip
        }
        $real = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
        if ($PostgresSha256) {
            Assert-NativoSha256 $zip $PostgresSha256
            Write-Ok 'SHA-256 do PostgreSQL conferido com o valor informado'
        } else {
            Write-Aviso "A EDB não publica hash deste zip. SHA-256 obtido: $real (guarde-o para conferir/travar com -PostgresSha256)."
        }
        $extraido = Join-Path $tmp 'x'
        Expand-NativoZip $zip $extraido
        $origem = Join-Path $extraido 'pgsql'
        if (-not (Test-Path -LiteralPath (Join-Path $origem 'bin\pg_ctl.exe'))) { throw 'O zip não contém pgsql\bin\pg_ctl.exe.' }
        foreach ($sobra in 'pgAdmin 4', 'StackBuilder', 'doc') {
            Remove-Item -LiteralPath (Join-Path $origem $sobra) -Recurse -Force -ErrorAction SilentlyContinue
        }
        Move-Item -LiteralPath $origem -Destination (Join-Path $script:Ferramentas 'pgsql')
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    $assinatura = Get-AuthenticodeSignature -FilePath (Join-Path $portatil 'postgres.exe')
    if ($assinatura.Status -eq 'Valid') {
        Write-Ok "postgres.exe com assinatura válida ($($assinatura.SignerCertificate.Subject.Split(',')[0]))"
    } else {
        Write-Aviso "postgres.exe sem assinatura Authenticode válida (status: $($assinatura.Status)). Origem garantida apenas por HTTPS em get.enterprisedb.com."
    }
}

function Test-NativoPostgresVersao {
    param([string]$PgBin)
    $r = Invoke-NativoExe -Exe (Join-Path $PgBin 'postgres.exe') -Argumentos @('--version') -Etapa 'versão do PostgreSQL'
    if ($r.Saida -notmatch '\) 17\.') {
        Write-Aviso "Esperado PostgreSQL 17 (DT-014); encontrado: $($r.Saida.Trim())"
    }
}

function Get-NativoConfigFinal {
    $cfg = Get-NativoEnv
    $padroes = [ordered]@{
        APP_ENV                    = 'development'
        SECRET_KEY                 = (Get-NativoSegredo 48)
        POSTGRES_DB                = 'boardhub'
        POSTGRES_USER              = 'boardhub_app'
        POSTGRES_PASSWORD          = (Get-NativoSegredo 24)
        DB_HOST                    = '127.0.0.1'
        COOKIE_SECURE              = 'false'
        LOG_LEVEL                  = 'INFO'
        MAIL_BACKEND               = 'file'
        MAIL_FROM                  = 'nao-responda@example.test'
        NATIVO_PG_ADMIN_PASSWORD   = (Get-NativoSegredo 24)
    }
    foreach ($chave in $padroes.Keys) {
        if (-not $cfg.Contains($chave)) { $cfg[$chave] = $padroes[$chave] }
    }
    if (-not $cfg.Contains('NATIVO_PORT') -or $script:PortaExplicita) { $cfg['NATIVO_PORT'] = [string]$Porta }
    if (-not $cfg.Contains('DB_PORT') -or $script:PortaBancoExplicita) { $cfg['DB_PORT'] = [string]$PortaBanco }
    # Origem única para CORS e WebSocket (SEC-07): exatamente o que o navegador usa.
    $cfg['FRONTEND_ORIGIN'] = "http://localhost:$($cfg['NATIVO_PORT'])"
    $cfg['MAIL_FILE_PATH'] = $script:ArquivoEmails
    $cfg['SERVE_FRONTEND_DIR'] = $script:FrontendDist
    if ($UsarPostgresDe) { $cfg['NATIVO_PG_BIN'] = $UsarPostgresDe }
    foreach ($nomeSeguro in 'POSTGRES_DB', 'POSTGRES_USER') {
        if ($cfg[$nomeSeguro] -notmatch '^[a-z_][a-z0-9_]{0,40}$') { throw "$nomeSeguro inválido em .native\.env (use letras minúsculas, dígitos e _)." }
    }
    return $cfg
}

function Invoke-NativoPsql {
    param([string]$PgBin, [System.Collections.IDictionary]$Cfg, [string]$Sql, [string]$Base = 'postgres')
    $arquivo = Join-Path $script:Run ('sql-' + [Guid]::NewGuid().ToString('N') + '.sql')
    [System.IO.File]::WriteAllText($arquivo, $Sql, (New-Object System.Text.UTF8Encoding($false)))
    Protect-NativoArquivo $arquivo
    $anterior = $env:PGPASSWORD
    $env:PGPASSWORD = [string]$Cfg['NATIVO_PG_ADMIN_PASSWORD']
    try {
        Invoke-NativoExe -Exe (Join-Path $PgBin 'psql.exe') -Etapa 'psql' -Argumentos @(
            '-h', '127.0.0.1', '-p', [string]$Cfg['DB_PORT'], '-U', 'boardhub_admin', '-d', $Base,
            '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1', '-f', $arquivo)
    } finally {
        $env:PGPASSWORD = $anterior
        Remove-Item -LiteralPath $arquivo -Force -ErrorAction SilentlyContinue
    }
}

function Initialize-NativoBanco {
    param([string]$PgBin, [System.Collections.IDictionary]$Cfg)
    if (-not (Test-Path -LiteralPath (Join-Path $script:PgDados 'PG_VERSION'))) {
        Write-Passo 'Criando o cluster do PostgreSQL (initdb)'
        $pwfile = Join-Path $script:Run 'pg-admin.pw'
        [System.IO.File]::WriteAllText($pwfile, [string]$Cfg['NATIVO_PG_ADMIN_PASSWORD'], (New-Object System.Text.UTF8Encoding($false)))
        Protect-NativoArquivo $pwfile
        try {
            $null = Invoke-NativoExe -Exe (Join-Path $PgBin 'initdb.exe') -Etapa 'initdb' -Argumentos @(
                '-D', $script:PgDados, '-U', 'boardhub_admin', '-A', 'scram-sha-256', '--pwfile', $pwfile,
                '-E', 'UTF8', '--locale=C')
        } finally {
            Remove-Item -LiteralPath $pwfile -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Passo 'Iniciando o PostgreSQL e criando banco e usuário da aplicação'
    Invoke-NativoPgIniciar $PgBin
    $modelo = @'
DO $bh$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '__USUARIO__') THEN
    ALTER ROLE __USUARIO__ WITH LOGIN PASSWORD '__SENHA__';
  ELSE
    CREATE ROLE __USUARIO__ WITH LOGIN PASSWORD '__SENHA__';
  END IF;
END
$bh$;
'@
    $sqlPapel = $modelo.Replace('__USUARIO__', [string]$Cfg['POSTGRES_USER']).Replace('__SENHA__', [string]$Cfg['POSTGRES_PASSWORD'])
    $null = Invoke-NativoPsql $PgBin $Cfg $sqlPapel
    $banco = [string]$Cfg['POSTGRES_DB']
    $existe = Invoke-NativoPsql $PgBin $Cfg "SELECT 1 FROM pg_database WHERE datname = '$banco';"
    if ($existe.Saida.Trim() -ne '1') {
        $null = Invoke-NativoPsql $PgBin $Cfg "CREATE DATABASE $banco OWNER $($Cfg['POSTGRES_USER']) ENCODING 'UTF8' TEMPLATE template0;"
    }
}

function Invoke-NativoMigracao {
    Write-Passo 'Aplicando as migrações (alembic upgrade head)'
    $null = Invoke-NativoExe -Exe (Get-NativoPythonVenv) -Argumentos @('-m', 'alembic', 'upgrade', 'head') `
        -Diretorio $script:Backend -Etapa 'alembic upgrade head'
}

function Install-NativoNode {
    $dir = Get-NativoNodeDir
    if ($null -ne $dir) { return $dir }
    Write-Passo 'Instalando Node.js 24 LTS portátil (SHA-256 conferido contra SHASUMS256.txt)'
    $tmp = Get-NativoTemporario
    try {
        $zip = Join-Path $tmp 'node.zip'
        if ($NodeZip) {
            Copy-Item -LiteralPath $NodeZip -Destination $zip
        } else {
            $base = 'https://nodejs.org/dist/latest-v24.x'
            $item = Get-NativoHashDeLista (Get-NativoTexto "$base/SHASUMS256.txt") '^node-v24\.\d+\.\d+-win-x64\.zip$'
            if ($null -eq $item) { throw 'Zip do Node 24 para Windows x64 não encontrado em SHASUMS256.txt.' }
            Save-NativoArquivo "$base/$($item.Nome)" $zip
            Assert-NativoSha256 $zip $item.Hash
            Write-Ok "Node baixado e SHA-256 conferido ($($item.Nome))"
        }
        $extraido = Join-Path $tmp 'x'
        Expand-NativoZip $zip $extraido
        $pasta = Get-ChildItem -LiteralPath $extraido -Directory | Select-Object -First 1
        Move-Item -LiteralPath $pasta.FullName -Destination (Join-Path $script:Ferramentas 'node')
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    return (Join-Path $script:Ferramentas 'node')
}

function Invoke-NativoBuildFrontend {
    $nodeDir = Install-NativoNode
    $env:PATH = "$nodeDir;$env:PATH"
    $frontend = Join-Path $script:Raiz 'frontend'
    $npm = Join-Path $nodeDir 'npm.cmd'
    Write-Passo 'Construindo o frontend (npm ci && npm run build)'
    $null = Invoke-NativoExe -Exe $npm -Argumentos @('ci', '--no-audit', '--no-fund') -Diretorio $frontend -Etapa 'npm ci'
    $null = Invoke-NativoExe -Exe $npm -Argumentos @('run', 'build') -Diretorio $frontend -Etapa 'npm run build'
    if (-not (Test-Path -LiteralPath (Join-Path $script:FrontendDist 'index.html'))) { throw 'O build não gerou frontend\dist\index.html.' }
}

function Install-NativoMailpit {
    $destino = Join-Path $script:Ferramentas 'mailpit'
    if (Test-Path -LiteralPath (Join-Path $destino 'mailpit.exe')) { return }
    Write-Passo 'Instalando Mailpit (SHA-256 conferido contra checksums.txt)'
    $tmp = Get-NativoTemporario
    try {
        $zip = Join-Path $tmp 'mailpit.zip'
        if ($MailpitZip) {
            Copy-Item -LiteralPath $MailpitZip -Destination $zip
        } else {
            $base = 'https://github.com/axllent/mailpit/releases/latest/download'
            Save-NativoArquivo "$base/mailpit-windows-amd64.zip" $zip
            $item = Get-NativoHashDeLista (Get-NativoTexto "$base/checksums.txt") '^mailpit-windows-amd64\.zip$'
            if ($null -eq $item) { throw 'SHA-256 do Mailpit não encontrado em checksums.txt; instalação cancelada.' }
            Assert-NativoSha256 $zip $item.Hash
            Write-Ok 'Mailpit baixado e SHA-256 conferido'
        }
        $extraido = Join-Path $tmp 'x'
        Expand-NativoZip $zip $extraido
        $null = New-Item -ItemType Directory -Force -Path $destino
        Copy-Item -Path (Join-Path $extraido '*') -Destination $destino -Recurse -Force
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ---------- Execução ----------

if ($SomenteVerificar) {
    Write-Passo 'Verificando o ambiente nativo (nada será instalado)'
    Get-NativoDiagnostico
    $faltando = Show-NativoDiagnostico
    if ($faltando -gt 0) {
        Write-Host "$faltando item(ns) obrigatório(s) faltando. Rode .\scripts\windows\instalar-nativo.ps1" -ForegroundColor Yellow
        exit 1
    }
    Write-Host 'Ambiente nativo pronto.' -ForegroundColor Green
    exit 0
}

Write-Host 'BoardHub - instalação NATIVA (sem Docker). Somente para TESTES; não use em produção.' -ForegroundColor Cyan
Initialize-NativoPasta
Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1' | Unblock-File -ErrorAction SilentlyContinue

Install-NativoRuntimeVC
Install-NativoUv
Install-NativoPythonEDependencia
Install-NativoPgPortatil
$pgBin = $UsarPostgresDe
if (-not $pgBin) { $pgBin = Get-NativoPgBin }
if (-not $pgBin) { throw 'PostgreSQL não encontrado após a instalação.' }
Test-NativoPostgresVersao $pgBin

$config = Get-NativoConfigFinal
Save-NativoEnv $config
Write-Ok 'Configuração gravada em .native\.env (segredos aleatórios; não compartilhe)'
$null = Import-NativoEnv

if ($ConstruirFrontend) { Invoke-NativoBuildFrontend }
if ($Mailpit) { Install-NativoMailpit }

if (-not (Test-NativoPortaLivre ([int]$config['DB_PORT'])) -and -not (Get-NativoPgSituacao $pgBin)) {
    throw "A porta $($config['DB_PORT']) já está em uso por outro programa. Use -PortaBanco com outro número."
}
$pgJaRodava = Get-NativoPgSituacao $pgBin
try {
    Initialize-NativoBanco $pgBin $config
    Invoke-NativoMigracao
} finally {
    if (-not $pgJaRodava) { Invoke-NativoPgParar $pgBin }
}

Write-Passo 'Conferindo o resultado'
Get-NativoDiagnostico
$null = Show-NativoDiagnostico
$faltando = @($script:Itens | Where-Object { -not $_.Ok -and $_.Obrigatorio -and $_.Nome -notlike 'Frontend*' }).Count
if ($faltando -gt 0) { throw "Instalação incompleta: $faltando item(ns) obrigatório(s) faltando." }
Write-Host ''
Write-Host 'Instalação concluída. Próximo passo:  .\scripts\windows\iniciar-nativo.ps1' -ForegroundColor Green
if (-not (Test-Path -LiteralPath (Join-Path $script:FrontendDist 'index.html'))) {
    Write-Aviso 'frontend\dist ainda não existe: baixe o pacote do CI ou rode de novo com -ConstruirFrontend.'
}
