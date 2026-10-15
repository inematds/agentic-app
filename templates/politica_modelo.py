"""Modelo de política codificada. Copie para agentic_app/policies/<sua_politica>.py.

Regra de ouro: cada número do documento vira uma CONSTANTE com nome, e cada
constante tem pelo menos um teste em tests/test_<sua_politica>.py.

Documento de origem: <nome do documento interno>, versão <x>, aprovado por <área> em <data>.
  R1  <regra 1 com o número>
  R2  <regra 2 com o número>
"""

VERSAO_POLITICA = "minha-politica-v1"

LIMITE_REEMBOLSO = 500      # R1: reembolso de curso até 500 por pedido
PRAZO_DIAS_UTEIS = 5        # R2: resposta em até 5 dias úteis


def _inteiro(nome, valor, minimo=0):
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nome} precisa ser inteiro")
    if valor < minimo:
        raise ValueError(f"{nome} não pode ser menor que {minimo}")
    return valor


def reembolso_aprovado(valor_pedido: int) -> dict:
    """Diz se um pedido de reembolso de curso está dentro do limite (R1)."""
    _inteiro("valor_pedido", valor_pedido, 1)
    return {"aprovado": valor_pedido <= LIMITE_REEMBOLSO, "limite": LIMITE_REEMBOLSO,
            "regra": "R1", "politica": VERSAO_POLITICA}


# Só estas ferramentas são entregues ao agente quando a pergunta cair nesta categoria.
FERRAMENTAS = {"reembolso": {"reembolso_aprovado": reembolso_aprovado}}
