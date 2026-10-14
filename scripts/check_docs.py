#!/usr/bin/env python3
"""Verificações automáticas da documentação do BoardHub.

Uso:
    python3 scripts/check_docs.py          # verifica; código de saída 1 se houver falhas
    python3 scripts/check_docs.py --write  # regenera a matriz de rastreabilidade e verifica

Verifica: arquivos obrigatórios, links internos (arquivo e âncora), blocos de código
fechados, IDs definidos uma única vez, referências a IDs inexistentes, cada RF/RNF
com teste e critério de aceite, e se a matriz no doc 11 está atualizada.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

REQUIRED = [
    "README.md", "AGENTS.md", "CONTRIBUTING.md", "CHANGELOG.md", ".gitignore",
    ".env.example", "docker-compose.yml", "pyproject.toml", "package.json",
    "docs/00-indice-e-governanca.md", "docs/01-visao-do-produto.md",
    "docs/02-requisitos-funcionais.md", "docs/03-requisitos-nao-funcionais.md",
    "docs/04-arquitetura-tecnica.md", "docs/05-modelagem-de-dados.md",
    "docs/06-api-e-tempo-real.md", "docs/07-motores-e-regras-dos-jogos.md",
    "docs/08-ia-e-boardhub-academy.md", "docs/09-seguranca-e-privacidade.md",
    "docs/10-interface-e-acessibilidade.md", "docs/11-testes-e-qualidade.md",
    "docs/12-infraestrutura-e-deploy.md", "docs/13-monitoramento-e-operacao.md",
    "docs/14-plano-de-implementacao.md", "docs/15-criterios-de-aceite.md",
    "docs/16-decisoes-tecnicas.md", "docs/17-riscos-e-mitigacoes.md",
    "docs/18-glossario.md", "docs/adr/ADR-0001-arquitetura-inicial.md",
]
MIN_BYTES_DOC = 1500  # "conteúdo substancial" mínimo para docs/

# Onde cada tipo de ID é DEFINIDO (padrão regex aplicado por linha).
DEFINITIONS = {
    "RF": ("docs/02-requisitos-funcionais.md", r"^### (RF-\d{3})\b"),
    "RNF": ("docs/03-requisitos-nao-funcionais.md", r"^\| (RNF-\d{3}) \|"),
    "CA": ("docs/15-criterios-de-aceite.md", r"^\| (CA-\d{3}) \|"),
    "DT": ("docs/16-decisoes-tecnicas.md", r"^\| (DT-\d{3}) \|"),
    "P": ("docs/16-decisoes-tecnicas.md", r"^\| (P-\d{2}) \|"),
    "R": ("docs/17-riscos-e-mitigacoes.md", r"^\| (R-\d{3}) \|"),
    "SEC": ("docs/09-seguranca-e-privacidade.md", r"^- \*\*(SEC-\d{2}) "),
}
REF_RE = re.compile(r"\b(RF|RNF|CA|DT|SEC|R|P|T)-(\d{2,3})\b")

# Módulo e endpoint/componente responsáveis por cada RF (fonte: docs 04 e 06).
RF_MAP = {
    1: ("services/auth_service", "POST /auth/register"),
    2: ("services/auth_service", "POST /auth/verify-email"),
    3: ("services/auth_service", "POST /auth/login"),
    4: ("services/auth_service", "/auth/logout, /auth/sessions"),
    5: ("services/auth_service", "/auth/password/*"),
    6: ("services/user_service", "PATCH /me/profile; features/profile"),
    7: ("services/user_service", "/me/preferences; features/profile"),
    8: ("frontend features/lobby", "GET /games; features/lobby"),
    9: ("services/match_service", "POST /engines/{game}/apply; POST /matches"),
    10: ("services/match_service + ai/opponents", "POST /matches; WS submit_move"),
    11: ("services/match_service", "POST /matches, /matches/join"),
    12: ("services/matchmaking_service", "/matchmaking/queue"),
    13: ("services/match_service + realtime", "WS submit_move"),
    14: ("realtime", "WS join_match"),
    15: ("services/match_service", "/matches/{id}/resign, draw-*"),
    16: ("game_engines/tictactoe", "features/tictactoe"),
    17: ("game_engines/checkers", "features/checkers"),
    18: ("game_engines/chess", "features/chess"),
    19: ("services/rating_service", "GET /ranking/{game_id}"),
    20: ("services/match_service", "GET /me/matches; /matches/{id}/moves"),
    21: ("services/stats_service", "GET /me/stats"),
    22: ("services/academy_service", "POST /academy/{game}/placement"),
    23: ("services/academy_service", "/academy/exercises/*"),
    24: ("ai/mentor + ai/llm", "GET /matches/{id}/analysis"),
    25: ("services/academy_service", "features/academy"),
    26: ("services/achievement_service", "(fase 6)"),
    27: ("services/academy_service", "(fase 6)"),
    28: ("services/notification_service", "WS eventos"),
    29: ("services/privacy_service", "/me/export"),
    30: ("services/privacy_service", "/me/delete"),
    31: ("services/moderation_service", "/reports, /admin/*"),
    32: ("services/social_service", "(fase 6)"),
    33: ("services/catalog_service", "GET /games; features/lobby"),
    34: ("services/guardian_service", "/guardian/*; features/guardian"),
}
MATRIX_START, MATRIX_END = "<!-- MATRIZ:INICIO -->", "<!-- MATRIZ:FIM -->"

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def slugify(heading: str) -> str:
    """Âncora no estilo GitHub."""
    text = heading.strip().lower()
    text = re.sub(r"[`*_]", "", text)
    out = []
    for ch in text:
        if ch == " " or ch == "-":
            out.append("-")
        elif ch.isalnum() or unicodedata.category(ch).startswith("L"):
            out.append(ch)
    return "".join(out)


def strip_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)


def anchors_of(path: Path) -> set[str]:
    seen: dict[str, int] = {}
    result = set()
    for line in strip_code(path.read_text(encoding="utf-8")).splitlines():
        m = re.match(r"^#{1,6}\s+(.*)", line)
        if m:
            s = slugify(m.group(1))
            n = seen.get(s, 0)
            result.add(s if n == 0 else f"{s}-{n}")
            seen[s] = n + 1
    return result


def md_files() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.md") if ".git" not in p.parts)


def check_required() -> None:
    for rel in REQUIRED:
        p = ROOT / rel
        if not p.exists():
            err(f"arquivo obrigatório ausente: {rel}")
        elif rel.startswith("docs/") and p.stat().st_size < MIN_BYTES_DOC:
            err(f"{rel}: conteúdo insuficiente ({p.stat().st_size} bytes)")


def check_markdown_and_links() -> None:
    for f in md_files():
        text = f.read_text(encoding="utf-8")
        if text.count("```") % 2:
            err(f"{f.relative_to(ROOT)}: bloco de código não fechado")
        for target in re.findall(r"\]\(([^)\s]+)\)", strip_code(text)):
            if re.match(r"^[a-z]+:", target):
                continue  # link externo — não verificado (sem rede)
            path_part, _, anchor = target.partition("#")
            dest = (f.parent / path_part).resolve() if path_part else f
            if not dest.exists():
                err(f"{f.relative_to(ROOT)}: link quebrado -> {target}")
                continue
            if anchor and dest.suffix == ".md" and anchor not in anchors_of(dest):
                err(f"{f.relative_to(ROOT)}: âncora inexistente -> {target}")


def collect_definitions() -> dict[str, set[str]]:
    defined: dict[str, set[str]] = {}
    for kind, (rel, pattern) in DEFINITIONS.items():
        ids: list[str] = []
        for line in (ROOT / rel).read_text(encoding="utf-8").splitlines():
            m = re.match(pattern, line)
            if m:
                ids.append(m.group(1))
        dup = {i for i in ids if ids.count(i) > 1}
        for d in sorted(dup):
            err(f"ID duplicado: {d} em {rel}")
        defined[kind] = set(ids)
    return defined


def rnf_tests() -> dict[str, str]:
    out = {}
    for line in (DOCS / "03-requisitos-nao-funcionais.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (RNF-\d{3}) \|.*\| (T-\d{3}|—) \|$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


PR1 = "[PR #1](https://github.com/edervani/boardhub/pull/1)"
# Estado/evidência por requisito. `implementado` só com código mesclado (doc 00 §4).
IMPLEMENTADOS = {1, 2, 3, 4, 5}
PARCIAIS = {6, 7, 17, 18, 9, 10, 13, 15, 16, 20, 33, 34}  # código mesclado, aceite incompleto (P-15)


def state_evidence(n: int) -> tuple[str, str]:
    if n in IMPLEMENTADOS:
        return "implementado", f"{PR1}; CI verde"
    if n in PARCIAIS:
        return "aprovado", f"parcial em {PR1}; lacunas em P-15"
    return "aprovado", "—"


def build_matrix(defined: dict[str, set[str]]) -> str:
    rows = [
        "| Requisito | Origem | Módulo | Endpoint/componente | Teste | Critério | Estado | Evidência |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for rf in sorted(defined["RF"]):
        n = int(rf[3:])
        mod, ep = RF_MAP.get(n, ("?", "?"))
        state, evid = state_evidence(n)
        rows.append(f"| {rf} | doc 02 | {mod} | {ep} | T-{n:03d} | CA-{n:03d} | {state} | {evid} |")
    tests = rnf_tests()
    for rnf in sorted(defined["RNF"]):
        n = int(rnf[4:])
        t = tests.get(rnf, "?")
        ca = f"CA-{100 + n:03d}"
        rows.append(f"| {rnf} | doc 03 | transversal | — | {t} | {ca} | aprovado | — |")
    return "\n".join(rows)


def check_matrix(defined: dict[str, set[str]], write: bool) -> None:
    path = DOCS / "11-testes-e-qualidade.md"
    text = path.read_text(encoding="utf-8")
    if MATRIX_START not in text or MATRIX_END not in text:
        err("doc 11: marcadores da matriz ausentes")
        return
    expected = build_matrix(defined)
    head, rest = text.split(MATRIX_START, 1)
    current, tail = rest.split(MATRIX_END, 1)
    if write:
        path.write_text(f"{head}{MATRIX_START}\n{expected}\n{MATRIX_END}{tail}", encoding="utf-8")
    elif current.strip() != expected.strip():
        err("doc 11: matriz de rastreabilidade desatualizada (rode com --write)")


def check_references(defined: dict[str, set[str]]) -> None:
    rnf_n = {int(x[4:]) for x in defined["RNF"]}
    # IDs de teste válidos: T-001..T-032 (RF) e os T-1xx listados no doc 03.
    tests = {f"T-{int(x[3:]):03d}" for x in defined["RF"]} | {
        t for t in rnf_tests().values() if t != "—"}
    # CA-1xx são definidos de forma genérica (doc 15 §2) para cada RNF.
    ca_all = defined["CA"] | {f"CA-{100 + n:03d}" for n in rnf_n}
    valid = {
        "RF": defined["RF"], "RNF": defined["RNF"], "CA": ca_all, "DT": defined["DT"],
        "P": defined["P"], "R": defined["R"], "SEC": defined["SEC"], "T": tests,
    }
    for f in md_files():
        for m in REF_RE.finditer(f.read_text(encoding="utf-8")):
            ident = m.group(0)
            if m.group(1) == "T" and ident.startswith("T-") and len(m.group(2)) != 3:
                continue
            if ident not in valid[m.group(1)]:
                err(f"{f.relative_to(ROOT)}: referência a ID inexistente {ident}")
    # Todo RF tem CA e teste correspondentes.
    for rf in defined["RF"]:
        n = int(rf[3:])
        if f"CA-{n:03d}" not in defined["CA"]:
            err(f"{rf} sem critério de aceite CA-{n:03d}")
    for rnf, t in rnf_tests().items():
        if t == "—" and rnf != "RNF-026":
            err(f"{rnf} sem teste associado")
    if set(rnf_tests()) != defined["RNF"]:
        err("doc 03: linhas de RNF sem coluna de teste reconhecível")


def check_compose() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for m in re.finditer(r'"([\d.]*:?\$?\{?[^"]*:\d+)"', text):
        if not m.group(1).startswith("127.0.0.1:"):
            err(f"docker-compose.yml: porta publicada fora de 127.0.0.1 -> {m.group(1)}")
    if re.search(r"(?im)^\s*[\w-]*password[\w-]*:\s*[^$\s]", text):
        err("docker-compose.yml: possível senha literal")


def check_secrets() -> None:
    pat = re.compile(r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,})")
    for p in ROOT.rglob("*"):
        if p.is_file() and ".git" not in p.parts and p.suffix in {".md", ".yml", ".toml", ".json", ".py", ".example", ""}:
            if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
                err(f"possível segredo em {p.relative_to(ROOT)}")


def main() -> int:
    write = "--write" in sys.argv
    check_required()
    if errors:
        print("\n".join(f"FALHA: {e}" for e in errors))
        return 1
    defined = collect_definitions()
    check_matrix(defined, write)
    check_markdown_and_links()
    check_references(defined)
    check_compose()
    check_secrets()
    counts = ", ".join(f"{k}={len(v)}" for k, v in defined.items())
    if errors:
        print("\n".join(f"FALHA: {e}" for e in errors))
        print(f"\n{len(errors)} falha(s). IDs: {counts}")
        return 1
    print(f"OK — {len(md_files())} arquivos Markdown verificados. IDs: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
