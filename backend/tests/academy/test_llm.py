"""RF-024 / CA-024: a IA generativa só reformula; saída com fato novo é descartada (doc 08 §8)."""

from app.ai.llm.provider import Facts, NullProvider, accept_rewrite, cited_in, get_provider

TEXT = ("No lance 7, você jogou Dh5. Depois dele, o adversário podia capturar o cavalo em e5 "
        "com Cxe5. Uma opção melhor era Cf3, que mantinha a posição sem entregar material.")
FACTS = Facts(TEXT, frozenset(cited_in(TEXT)))


def test_provedor_padrao_e_nulo_e_nao_reformula() -> None:
    provider = get_provider()
    assert isinstance(provider, NullProvider)
    assert provider.rephrase(FACTS, "simple") is None
    assert accept_rewrite(FACTS, provider.rephrase(FACTS, "technical")) is None


def test_fatos_extraidos_do_texto() -> None:
    assert FACTS.cited == {"Dh5", "e5", "Cxe5", "Cf3"}


def test_reformulacao_fiel_e_aceita() -> None:
    ok = ("Você jogou Dh5 no lance 7 e isso deixou o cavalo em e5 exposto: Cxe5 o capturava. "
          "Cf3 era uma saída mais segura.")
    assert accept_rewrite(FACTS, ok) == ok


def test_lance_inventado_e_descartado() -> None:
    bad = "Você jogou Dh5, mas Cf3 e Cxe5 existiam. Também havia Bb5, uma ideia melhor."
    assert accept_rewrite(FACTS, bad) is None


def test_casa_inventada_e_descartada() -> None:
    invented = "Dh5 foi ruim: Cxe5 e Cf3 mostram, e a casa h7 ficou fraca."
    assert accept_rewrite(FACTS, invented) is None


def test_lance_omitido_e_descartado() -> None:
    assert accept_rewrite(FACTS, "Dh5 foi um erro, pois Cxe5 capturava o cavalo.") is None


def test_marcacao_html_e_descartada() -> None:
    html = "<b>Dh5</b> foi ruim; Cxe5 capturava em e5 e Cf3 era melhor."
    assert accept_rewrite(FACTS, html) is None
    assert accept_rewrite(FACTS, "Dh5, Cxe5, e5 e Cf3 &amp; mais.") is None


def test_texto_longo_demais_e_descartado() -> None:
    long = "Dh5 Cxe5 e5 Cf3 " + "palavra " * 80
    assert accept_rewrite(FACTS, long) is None


def test_vazio_ou_nulo_e_descartado() -> None:
    assert accept_rewrite(FACTS, None) is None
    assert accept_rewrite(FACTS, "   ") is None


def test_velha_e_damas_tambem_sao_verificadas() -> None:
    ttt = Facts("Você jogou linha 3, coluna 1. Era melhor linha 1, coluna 3.",
                frozenset({"linha 3, coluna 1", "linha 1, coluna 3"}))
    assert accept_rewrite(ttt, "Em linha 3, coluna 1 foi um erro; linha 1, coluna 3 servia.")
    invented = "Em linha 3, coluna 1 foi um erro; linha 2, coluna 2 servia."
    assert accept_rewrite(ttt, invented) is None
    ck = Facts("Você jogou 22-18; 17-13 era melhor.", frozenset({"22-18", "17-13"}))
    assert accept_rewrite(ck, "22-18 entregou uma peça e 17-13 não.") is not None
    assert accept_rewrite(ck, "22-18 entregou uma peça e 21-17 não.") is None
