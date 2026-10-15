"""App de referência: Coaching de gestor.

Resultado de negócio (canvas preenchido em templates/canvas-resultado.md):
  usuária   = Ana, gestora com 12 liderados
  decisão   = com quem falar esta semana e o que dizer
  métrica   = % de metas de desenvolvimento vencidas que tiveram conversa em até 7 dias

Componentes do painel -> workflows:
  painel_engajamento   (leitura direta dos dados, sem LLM)
  botao_followup       -> followup_metas      (rascunhos editáveis + aprovação)
  painel_sugestoes     -> proximos_passos     (agente de fundo, toda segunda 08:00)
  caixa_pergunta_rh    -> assistente_rh       (política codificada, escopo mínimo)
  botao_relatorio      -> relatorio_equipe    (HTML + PDF)
"""
import json
import re
from datetime import date
from pathlib import Path

from ... import config, executivo
from ...acoes import CaixaSaida, FilaAprovacao
from ...gatilhos import Gatilhos
from ...llm import normalizar
from ...policies import grupos_de_ferramentas
from ...relatorio import gerar_artefatos, gerar_executivo
from ...seguranca import AuditLog, Identidade, PermissaoNegada, Usuario
from ...workflow import Motor, Registro

AQUI = Path(__file__).resolve().parent
DADOS = AQUI / "data"
WORKFLOWS = AQUI / "workflows"


def _ler(nome):
    return json.loads((DADOS / nome).read_text(encoding="utf-8"))


def _data(s):
    return date.fromisoformat(s)


def meses_entre(inicio: date, fim: date) -> int:
    m = (fim.year - inicio.year) * 12 + (fim.month - inicio.month)
    return m - 1 if fim.day < inicio.day else m


def _br(d):
    return _data(d).strftime("%d/%m/%Y")


# ---------------------------------------------------------------- funções puras
def resumo_pessoa(p: dict, hoje: date) -> dict:
    atrasadas = [m for m in p["metas"] if _data(m["prazo"]) < hoje and m["progresso"] < 100]
    prog = round(sum(m["progresso"] for m in p["metas"]) / len(p["metas"]))
    dias_1a1 = (hoje - _data(p["ultimo_1a1"])).days
    tend = p["engajamento"][-1] - p["engajamento"][0]
    if atrasadas:
        status = "atrasado"
    elif dias_1a1 > 30 or tend <= -10:
        status = "atencao"
    else:
        status = "em_dia"
    return {"id": p["id"], "nome": p["nome"], "primeiro_nome": p["nome"].split()[0], "email": p["email"],
            "cargo": p["cargo"], "progresso_medio": prog, "engajamento": p["engajamento"][-1],
            "tendencia": tend, "atrasadas": len(atrasadas), "dias_sem_1a1": dias_1a1, "status": status,
            "metas": p["metas"]}


def metas_atrasadas(equipe: dict, filtro: dict) -> dict:
    hoje = _data(equipe["data_referencia"])
    ids = set(filtro.get("liderado_ids") or [])
    itens = []
    for p in equipe["liderados"]:
        if ids and p["id"] not in ids:
            continue
        vencidas = sorted((m for m in p["metas"] if _data(m["prazo"]) < hoje and m["progresso"] < 100),
                          key=lambda m: m["prazo"])
        if vencidas:
            m = vencidas[0]
            itens.append({"id": p["id"], "nome": p["nome"], "primeiro_nome": p["nome"].split()[0],
                          "email": p["email"], "meta": m["titulo"], "progresso": m["progresso"],
                          "prazo_br": _br(m["prazo"]), "assunto": f"Sua meta \"{m['titulo']}\""})
    return {"qtd": len(itens), "itens": itens}


def detectar_sinais(equipe: dict) -> dict:
    """O que o agente de fundo observa. Regras simples e explícitas, não 'intuição' do LLM."""
    hoje = _data(equipe["data_referencia"])
    itens = []
    for p in equipe["liderados"]:
        r = resumo_pessoa(p, hoje)
        if r["atrasadas"]:
            itens.append({"id": f"s-{p['id']}-meta", "primeiro_nome": r["primeiro_nome"], "verbo": "Retomar a meta",
                          "motivo": f"{r['atrasadas']} meta(s) vencida(s) sem concluir", "prioridade": 1,
                          "workflow": "followup_metas", "entrada": {"liderado_ids": [p["id"]]}})
        motivos = []
        if r["dias_sem_1a1"] > 30:
            motivos.append(f"{r['dias_sem_1a1']} dias sem conversa individual")
        if r["tendencia"] <= -10:
            motivos.append(f"engajamento caiu {-r['tendencia']} pontos em 4 semanas")
        if motivos:
            itens.append({"id": f"s-{p['id']}-1a1", "primeiro_nome": r["primeiro_nome"], "verbo": "Marcar 1:1",
                          "motivo": "; ".join(motivos), "prioridade": 1 if len(motivos) > 1 else 2,
                          "workflow": "convite_1a1",
                          "entrada": {"liderado_id": p["id"], "motivo": "; ".join(motivos)}})
    itens.sort(key=lambda s: (s["prioridade"], s["id"]))
    return {"qtd": len(itens), "itens": itens}


def pegar_liderado(equipe: dict, liderado_id: str) -> dict:
    hoje = _data(equipe["data_referencia"])
    for p in equipe["liderados"]:
        if p["id"] == liderado_id:
            return resumo_pessoa(p, hoje)
    raise KeyError(f"liderado não encontrado: {liderado_id}")


def agregar_equipe(equipe: dict) -> dict:
    hoje = _data(equipe["data_referencia"])
    pessoas = [resumo_pessoa(p, hoje) for p in equipe["liderados"]]
    metas = [m for p in equipe["liderados"] for m in p["metas"]]
    return {
        "total": len(pessoas), "metas_total": len(metas),
        "metas_concluidas": sum(1 for m in metas if m["progresso"] >= 100),
        "metas_atrasadas": sum(p["atrasadas"] for p in pessoas),
        "pessoas_atrasadas": sum(1 for p in pessoas if p["atrasadas"]),
        "engajamento_medio": round(sum(p["engajamento"] for p in pessoas) / len(pessoas)),
        "pessoas_sem_1a1": sum(1 for p in pessoas if p["dias_sem_1a1"] > 30),
        "pessoas": [{k: v for k, v in p.items() if k != "metas"} for p in pessoas],
    }


def metricas_negocio(equipe: dict, fila: list, regra: dict) -> dict:
    """Números do canvas (pilar 1) para o painel executivo. Regra da métrica principal em indicadores.json."""
    hoje = _data(equipe["data_referencia"])
    pessoas = [resumo_pessoa(p, hoje) for p in equipe["liderados"]]
    contatados = {i.get("payload_final", i["payload"]).get("para") for i in fila
                  if i["status"] == "executada" and i["workflow"] in regra["workflows"]}
    vencidas = cobertas = 0
    for p in pessoas:
        vencidas += p["atrasadas"]
        if p["atrasadas"] and (p["dias_sem_1a1"] <= regra["dias"] or p["email"] in contatados):
            cobertas += p["atrasadas"]
    metas = [m for p in equipe["liderados"] for m in p["metas"]]
    concl = sum(1 for m in metas if m["progresso"] >= 100)
    semanas = len(equipe["liderados"][0]["engajamento"])
    serie_eng = [round(sum(p["engajamento"][i] for p in equipe["liderados"]) / len(equipe["liderados"]), 1)
                 for i in range(semanas)]
    rot = [f"sem -{semanas - 1 - i}" if i < semanas - 1 else "atual" for i in range(semanas)]
    risco = [p for p in pessoas if p["status"] != "em_dia"]
    pct_conv = round(100 * cobertas / vencidas, 1) if vencidas else 100.0
    return {
        "conversa_7d": {"valor": pct_conv, "detalhe": f"{cobertas} de {vencidas} metas vencidas"},
        "metas_concluidas": {"valor": round(100 * concl / len(metas), 1), "detalhe": f"{concl} de {len(metas)} metas"},
        "engajamento_medio": {"valor": serie_eng[-1], "serie": serie_eng, "rotulos": rot,
                              "detalhe": f"média de {len(pessoas)} pessoas nas últimas {semanas} semanas"},
        "pessoas_em_risco": {"valor": len(risco),
                             "detalhe": f"{sum(1 for p in risco if p['status'] == 'atrasado')} com meta vencida, "
                                        f"{sum(1 for p in risco if p['status'] == 'atencao')} em atenção"},
    }


def extrair_dados_pedido(pergunta: str, perfil: dict) -> dict:
    """Código, não LLM: tira da pergunta os números que a política precisa."""
    q = normalizar(pergunta)
    dados = {"meses_de_casa": perfil["meses_de_casa"]}
    ante = re.search(r"(\d+)\s*dias?\s*de\s*antecedencia", q)
    dados["dias_de_antecedencia"] = int(ante.group(1)) if ante else 0
    sem_ante = re.sub(r"(\d+)\s*dias?\s*de\s*antecedencia", " ", q)
    periodos = [int(x) for x in re.findall(r"(\d+)\s*(?:e|,|dias)", sem_ante + " ")]
    dados["periodos"] = [p for p in periodos if 0 < p <= 60] or [30]
    if "adot" in q or "adocao" in q:
        dados["papel_parental"] = "adotante_secundario" if ("segundo" in q or "secundari" in q) else "adotante_principal"
    elif any(w in q for w in ("gestante", "gravida", "maternidade", "vou ter um bebe")):
        dados["papel_parental"] = "gestante"
    else:
        dados["papel_parental"] = "parceiro_gestante"
    return dados


def explicar_resultado(perfil: dict, agente: dict) -> str:
    """O texto crítico sai do RESULTADO da política, montado por código."""
    r, f, nome = agente["resultado"], agente["ferramenta"], perfil["primeiro_nome"]
    if f == "dias_de_ferias":
        return (f"{nome}, com {perfil['meses_de_casa']} meses de casa você tem {r['dias']} dias de férias "
                f"por ano (regra {r['regra']} do {r['politica']}).")
    if f == "validar_pedido_ferias":
        if r["aprovado"]:
            return f"{nome}, o pedido segue as regras de fracionamento e antecedência do {r['politica']}."
        return f"{nome}, o pedido precisa de ajuste: " + "; ".join(r["motivos"]) + "."
    if f == "licenca_parental":
        return (f"{nome}, a licença parental para o seu caso é de {r['dias']} dias, remunerada e sem "
                f"descontar das férias ({r['politica']}).")
    raise ValueError(f"ferramenta sem explicação: {f}")


def buscar_faq(faq: dict, pergunta: str) -> dict:
    """Busca simples por palavras (tipo RAG) — só para perguntas abertas, não críticas."""
    q = set(normalizar(pergunta).replace("?", " ").split())
    melhor, pontos = None, 0
    for item in faq["itens"]:
        p = len(q & set(item["tags"]))
        if p > pontos:
            melhor, pontos = item, p
    if melhor is None:
        return {"resposta": "Não achei isso nas perguntas frequentes. Encaminhei para o time de pessoas.", "achou": False}
    return {"resposta": melhor["resposta"], "achou": True}


# ---------------------------------------------------------------- montagem
class AppCoaching:
    def __init__(self, pasta=None, llm=None, relogio=None):
        self.pasta = Path(pasta) if pasta else config.pasta_saida()
        self.pasta.mkdir(parents=True, exist_ok=True)
        acesso = _ler("acesso.json")
        self.equipe = _ler("equipe.json")
        self.usuarios = {u["id"]: Usuario(u["id"], u["nome"], tuple(u["papeis"])) for u in acesso["usuarios"]}
        kw = {"relogio": relogio} if relogio else {}
        self.audit = AuditLog(self.pasta / "audit.jsonl", **kw)
        self.caixa = CaixaSaida(self.pasta / "caixa_saida.jsonl")
        self.fila = FilaAprovacao(self.pasta / "aprovacoes.json", self.audit,
                                  {"enviar_email": self.caixa.enviar_email}, acesso["aprovadores"])
        reg = Registro()
        for i in acesso["identidades"]:
            reg.identidades[i["id"]] = Identidade(i["id"], tuple(i["escopos"]))
        hoje = _data(self.equipe["data_referencia"])
        equipe = self.equipe

        @reg.contexto("equipe", escopo="equipe.ler")
        def _ctx_equipe(args):
            return json.loads(json.dumps(equipe))  # cópia: workflow não altera a fonte

        @reg.contexto("perfil_rh", escopo="rh.perfil.ler")
        def _ctx_perfil(args):
            # Colaborador só consulta o próprio perfil; gestor, RH e sistema consultam a equipe.
            u = args.get("usuario", {})
            if set(u.get("papeis", [])) <= {"colaborador"} and u.get("id") != args["id"]:
                raise PermissaoNegada(f"{u.get('id')} só pode perguntar sobre o próprio perfil")
            for p in equipe["liderados"]:
                if p["id"] == args["id"]:
                    return {"id": p["id"], "primeiro_nome": p["nome"].split()[0],
                            "meses_de_casa": meses_entre(_data(p["admissao"]), hoje)}
            raise KeyError(f"colaborador não encontrado: {args['id']}")

        @reg.contexto("faq", escopo="rh.faq.ler")
        def _ctx_faq(args):
            return _ler("faq.json")

        indicadores = _ler("indicadores.json")
        self.indicadores = indicadores
        pasta = self.pasta

        @reg.contexto("registros_operacao", escopo="audit.ler")
        def _ctx_registros(args):
            linhas, arq = [], pasta / "audit.jsonl"
            if arq.exists():
                for texto in arq.read_text(encoding="utf-8").splitlines():
                    try:
                        linhas.append(json.loads(texto))
                    except ValueError:
                        pass  # linha corrompida: a corrente acusa em quebra_na_linha
            return {"audit": linhas, "quebra_na_linha": self.audit.primeira_quebra(),
                    "enviados": self.caixa.enviados()}

        @reg.contexto("aprovacoes", escopo="aprovacoes.ler")
        def _ctx_aprovacoes(args):
            arq = pasta / "sugestoes.json"
            sug = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []
            return {"fila": json.loads(json.dumps(self.fila.itens)), "sugestoes": sug}

        @reg.funcao("indicadores_executivos")
        def _indicadores(equipe, registros, aprovacoes):
            return executivo.calcular(
                metricas_negocio(equipe, aprovacoes["fila"], indicadores["regra_conversa"]),
                registros["audit"], aprovacoes["fila"], registros["enviados"], aprovacoes["sugestoes"],
                indicadores, registros["quebra_na_linha"], equipe["data_referencia"])

        for f in (metas_atrasadas, detectar_sinais, pegar_liderado, agregar_equipe,
                  extrair_dados_pedido, explicar_resultado, buscar_faq):
            reg.funcoes[f.__name__] = f
        reg.ferramentas.update(grupos_de_ferramentas())
        reg.artefatos["relatorio"] = gerar_artefatos
        reg.artefatos["executivo"] = gerar_executivo
        self.registro = reg
        self.motor = Motor(reg, self.audit, self.fila, llm=llm)
        for arq in sorted(WORKFLOWS.glob("*.json")):
            self.motor.adicionar(arq)
        self.gatilhos = Gatilhos(self.motor, self.usuarios)
        self.sugestoes = []

    # atalhos que o painel e a demo usam
    def usuario(self, uid):
        return self.usuarios[uid]

    def painel(self) -> dict:
        """Componente 'painel de engajamento': dados direto, sem LLM."""
        return agregar_equipe(self.equipe)

    def executivo(self, usuario, gatilho="manual"):
        """Aba 'painel executivo': workflow painel_executivo (só diretoria/admin; negado = auditado)."""
        return self.motor.executar("painel_executivo", {}, usuario, gatilho=gatilho)

    def guardar_sugestoes(self, resultado):
        self.sugestoes = resultado["saida"]["sugestoes"]
        (self.pasta / "sugestoes.json").write_text(json.dumps(self.sugestoes, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
        return self.sugestoes

    def executar_sugestao(self, sugestao_id, usuario):
        """Botão 'executar' da sugestão: roda o workflow; a ação ainda passa por aprovação."""
        s = next(s for s in self.sugestoes if s["id"] == sugestao_id)
        return self.motor.executar(s["workflow"], s["entrada"], usuario, gatilho=f"sugestao:{s['id']}")


def montar(pasta=None, llm=None, relogio=None) -> AppCoaching:
    return AppCoaching(pasta, llm, relogio)
