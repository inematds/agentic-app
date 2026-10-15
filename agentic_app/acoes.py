"""Pilar 4 — humano no comando.

Workflow nunca executa ação externa. Ele PROPÕE. A proposta fica na fila até
alguém com o papel certo revisar, editar (se quiser) e aprovar. Só então o
executor roda — e tudo vai para o audit log.
"""
import json
from pathlib import Path

from .seguranca import PermissaoNegada


class FilaAprovacao:
    def __init__(self, arquivo, audit, executores: dict, papeis_aprovadores: dict):
        self.arquivo = Path(arquivo)
        self.audit = audit
        self.executores = executores              # tipo -> função(payload) -> dict
        self.papeis_aprovadores = papeis_aprovadores  # tipo -> [papéis]
        self.itens = self._carregar()

    def _carregar(self):
        if self.arquivo.exists():
            return json.loads(self.arquivo.read_text(encoding="utf-8"))
        return []

    def _salvar(self):
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps(self.itens, ensure_ascii=False, indent=2), encoding="utf-8")

    def propor(self, tipo, payload, campos_editaveis, run_id, workflow, solicitante) -> dict:
        if tipo not in self.executores:
            raise ValueError(f"ação sem executor registrado: {tipo}")
        item = {
            "id": f"acao-{len(self.itens) + 1:04d}", "tipo": tipo, "status": "aguardando_aprovacao",
            "payload": payload, "editaveis": list(campos_editaveis), "run_id": run_id,
            "workflow": workflow, "solicitante": solicitante,
        }
        self.itens.append(item)
        self._salvar()
        return item

    def pendentes(self):
        return [i for i in self.itens if i["status"] == "aguardando_aprovacao"]

    def obter(self, acao_id):
        for i in self.itens:
            if i["id"] == acao_id:
                return i
        raise KeyError(acao_id)

    def _checar(self, item, usuario):
        papeis = self.papeis_aprovadores.get(item["tipo"], [])
        if not usuario.tem_algum(papeis):
            self.audit.registrar("acao.negada", acao=item["id"], usuario=usuario.id,
                                 papeis=list(usuario.papeis), motivo="papel sem permissão de aprovar")
            raise PermissaoNegada(f"{usuario.id} não pode aprovar '{item['tipo']}'")
        if item["status"] != "aguardando_aprovacao":
            raise ValueError(f"{item['id']} já está '{item['status']}'")

    def aprovar(self, acao_id, usuario, edicoes=None) -> dict:
        item = self.obter(acao_id)
        self._checar(item, usuario)
        edicoes = edicoes or {}
        proibidas = set(edicoes) - set(item["editaveis"])
        if proibidas:
            raise ValueError(f"campos não editáveis: {sorted(proibidas)}")
        final = {**item["payload"], **edicoes}
        resultado = self.executores[item["tipo"]](final)
        item.update(status="executada", payload_final=final, aprovado_por=usuario.id,
                    editado=bool(edicoes), resultado=resultado)
        self._salvar()
        self.audit.registrar("acao.executada", acao=item["id"], tipo=item["tipo"], run_id=item["run_id"],
                             aprovado_por=usuario.id, editado=bool(edicoes), resultado=resultado)
        return item

    def rejeitar(self, acao_id, usuario, motivo="") -> dict:
        item = self.obter(acao_id)
        self._checar(item, usuario)
        item.update(status="rejeitada", rejeitado_por=usuario.id, motivo=motivo)
        self._salvar()
        self.audit.registrar("acao.rejeitada", acao=item["id"], tipo=item["tipo"],
                             rejeitado_por=usuario.id, motivo=motivo)
        return item


class CaixaSaida:
    """Executor de e-mail SIMULADO: grava em JSONL. Troque por SMTP na sua empresa."""

    def __init__(self, arquivo):
        self.arquivo = Path(arquivo)

    def enviar_email(self, payload: dict) -> dict:
        for campo in ("para", "assunto", "corpo"):
            if not payload.get(campo):
                raise ValueError(f"e-mail sem '{campo}'")
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        with self.arquivo.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return {"enviado": True, "para": payload["para"]}

    def enviados(self):
        if not self.arquivo.exists():
            return []
        return [json.loads(l) for l in self.arquivo.read_text(encoding="utf-8").splitlines() if l]
