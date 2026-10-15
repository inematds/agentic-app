"""Pilar 7 — segurança por workflow.

- Quem pode executar: papéis declarados no próprio workflow (`seguranca.executar`).
- Com qual identidade o workflow age: `seguranca.identidade` (conta de serviço com escopos).
- Audit log: uma linha JSON por evento, encadeada por hash (adulterar uma linha quebra a corrente).
"""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


class PermissaoNegada(PermissionError):
    pass


@dataclass(frozen=True)
class Usuario:
    id: str
    nome: str
    papeis: tuple = field(default_factory=tuple)

    def tem_algum(self, papeis) -> bool:
        return bool(set(self.papeis) & set(papeis))


@dataclass(frozen=True)
class Identidade:
    """Conta de serviço com a qual o workflow age. Escopo mínimo."""
    id: str
    escopos: tuple = field(default_factory=tuple)

    def exige(self, escopo: str):
        if escopo not in self.escopos:
            raise PermissaoNegada(f"identidade '{self.id}' não tem o escopo '{escopo}'")


def relogio_real() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AuditLog:
    """JSONL só de acréscimo, com hash encadeado."""

    def __init__(self, arquivo, relogio=relogio_real):
        self.arquivo = Path(arquivo)
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.relogio = relogio

    def _ultimo_hash(self) -> str:
        if not self.arquivo.exists():
            return "0" * 16
        linhas = self.arquivo.read_text(encoding="utf-8").strip().splitlines()
        return json.loads(linhas[-1])["hash"] if linhas else "0" * 16

    def registrar(self, evento: str, **dados) -> dict:
        linha = {"ts": self.relogio(), "evento": evento, **dados, "hash_anterior": self._ultimo_hash()}
        bruto = json.dumps(linha, ensure_ascii=False, sort_keys=True)
        linha["hash"] = hashlib.sha256(bruto.encode()).hexdigest()[:16]
        with self.arquivo.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False, sort_keys=True) + "\n")
        return linha

    def ler(self) -> list:
        if not self.arquivo.exists():
            return []
        return [json.loads(l) for l in self.arquivo.read_text(encoding="utf-8").splitlines() if l.strip()]

    def verificar_corrente(self) -> bool:
        anterior = "0" * 16
        for linha in self.ler():
            h = linha.pop("hash")
            if linha["hash_anterior"] != anterior:
                return False
            bruto = json.dumps(linha, ensure_ascii=False, sort_keys=True)
            if hashlib.sha256(bruto.encode()).hexdigest()[:16] != h:
                return False
            anterior = h
        return True
