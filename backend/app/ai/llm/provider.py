"""Interface da IA generativa opcional (doc 04 §10, doc 08 §8).

Nada aqui chama rede. O produto inteiro funciona com `NullProvider` (RNF-025); um provedor real
(Ollama, desligado por padrão) é pendência da Fase 5 e precisará passar por `accept_rewrite`.
A IA generativa só muda a *forma* de um texto que o Mentor já produziu: ela recebe fatos
estruturados (lances e casas), nunca dados da pessoa, e sua saída é descartada se citar um
lance ou casa que não esteja nos fatos.
"""

import re
from dataclasses import dataclass
from typing import Literal, Protocol

Style = Literal["simple", "technical"]
MAX_WORDS = 80

# Qualquer coisa que se pareça com lance ou casa: linha/coluna, PDN (22x15) ou notação
# algébrica (e4, Cf3).
_CITED = (
    r"linha \d, coluna \d"
    r"|\b\d{1,2}(?:[-x]\d{1,2})+\b"
    r"|\b(?:O-O-O|O-O)\b"
    r"|\b[RDTBC]?[a-h]?[1-8]?x?[a-h][1-8](?:=[DTBC])?[+#]?(?![a-z0-9])"
)
_CITED_RE = re.compile(_CITED)
_MARKUP_RE = re.compile(r"[<>&`]")


@dataclass(frozen=True)
class Facts:
    """Fatos estruturados entregues à IA generativa. Nunca contém dados pessoais."""

    text: str  # o texto determinístico do Mentor, que é a verdade
    cited: frozenset[str]  # lances e casas que o texto cita, exatamente como aparecem


class LLMProvider(Protocol):
    def rephrase(self, facts: Facts, style: Style) -> str | None:
        """Reformula `facts.text` sem acrescentar fatos; `None` se não puder."""
        ...


class NullProvider:
    """Padrão: não reformula nada, e o texto determinístico é usado."""

    def rephrase(self, facts: Facts, style: Style) -> str | None:
        return None


def get_provider() -> LLMProvider:
    return NullProvider()


def cited_in(text: str) -> set[str]:
    return {m.group(0) for m in _CITED_RE.finditer(text)}


def accept_rewrite(facts: Facts, rewritten: str | None) -> str | None:
    """Devolve o texto reformulado só se ele for seguro; senão `None` (e usa-se o modelo).

    Regras (doc 08 §8): sem marcação, até 80 palavras, cita todos os lances/casas dos fatos e
    nenhum lance/casa que não esteja neles.
    """
    if rewritten is None:
        return None
    text = rewritten.strip()
    if not text or _MARKUP_RE.search(text) or len(text.split()) > MAX_WORDS:
        return None
    cited = cited_in(text)
    if not facts.cited <= cited:
        return None
    allowed = set(facts.cited) | {sq for c in facts.cited for sq in cited_in_squares(c)}
    if cited - allowed:
        return None
    return text


_SQUARE_RE = re.compile(r"[a-h][1-8]")


def cited_in_squares(token: str) -> set[str]:
    """Casas contidas num token de lance (ex.: «Cxe5» contém e5), permitidas isoladamente."""
    return set(_SQUARE_RE.findall(token))
