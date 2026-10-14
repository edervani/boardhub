#!/usr/bin/env bash
# Executa um passo do CI. Em caso de falha, publica as últimas 80 linhas da saída como
# anotação de erro (legível pela API do GitHub mesmo sem acesso ao log completo).
# Uso: scripts/ci/run.sh "<rótulo>" <comando...>
set -uo pipefail
label="$1"; shift
out="$(mktemp)"
"$@" >"$out" 2>&1
code=$?
cat "$out"
if [ "$code" -ne 0 ]; then
  msg="$(tail -n 80 "$out" | tr -d '\r' | sed 's/%/%25/g' | awk '{printf "%s%%0A", $0}')"
  echo "::error title=${label}::${msg}"
fi
rm -f "$out"
exit "$code"
