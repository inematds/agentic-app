"""Adaptador de LLM plugável.

- FakeLLM (padrão): determinístico, sem rede. Usado nos testes e na demo.
- OllamaLLM (opcional): só quando AGENTIC_LLM=ollama. Fala com o Ollama local
  (http://localhost:11434). Nenhuma chave, nenhuma API externa.

Todo LLM recebe o NOME DO MODELO escolhido pela tarefa (pilar 2) e devolve texto
ou uma escolha estruturada. Quem valida a saída é o nó de formatação, nunca o LLM.
"""
import inspect
import json
import os
import string
import unicodedata
import urllib.request


def normalizar(txt: str) -> str:
    """minúsculas e sem acento: 'Férias' -> 'ferias'."""
    t = unicodedata.normalize("NFKD", str(txt))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


class _Formatador(string.Formatter):
    """str.format tolerante: campo ausente vira '' em vez de quebrar."""

    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            return kwargs.get(key, "")
        return super().get_value(key, args, kwargs)


def preencher(modelo: str, dados: dict) -> str:
    return _Formatador().format(modelo, **(dados or {}))


class LLM:
    nome = "base"

    def __init__(self):
        self.chamadas = []  # (modo, modelo) — para auditoria e testes

    def _registra(self, modo, modelo):
        self.chamadas.append({"modo": modo, "modelo": modelo})

    # Cada modo devolve tipos simples (str / dict) para o nó de formatação validar.
    def classificar(self, texto, rotulos, dicas, modelo):
        raise NotImplementedError

    def redigir(self, modelo_texto, dados, instrucao, modelo):
        raise NotImplementedError

    def escolher_ferramenta(self, pergunta, ferramentas, modelo):
        raise NotImplementedError


class FakeLLM(LLM):
    """Determinístico: mesma entrada, mesma saída, sempre."""

    nome = "fake"

    def classificar(self, texto, rotulos, dicas, modelo):
        self._registra("classificar", modelo)
        t = normalizar(texto)
        for rotulo in rotulos:
            for palavra in (dicas or {}).get(rotulo, []):
                if normalizar(palavra) in t:
                    return rotulo
        return rotulos[-1]  # último rótulo = "outro"

    def redigir(self, modelo_texto, dados, instrucao, modelo):
        self._registra("redigir", modelo)
        return preencher(modelo_texto, dados).strip()

    def escolher_ferramenta(self, pergunta, ferramentas, modelo):
        """Escolhe a ferramenta cujo nome/descrição mais casa com a pergunta."""
        self._registra("escolher_ferramenta", modelo)
        q = set(normalizar(pergunta).replace("?", " ").split())
        melhor, pontos = None, -1
        for nome, func in ferramentas.items():
            alvo = normalizar(nome.replace("_", " ") + " " + (func.__doc__ or ""))
            p = sum(1 for w in q if len(w) > 3 and w in alvo)
            if p > pontos:
                melhor, pontos = nome, p
        return melhor


class OllamaLLM(LLM):
    """Opcional e local. Se o Ollama não responder, cai no FakeLLM (e registra)."""

    nome = "ollama"
    URL = "http://localhost:11434/api/generate"
    MAPA = {"pequeno": "qwen2.5:7b", "medio": "qwen2.5:14b"}

    def __init__(self):
        super().__init__()
        self.reserva = FakeLLM()

    def _modelo_real(self, modelo):
        return os.environ.get("AGENTIC_OLLAMA_MODELO") or self.MAPA.get(modelo, modelo)

    def _gerar(self, prompt, modelo):
        corpo = json.dumps({"model": self._modelo_real(modelo), "prompt": prompt,
                            "stream": False, "options": {"temperature": 0}}).encode()
        req = urllib.request.Request(self.URL, data=corpo,
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["response"].strip()

    def classificar(self, texto, rotulos, dicas, modelo):
        self._registra("classificar", modelo)
        try:
            r = normalizar(self._gerar(
                f"Classifique a pergunta em UM destes rótulos: {', '.join(rotulos)}.\n"
                f"Responda só o rótulo.\nPergunta: {texto}", modelo))
            for rot in rotulos:
                if rot in r:
                    return rot
        except Exception:
            pass
        return self.reserva.classificar(texto, rotulos, dicas, modelo)

    def redigir(self, modelo_texto, dados, instrucao, modelo):
        self._registra("redigir", modelo)
        base = preencher(modelo_texto, dados)
        try:
            return self._gerar(f"{instrucao}\nReescreva em português claro, mantendo os fatos:\n{base}", modelo)
        except Exception:
            return base.strip()

    def escolher_ferramenta(self, pergunta, ferramentas, modelo):
        self._registra("escolher_ferramenta", modelo)
        try:
            lista = "\n".join(f"- {n}: {(f.__doc__ or '').strip()}" for n, f in ferramentas.items())
            r = self._gerar(f"Ferramentas:\n{lista}\nQual ferramenta responde: {pergunta}\n"
                            "Responda só o nome.", modelo)
            for n in ferramentas:
                if n in r:
                    return n
        except Exception:
            pass
        return self.reserva.escolher_ferramenta(pergunta, ferramentas, modelo)


def get_llm() -> LLM:
    """FakeLLM por padrão. OllamaLLM só com AGENTIC_LLM=ollama."""
    if os.environ.get("AGENTIC_LLM", "fake").lower() == "ollama":
        return OllamaLLM()
    return FakeLLM()


def argumentos_de(func, contexto: dict) -> dict:
    """Preenche os parâmetros da ferramenta a partir do contexto (nome = chave)."""
    args = {}
    for nome, p in inspect.signature(func).parameters.items():
        if nome in contexto:
            args[nome] = contexto[nome]
        elif p.default is inspect.Parameter.empty:
            raise KeyError(f"contexto não tem '{nome}' exigido por {func.__name__}")
    return args
