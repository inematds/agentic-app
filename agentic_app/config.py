"""Configuração: pasta de saída e mapa 'tarefa -> modelo'."""
import json
import os
from pathlib import Path

PACOTE = Path(__file__).resolve().parent

# Pilar 2: o modelo é escolhido pela TAREFA, não por gosto. Uma tabela, um lugar.
MODELOS_PADRAO = {
    "classificacao": "pequeno",   # rótulo curto, barato e rápido
    "redacao": "medio",           # rascunho de texto para humano revisar
    "resumo": "medio",
    "agente": "medio",            # escolhe ferramenta dentro do escopo
}


def pasta_saida() -> Path:
    """Onde ficam audit log, caixa de saída e relatórios. AGENTIC_SAIDA muda o local."""
    p = Path(os.environ.get("AGENTIC_SAIDA", "saida"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def modelos() -> dict:
    """Lê modelos.json (se existir na pasta atual) por cima do padrão."""
    m = dict(MODELOS_PADRAO)
    arq = Path(os.environ.get("AGENTIC_MODELOS", "modelos.json"))
    if arq.exists():
        m.update(json.loads(arq.read_text(encoding="utf-8")))
    return m


def modelo_para(tarefa: str) -> str:
    tab = modelos()
    if tarefa not in tab:
        raise KeyError(f"tarefa sem modelo definido: {tarefa!r} (ajuste modelos.json)")
    return tab[tarefa]
