"""agentic-app — framework de apps construídas em torno de um resultado de negócio.

Agentes são ferramentas dentro de workflows determinísticos, não o centro de tudo.
Só biblioteca padrão do Python 3. Nenhuma chamada de API externa.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_VERSAO = RAIZ / "VERSION"
__version__ = _VERSAO.read_text().strip() if _VERSAO.exists() else "1.0.0"
