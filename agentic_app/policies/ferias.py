"""Pilar 6 — política vira código testado (não RAG).

Codificação do "Manual de Pessoas da Empresa Exemplo, v3" — FICTÍCIO, só para o
app de referência. Não é aconselhamento jurídico nem reflete lei de nenhum país.

Regras (cada número abaixo tem teste em tests/test_politica_ferias.py):
  F1  Menos de 12 meses de casa: 2,5 dias por mês completo (proporcional, arredonda p/ baixo).
  F2  12 a 59 meses: 30 dias por ano.
  F3  60 a 119 meses: 30 + 2 dias de bônus de tempo de casa.
  F4  120 meses ou mais: 30 + 5 dias de bônus.
  F5  Pedido com pelo menos 30 dias de antecedência.
  F6  Fracionar em até 3 períodos; um deles com pelo menos 14 dias; nenhum com menos de 5.
  P1  Licença parental — pessoa gestante: 180 dias.
  P2  Licença parental — parceira(o) da pessoa gestante: 20 dias.
  P3  Adoção — adotante principal: 180 dias; segundo adotante: 20 dias.
  P4  Toda licença parental é remunerada e não desconta das férias.

Entradas ESTRITAS: tipo errado ou valor fora da faixa levanta erro, nunca "chuta".
"""

VERSAO_POLITICA = "manual-pessoas-v3"

DIAS_POR_MES_PROPORCIONAL = 2.5
DIAS_BASE = 30
BONUS_5_ANOS = 2
BONUS_10_ANOS = 5
ANTECEDENCIA_MINIMA_DIAS = 30
MAX_PERIODOS = 3
MIN_PERIODO_PRINCIPAL = 14
MIN_PERIODO = 5

LICENCA_PARENTAL = {
    "gestante": 180,
    "parceiro_gestante": 20,
    "adotante_principal": 180,
    "adotante_secundario": 20,
}


def _inteiro(nome, valor, minimo=0, maximo=None):
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nome} precisa ser inteiro, veio {type(valor).__name__}")
    if valor < minimo:
        raise ValueError(f"{nome} não pode ser menor que {minimo}")
    if maximo is not None and valor > maximo:
        raise ValueError(f"{nome} não pode passar de {maximo}")
    return valor


def dias_de_ferias(meses_de_casa: int) -> dict:
    """Quantos dias de férias por ano a pessoa tem pelo tempo de casa (regras F1–F4)."""
    _inteiro("meses_de_casa", meses_de_casa, 0, 600)
    if meses_de_casa < 12:
        dias, regra = int(meses_de_casa * DIAS_POR_MES_PROPORCIONAL), "F1"
    elif meses_de_casa < 60:
        dias, regra = DIAS_BASE, "F2"
    elif meses_de_casa < 120:
        dias, regra = DIAS_BASE + BONUS_5_ANOS, "F3"
    else:
        dias, regra = DIAS_BASE + BONUS_10_ANOS, "F4"
    return {"dias": dias, "regra": regra, "politica": VERSAO_POLITICA}


def validar_pedido_ferias(periodos: list, dias_de_antecedencia: int) -> dict:
    """Confere se um pedido de férias (dividir/fracionar em períodos) segue a antecedência F5 e a regra F6."""
    if not isinstance(periodos, list) or not periodos:
        raise TypeError("periodos precisa ser uma lista não vazia de inteiros")
    for p in periodos:
        _inteiro("periodo", p, 1, 60)
    _inteiro("dias_de_antecedencia", dias_de_antecedencia, 0, 365)
    motivos = []
    if dias_de_antecedencia < ANTECEDENCIA_MINIMA_DIAS:
        motivos.append(f"F5: pedir com {ANTECEDENCIA_MINIMA_DIAS} dias de antecedência")
    if len(periodos) > MAX_PERIODOS:
        motivos.append(f"F6: no máximo {MAX_PERIODOS} períodos")
    if max(periodos) < MIN_PERIODO_PRINCIPAL:
        motivos.append(f"F6: um período precisa ter {MIN_PERIODO_PRINCIPAL} dias ou mais")
    if min(periodos) < MIN_PERIODO:
        motivos.append(f"F6: nenhum período pode ter menos de {MIN_PERIODO} dias")
    return {"aprovado": not motivos, "motivos": motivos, "politica": VERSAO_POLITICA}


def licenca_parental(papel_parental: str) -> dict:
    """Dias de licença parental (maternidade, paternidade, adoção) pelo papel da pessoa (P1–P4)."""
    if not isinstance(papel_parental, str):
        raise TypeError("papel_parental precisa ser texto")
    if papel_parental not in LICENCA_PARENTAL:
        raise ValueError(f"papel_parental inválido: {papel_parental!r}; use {sorted(LICENCA_PARENTAL)}")
    return {"dias": LICENCA_PARENTAL[papel_parental], "remunerada": True,
            "desconta_ferias": False, "politica": VERSAO_POLITICA}


# Grupos de ferramentas: o workflow libera SÓ o grupo da categoria classificada.
FERRAMENTAS = {
    "ferias": {"dias_de_ferias": dias_de_ferias, "validar_pedido_ferias": validar_pedido_ferias},
    "licenca_parental": {"licenca_parental": licenca_parental},
}
