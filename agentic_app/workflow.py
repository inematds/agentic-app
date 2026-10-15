"""Pilar 2 — motor de workflow determinístico.

Um workflow é um JSON com uma lista de NÓS. O LLM é só um tipo de nó entre cinco:

  contexto   carrega dados sempre do mesmo jeito (função registrada + escopo da identidade)
  codigo     regra de negócio em Python puro (filtrar, calcular, chamar política)
  condicao   desvia o fluxo ({"campo": "$x.y", "op": ">", "valor": 0} -> entao/senao)
  llm        classificar | redigir | agente — modelo escolhido pela TAREFA
  formatacao monta o JSON da UI, valida contra esquema e PROPÕE ação (nunca executa)

Referências: "$entrada.campo", "$no_id.campo.sub". O resto é literal.
"""
import hashlib
import json
from pathlib import Path

from . import config
from .esquema import validar
from .llm import argumentos_de, get_llm
from .seguranca import Identidade, PermissaoNegada

TIPOS_DE_NO = ("contexto", "codigo", "condicao", "llm", "formatacao")
FIM = "$fim"


class ErroWorkflow(RuntimeError):
    pass


class Registro:
    """O que os workflows podem usar. Tudo explícito: nada é chamado por nome solto."""

    def __init__(self):
        self.contextos = {}     # nome -> (escopo, func(entrada) -> dict)
        self.funcoes = {}       # nome -> func(**args)
        self.ferramentas = {}   # grupo -> {nome: func}  (ex.: política de férias)
        self.artefatos = {}     # tipo -> func(dados, pasta) -> caminho
        self.identidades = {}   # id -> Identidade

    def contexto(self, nome, escopo):
        def deco(f):
            self.contextos[nome] = (escopo, f)
            return f
        return deco

    def funcao(self, nome):
        def deco(f):
            self.funcoes[nome] = f
            return f
        return deco


def resolver(valor, estado):
    if isinstance(valor, str) and valor.startswith("$") and valor != FIM:
        partes = valor[1:].split(".")
        atual = estado
        for p in partes:
            if isinstance(atual, dict) and p in atual:
                atual = atual[p]
            elif isinstance(atual, list) and p.isdigit():
                atual = atual[int(p)]
            else:
                raise ErroWorkflow(f"referência inválida: {valor}")
        return atual
    if isinstance(valor, dict):
        return {k: resolver(v, estado) for k, v in valor.items()}
    if isinstance(valor, list):
        return [resolver(v, estado) for v in valor]
    return valor


OPS = {
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    "em": lambda a, b: a in b,
}


def carregar_spec(origem) -> dict:
    spec = origem if isinstance(origem, dict) else json.loads(Path(origem).read_text(encoding="utf-8"))
    for campo in ("id", "versao", "nos", "seguranca"):
        if campo not in spec:
            raise ErroWorkflow(f"spec sem '{campo}'")
    ids = set()
    for no in spec["nos"]:
        if no.get("tipo") not in TIPOS_DE_NO:
            raise ErroWorkflow(f"nó '{no.get('id')}' com tipo inválido: {no.get('tipo')}")
        if no["id"] in ids:
            raise ErroWorkflow(f"id de nó repetido: {no['id']}")
        ids.add(no["id"])
    for no in spec["nos"]:
        alvos = [no.get("entao"), no.get("senao")] if no["tipo"] == "condicao" else []
        if "proximo" in no:
            alvos.append(no["proximo"])
        for alvo in alvos:
            if alvo not in ids and alvo != FIM:
                raise ErroWorkflow(f"nó '{no['id']}' aponta para nó inexistente: {alvo}")
    return spec


class Motor:
    def __init__(self, registro: Registro, audit, fila=None, llm=None):
        self.registro = registro
        self.audit = audit
        self.fila = fila
        self.llm = llm or get_llm()
        self.workflows = {}
        self._execucoes = 0

    def adicionar(self, origem) -> dict:
        spec = carregar_spec(origem)
        self.workflows[spec["id"]] = spec
        return spec

    # ------------------------------------------------------------------ execução
    def executar(self, workflow_id, entrada, usuario, gatilho="manual") -> dict:
        spec = self.workflows[workflow_id]
        seg = spec["seguranca"]
        self._execucoes += 1
        run_id = f"{workflow_id}-{self._execucoes:04d}"
        hash_entrada = hashlib.sha256(json.dumps(entrada, sort_keys=True, ensure_ascii=False)
                                      .encode()).hexdigest()[:12]
        base = dict(run_id=run_id, workflow=workflow_id, versao=spec["versao"], usuario=usuario.id,
                    papeis=list(usuario.papeis), identidade=seg["identidade"], gatilho=gatilho,
                    hash_entrada=hash_entrada)

        if not usuario.tem_algum(seg["executar"]):
            self.audit.registrar("workflow.negado", **base, motivo="papel sem permissão de executar")
            raise PermissaoNegada(f"{usuario.id} ({', '.join(usuario.papeis)}) não executa {workflow_id}")

        identidade = self.registro.identidades.get(seg["identidade"])
        if identidade is None:
            raise ErroWorkflow(f"identidade não registrada: {seg['identidade']}")

        n_chamadas = len(self.llm.chamadas)
        estado = {"entrada": entrada, "usuario": {"id": usuario.id, "nome": usuario.nome, "papeis": list(usuario.papeis)}}
        trilha, propostas = [], []
        try:
            if "entrada" in spec:
                validar(entrada, spec["entrada"], "$entrada")
            indice = {no["id"]: i for i, no in enumerate(spec["nos"])}
            i = 0
            while i < len(spec["nos"]):
                no = spec["nos"][i]
                passo = {"no": no["id"], "tipo": no["tipo"]}
                proximo = i + 1
                if no["tipo"] == "contexto":
                    escopo, func = self.registro.contextos[no["carregar"]]
                    identidade.exige(escopo)
                    estado[no["id"]] = func(resolver(no.get("args", {}), estado))
                elif no["tipo"] == "codigo":
                    func = self.registro.funcoes[no["funcao"]]
                    estado[no["id"]] = func(**resolver(no.get("args", {}), estado))
                elif no["tipo"] == "condicao":
                    c = no["se"]
                    ok = OPS[c["op"]](resolver(c["campo"], estado), resolver(c["valor"], estado))
                    alvo = no["entao"] if ok else no["senao"]
                    passo["resultado"] = ok
                    estado[no["id"]] = ok
                    proximo = len(spec["nos"]) if alvo == FIM else indice[alvo]
                elif no["tipo"] == "llm":
                    estado[no["id"]], passo["modelo"] = self._no_llm(no, estado, identidade)
                elif no["tipo"] == "formatacao":
                    estado[no["id"]] = self._no_formatacao(no, estado, run_id, workflow_id,
                                                           usuario, propostas)
                    estado["_saida"] = estado[no["id"]]
                if no["tipo"] != "condicao" and "proximo" in no:
                    proximo = len(spec["nos"]) if no["proximo"] == FIM else indice[no["proximo"]]
                trilha.append(passo)
                i = proximo
            status = "ok"
            erro = None
        except PermissaoNegada as e:
            status, erro = "negado", str(e)
        except Exception as e:  # noqa: BLE001 — erro vira linha de auditoria, depois sobe
            status, erro = "erro", f"{type(e).__name__}: {e}"

        chamadas = self.llm.chamadas[n_chamadas:]
        por_modelo = {}
        for c in chamadas:
            por_modelo[c["modelo"]] = por_modelo.get(c["modelo"], 0) + 1
        self.audit.registrar("workflow.executado", **base, status=status, erro=erro,
                             nos=[p["no"] for p in trilha], propostas=[p["id"] for p in propostas],
                             modelos=[p["modelo"] for p in trilha if "modelo" in p],
                             llm={"chamadas": por_modelo,
                                  "tokens_estimados": sum(c.get("tokens_estimados", 0) for c in chamadas)})
        if status == "negado":
            raise PermissaoNegada(erro)
        if status == "erro":
            raise ErroWorkflow(f"{run_id}: {erro}")
        return {"run_id": run_id, "workflow": workflow_id, "status": status,
                "identidade": identidade.id, "trilha": trilha,
                "saida": estado.get("_saida"), "propostas": propostas}

    # ------------------------------------------------------------------ nós
    def _no_llm(self, no, estado, identidade):
        modelo = config.modelo_para(no["tarefa"])
        modo = no["modo"]
        if modo == "classificar":
            texto = resolver(no["texto"], estado)
            return self.llm.classificar(texto, no["rotulos"], no.get("dicas", {}), modelo), modelo
        if modo == "redigir":
            itens = resolver(no["para_cada"], estado) if "para_cada" in no else None
            if itens is None:
                dados = resolver(no.get("dados", {}), estado)
                return self.llm.redigir(no["modelo_texto"], dados, no.get("instrucao", ""), modelo), modelo
            return [{**item, no.get("campo", "texto"):
                     self.llm.redigir(no["modelo_texto"], {**resolver(no.get("dados", {}), estado), **item},
                                      no.get("instrucao", ""), modelo)} for item in itens], modelo
        if modo == "agente":
            # Escopo mínimo: o agente só enxerga as ferramentas que o workflow liberou.
            grupo = resolver(no["ferramentas"], estado)
            ferramentas = self.registro.ferramentas.get(grupo, {})
            if not ferramentas:
                raise ErroWorkflow(f"grupo de ferramentas vazio ou desconhecido: {grupo!r}")
            pergunta = resolver(no["pergunta"], estado)
            escolha = self.llm.escolher_ferramenta(pergunta, ferramentas, modelo)
            if escolha not in ferramentas:
                raise PermissaoNegada(f"ferramenta fora do escopo do nó '{no['id']}': {escolha}")
            ctx = resolver(no.get("contexto", {}), estado)
            func = ferramentas[escolha]
            args = argumentos_de(func, ctx)
            return {"ferramenta": escolha, "grupo": grupo, "argumentos": args,
                    "resultado": func(**args), "ofertadas": sorted(ferramentas)}, modelo
        raise ErroWorkflow(f"modo de LLM desconhecido: {modo}")

    def _no_formatacao(self, no, estado, run_id, workflow_id, usuario, propostas):
        saida = resolver(no["saida"], estado)
        validar(saida, no["esquema"], f"${no['id']}")
        acao = no.get("propor_acao")
        if acao and "se" in acao:
            try:
                if not resolver(acao["se"], estado):
                    acao = None
            except ErroWorkflow:
                acao = None
        if acao:
            if self.fila is None:
                raise ErroWorkflow("workflow propõe ação mas o motor não tem fila de aprovação")
            local = {**estado, no["id"]: saida}
            itens = resolver(acao["para_cada"], local) if "para_cada" in acao else [saida]
            for item in itens:
                payload = {k: resolver(v, {**local, "item": item}) for k, v in acao["payload"].items()}
                p = self.fila.propor(acao["tipo"], payload, acao.get("editaveis", []),
                                     run_id, workflow_id, usuario.id)
                propostas.append(p)
        art = no.get("artefato")
        if art:
            gerar = self.registro.artefatos[art["tipo"]]
            saida = {**saida, "artefatos": gerar(saida, config.pasta_saida(), art)}
        return saida


def nova_identidade(id_, escopos):
    return Identidade(id_, tuple(escopos))
