"""Centro de Comando — duas telas para quem opera e acompanha o app ao vivo.

- Agent Control Tower (aba "Agentes"): o que os agentes estão fazendo agora. Semáforo por workflow,
  última execução, falhas, pausados, próximo disparo agendado, fila de aprovação por idade (SLA),
  corrente do audit e os últimos eventos. Ações: pausar, retomar, rodar agora, reexecutar, escalar.
- Mission Control (aba "Negócio"): o resultado do canvas ao vivo. Metas contra a meta, quanto falta,
  quem precisa de ação e em que pé está cada caso. Ações: acionar o agente certo, aprovar, rejeitar.

Regras que não mudam:
- Ação de controle (pausar, retomar, rodar, reexecutar, escalar) é do próprio app, não ação externa:
  não passa pela fila, mas exige papel (`acoes.controlar_agentes`) e grava no audit — negada também.
- Quem opera nunca aprova nem envia. Escalar só marca o item; quem aprova continua sendo quem aprovava.
- Reexecutar só refaz o que dá para refazer sem guardar a entrada da pessoa: execução agendada (a entrada
  está no gatilho) ou de entrada vazia. O audit guarda só o hash da entrada, de propósito.
- Frases de alerta montadas por regra, em ordem fixa. Nada de LLM aqui. Só biblioteca padrão.

Funções centrais: `Controle` (estado em comando.json) e `calcular(...)` -> dict validado por `ESQUEMA`.
"""
import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from .esquema import validar
from .executivo import bloco_controle, bloco_custo, NIVEIS
from .seguranca import PermissaoNegada

DIAS = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6}
SAUDE = ("vermelho", "amarelo", "verde")
HASH_VAZIO = hashlib.sha256(json.dumps({}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]

_int = {"type": "integer", "minimum": 0}
_txt = {"type": "string"}
_alerta = {"type": "object", "additionalProperties": False, "required": ["nivel", "texto"],
           "properties": {"nivel": {"type": "string", "enum": list(NIVEIS)},
                          "texto": {"type": "string", "minLength": 10, "maxLength": 220}}}

ESQUEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["gerado_em", "saude", "alertas", "agentes", "negocio", "pode"],
    "properties": {
        "gerado_em": {"type": "string", "minLength": 16},
        "saude": {"type": "string", "enum": list(SAUDE)},
        "alertas": {"type": "array", "items": _alerta},
        "pode": {"type": "object", "required": ["controlar", "aprovar", "acionar"],
                 "properties": {"controlar": {"type": "boolean"}, "aprovar": {"type": "boolean"},
                                "acionar": {"type": "object"}}},
        "agentes": {
            "type": "object", "additionalProperties": False,
            "required": ["saude", "workflows", "fila", "problemas", "eventos", "controle", "custo", "sla_horas"],
            "properties": {
                "saude": {"type": "string", "enum": list(SAUDE)},
                "sla_horas": {"type": "number", "minimum": 0},
                "workflows": {"type": "array", "items": {
                    "type": "object",
                    "required": ["id", "titulo", "estado", "semaforo", "ok", "erros", "negados", "bloqueados",
                                 "ultima", "proximo", "pode_rodar_agora", "reexecutar"],
                    "properties": {
                        "id": _txt, "titulo": _txt,
                        "estado": {"type": "string", "enum": ["ativo", "pausado"]},
                        "semaforo": {"type": "string", "enum": ["verde", "amarelo", "vermelho", "pausado", "sem_execucao"]},
                        "ok": _int, "erros": _int, "negados": _int, "bloqueados": _int,
                        "pode_rodar_agora": {"type": "boolean"},
                    }}},
                "fila": {"type": "array", "items": {
                    "type": "object", "required": ["id", "tipo", "workflow", "para", "idade_h", "vencida", "escalada"],
                    "properties": {"idade_h": {"type": "number", "minimum": 0}, "vencida": {"type": "boolean"}}}},
                "problemas": {"type": "array"}, "eventos": {"type": "array"},
                "controle": {"type": "object"}, "custo": {"type": "object"},
            }},
        "negocio": {
            "type": "object", "additionalProperties": False,
            "required": ["saude", "metricas", "principal", "faltam", "decisoes", "pendentes", "alertas"],
            "properties": {
                "saude": {"type": "string", "enum": list(SAUDE)},
                "principal": _txt, "faltam": _int,
                "metricas": {"type": "array", "minItems": 1},
                "decisoes": {"type": "array", "items": {
                    "type": "object", "required": ["id", "nome", "status", "motivos", "situacao", "proxima"],
                    "properties": {"situacao": {"type": "string",
                                                "enum": ["rascunho_pendente", "enviado", "rejeitado", "sem_acao"]}}}},
                "pendentes": {"type": "array"},
                "alertas": {"type": "array", "items": _alerta},
            }},
    },
}


# ------------------------------------------------------------------ estado de controle
class Controle:
    """Pausas e escaladas, em comando.json. Toda mudança (e toda negativa) vai para o audit."""

    def __init__(self, arquivo, audit, papeis_controle):
        self.arquivo = Path(arquivo)
        self.audit = audit
        self.papeis = list(papeis_controle)
        self.estado = self._carregar()

    def _carregar(self):
        if self.arquivo.exists():
            return json.loads(self.arquivo.read_text(encoding="utf-8"))
        return {"pausados": {}, "escaladas": {}}

    def _salvar(self):
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps(self.estado, ensure_ascii=False, indent=2), encoding="utf-8")

    def checar(self, usuario, acao, alvo):
        if not usuario.tem_algum(self.papeis):
            self.audit.registrar("comando.negado", acao=acao, alvo=alvo, usuario=usuario.id,
                                 papeis=list(usuario.papeis), motivo="papel sem permissão de controlar agentes")
            raise PermissaoNegada(f"{usuario.id} não controla agentes (papéis: {', '.join(self.papeis)})")

    def pausado(self, workflow_id) -> bool:
        return workflow_id in self.estado["pausados"]

    def pausar(self, workflow_id, usuario, motivo=""):
        self.checar(usuario, "pausar", workflow_id)
        if self.pausado(workflow_id):
            raise ValueError(f"{workflow_id} já está pausado")
        linha = self.audit.registrar("comando.pausar", workflow=workflow_id, usuario=usuario.id, motivo=motivo)
        self.estado["pausados"][workflow_id] = {"por": usuario.id, "motivo": motivo, "ts": linha["ts"]}
        self._salvar()
        return self.estado["pausados"][workflow_id]

    def retomar(self, workflow_id, usuario):
        self.checar(usuario, "retomar", workflow_id)
        if not self.pausado(workflow_id):
            raise ValueError(f"{workflow_id} não está pausado")
        self.audit.registrar("comando.retomar", workflow=workflow_id, usuario=usuario.id)
        info = self.estado["pausados"].pop(workflow_id)
        self._salvar()
        return info

    def escalar(self, item, usuario, motivo=""):
        """Marca a aprovação parada. Não muda quem aprova: operação nunca aprova."""
        self.checar(usuario, "escalar", item["id"])
        if item["status"] != "aguardando_aprovacao":
            raise ValueError(f"{item['id']} já está '{item['status']}'")
        linha = self.audit.registrar("comando.escalar", acao=item["id"], usuario=usuario.id, motivo=motivo)
        self.estado["escaladas"][item["id"]] = {"por": usuario.id, "motivo": motivo, "ts": linha["ts"]}
        self._salvar()
        return self.estado["escaladas"][item["id"]]


# ------------------------------------------------------------------ funções puras
def _ts(s):
    return datetime.fromisoformat(s)


def aware(agora: datetime) -> datetime:
    return agora if agora.tzinfo else agora.astimezone()


def proximo_disparo(g: dict, agora: datetime) -> datetime:
    """Próxima data/hora local (sem fuso) em que um gatilho agendado roda, a partir de `agora`."""
    local = aware(agora).astimezone().replace(tzinfo=None) if agora.tzinfo else agora
    h, m = (int(x) for x in g["hora"].split(":"))
    for dias in range(8):
        d = (local + timedelta(days=dias)).replace(hour=h, minute=m, second=0, microsecond=0)
        if d.weekday() == DIAS[g["dia_semana"]] and d >= local.replace(second=0, microsecond=0):
            return d
    raise ValueError(f"gatilho sem próximo disparo: {g}")


def reexecucao(linha: dict, spec: dict, executar_como: str):
    """(entrada, usuario_id) para refazer a execução, ou (None, motivo) quando não dá."""
    if linha.get("evento") != "workflow.executado":
        return None, "acesso negado não se refaz: peça a quem tem o papel"
    g = linha.get("gatilho") or ""
    if g.startswith("agendado:"):
        for ag in spec.get("gatilhos", []):
            if ag["tipo"] == "agendado" and g == f"agendado:{ag['dia_semana']} {ag['hora']}":
                return dict(ag.get("entrada", {})), ag["usuario"]
    if linha.get("hash_entrada") == HASH_VAZIO:
        if executar_como in spec["seguranca"]["executar"]:
            return {}, executar_como
        return None, f"só quem tem o papel ({', '.join(spec['seguranca']['executar'])}) refaz este workflow"
    return None, "entrada não guardada (o audit só tem o hash): refaça pela tela de origem"


def _evento_texto(l: dict) -> str:
    ev = l.get("evento", "")
    if ev == "workflow.executado":
        st = {"ok": "ok", "erro": "FALHOU", "negado": "barrado no escopo", "pausado": "bloqueado (pausado)"}
        return f"{l['workflow']} · {st.get(l.get('status'), l.get('status'))} · {l.get('usuario')} · {l.get('gatilho')}"
    if ev == "workflow.negado":
        return f"{l.get('usuario')} ({', '.join(l.get('papeis', []))}) barrado em {l['workflow']}"
    if ev == "acao.executada":
        return f"{l['acao']} aprovada por {l.get('aprovado_por')}{' com edição' if l.get('editado') else ''} e executada"
    if ev == "acao.rejeitada":
        return f"{l['acao']} rejeitada por {l.get('rejeitado_por')}"
    if ev == "acao.negada":
        return f"{l.get('usuario')} tentou decidir {l['acao']} sem papel"
    if ev == "comando.pausar":
        return f"{l['workflow']} pausado por {l['usuario']}" + (f": {l['motivo']}" if l.get("motivo") else "")
    if ev == "comando.retomar":
        return f"{l['workflow']} retomado por {l['usuario']}"
    if ev == "comando.escalar":
        return f"{l['acao']} escalada por {l['usuario']}" + (f": {l['motivo']}" if l.get("motivo") else "")
    if ev in ("comando.rodar", "comando.reexecutar"):
        alvo = l.get("workflow") or l.get("run_id")
        return f"{'rodar agora' if ev == 'comando.rodar' else 'reexecução'} de {alvo} por {l['usuario']}"
    if ev == "comando.negado":
        return f"{l.get('usuario')} tentou {l.get('acao')} em {l.get('alvo')} sem papel"
    return ev


def _horas(a, b):
    return max(0.0, round((a - b).total_seconds() / 3600, 1))


def torre(catalogo: dict, estado: dict, audit: list, fila: list, enviados: list, quebra: int,
          cfg: dict, agora: datetime, pode_controlar: bool) -> dict:
    """Aba Agentes: semáforo por workflow, fila por idade, problemas e eventos recentes."""
    agora_a = aware(agora)
    sla = cfg.get("sla_aprovacao_horas", 24)
    ignorar = set(cfg.get("ignorar_workflows", []))
    pausados, escaladas = estado.get("pausados", {}), estado.get("escaladas", {})
    proposta_em = {}
    for l in audit:
        if l.get("evento") == "workflow.executado":
            for a in l.get("propostas", []):
                proposta_em[a] = l["ts"]

    pend = [i for i in fila if i["status"] == "aguardando_aprovacao"]
    fila_out = []
    for i in pend:
        idade = _horas(agora_a, _ts(proposta_em[i["id"]])) if i["id"] in proposta_em else 0.0
        fila_out.append({"id": i["id"], "tipo": i["tipo"], "workflow": i["workflow"],
                         "para": i["payload"].get("para", ""), "solicitante": i.get("solicitante", ""),
                         "idade_h": idade, "vencida": idade > sla, "escalada": i["id"] in escaladas,
                         "escalada_info": escaladas.get(i["id"])})
    fila_out.sort(key=lambda x: (-x["idade_h"], x["id"]))
    vencidas_por_wf = {}
    for x in fila_out:
        if x["vencida"]:
            vencidas_por_wf[x["workflow"]] = vencidas_por_wf.get(x["workflow"], 0) + 1

    wfs = []
    for wid, spec in catalogo.items():
        linhas = [l for l in audit if l.get("workflow") == wid
                  and l.get("evento") in ("workflow.executado", "workflow.negado")]
        execs = [l for l in linhas if l["evento"] == "workflow.executado"]
        conta = {s: sum(1 for l in execs if l.get("status") == s) for s in ("ok", "erro", "negado", "pausado")}
        reais = [l for l in execs if l.get("status") != "pausado"]
        ultima = reais[-1] if reais else None
        agendados = [g for g in spec.get("gatilhos", []) if g["tipo"] == "agendado"]
        prox = min((proximo_disparo(g, agora) for g in agendados), default=None)
        if wid in pausados:
            sem = "pausado"
        elif ultima is None:
            sem = "sem_execucao"
        elif ultima.get("status") == "erro":
            sem = "vermelho"
        elif conta["erro"] or vencidas_por_wf.get(wid):
            sem = "amarelo"
        else:
            sem = "verde"
        reexec = None
        if ultima is not None:
            entrada, quem = reexecucao(ultima, spec, cfg.get("executar_como", "sistema"))
            reexec = {"run_id": ultima["run_id"], "pode": entrada is not None,
                      "como": quem if entrada is not None else None,
                      "motivo": None if entrada is not None else quem}
        wfs.append({
            "id": wid, "titulo": spec.get("titulo", wid), "estado": "pausado" if wid in pausados else "ativo",
            "pausa": pausados.get(wid), "semaforo": sem, "leitura": wid in ignorar,
            "ok": conta["ok"], "erros": conta["erro"],
            "negados": conta["negado"] + sum(1 for l in linhas if l["evento"] == "workflow.negado"),
            "bloqueados": conta["pausado"], "gatilhos": [g["tipo"] for g in spec.get("gatilhos", [])],
            "ultima": None if ultima is None else {
                "run_id": ultima["run_id"], "ts": ultima["ts"], "status": ultima.get("status"),
                "usuario": ultima.get("usuario"), "gatilho": ultima.get("gatilho"),
                "erro": ultima.get("erro"), "idade_h": _horas(agora_a, _ts(ultima["ts"]))},
            "proximo": prox.strftime("%Y-%m-%d %H:%M") if prox else None,
            "pode_rodar_agora": bool(agendados) and pode_controlar and wid not in pausados,
            "reexecutar": reexec, "vencidas": vencidas_por_wf.get(wid, 0),
        })
    ordem = {"vermelho": 0, "amarelo": 1, "pausado": 2, "verde": 3, "sem_execucao": 4}
    wfs.sort(key=lambda w: (w["leitura"], ordem[w["semaforo"]], w["id"]))

    problemas = []
    for l in audit:
        if l.get("workflow") in ignorar:
            continue
        ruim = (l.get("evento") == "workflow.executado" and l.get("status") in ("erro", "negado", "pausado")) \
            or l.get("evento") == "workflow.negado"
        if ruim:
            entrada, quem = reexecucao(l, catalogo[l["workflow"]], cfg.get("executar_como", "sistema")) \
                if l["workflow"] in catalogo else (None, "workflow fora do catálogo")
            if l.get("status") == "negado":
                entrada, quem = None, "barrado no escopo: refazer repete o bloqueio; ajuste prompt ou modelo"
            problemas.append({"run_id": l.get("run_id"), "workflow": l["workflow"], "ts": l["ts"],
                              "tipo": l.get("status") if l["evento"] == "workflow.executado" else "acesso_negado",
                              "usuario": l.get("usuario"), "detalhe": l.get("erro") or l.get("motivo") or "",
                              "reexecutar": {"pode": entrada is not None,
                                             "motivo": None if entrada is not None else quem}})
    problemas = problemas[-cfg.get("problemas_max", 10):][::-1]

    feed = [{"ts": l["ts"], "evento": l.get("evento"), "texto": _evento_texto(l)}
            for l in audit if l.get("workflow") not in ignorar]
    feed = feed[-cfg.get("eventos_no_feed", 15):][::-1]

    ctl = bloco_controle(audit, fila, enviados, quebra)
    custo = bloco_custo(audit, cfg.get("custo_por_modelo", {}))
    return {"sla_horas": sla, "workflows": wfs, "fila": fila_out, "problemas": problemas, "eventos": feed,
            "controle": ctl, "custo": custo}


def alertas_agentes(t: dict) -> list:
    a = []
    ctl = t["controle"]
    if not ctl["corrente_integra"]:
        a.append(("critico", f"Audit adulterado: a corrente quebra na linha {ctl['quebra_na_linha']}. "
                             "Trate como incidente antes de agir."))
    if ctl["pct_com_aprovacao"] < 100:
        a.append(("critico", f"{ctl['acoes_externas'] - ctl['acoes_com_aprovacao']} ação(ões) externa(s) saíram "
                             "sem aprovação registrada. Pause o workflow e investigue."))
    for w in t["workflows"]:
        if w["semaforo"] == "vermelho":
            erro = (w["ultima"].get("erro") or "")[:90]
            a.append(("critico", f"{w['id']}: a última execução falhou ({erro}). Corrija e reexecute."))
    venc = [x for x in t["fila"] if x["vencida"]]
    if venc:
        a.append(("atencao", f"{len(venc)} aprovação(ões) passaram do SLA de {t['sla_horas']:g} h; a mais antiga "
                             f"espera há {venc[0]['idade_h']:g} h. Escale para quem aprova."))
    for w in t["workflows"]:
        if w["estado"] == "pausado":
            p = w["pausa"] or {}
            extra = f" ({w['bloqueados']} disparo(s) bloqueado(s))" if w["bloqueados"] else ""
            a.append(("atencao", f"{w['id']} está pausado por {p.get('por')}{extra}."))
    if not any(n == "critico" for n, _ in a):
        ativos = sum(1 for w in t["workflows"] if w["estado"] == "ativo" and not w["leitura"])
        ok = sum(w["ok"] for w in t["workflows"] if not w["leitura"])
        a.append(("ok", f"Agentes no ar: {ativos} workflows ativos, {ok} execuções ok, corrente íntegra e "
                        "toda ação externa com aprovação."))
    ordem = {n: i for i, n in enumerate(NIVEIS)}
    a.sort(key=lambda x: ordem[x[0]])
    return [{"nivel": n, "texto": t_[:220]} for n, t_ in a]


def missao(metricas: list, principal: str, conversa: dict, decisoes: list, fila_torre: list) -> dict:
    """Aba Negócio: o canvas ao vivo e a lista de quem precisa de ação."""
    prin = next(m for m in metricas if m["id"] == principal)
    parte, todo = conversa.get("parte", 0), conversa.get("todo", 0)
    faltam = max(0, math.ceil(prin["meta"] / 100 * todo - 1e-9) - parte) if prin["unidade"] == "%" else 0
    sem_acao = [d for d in decisoes if d["situacao"] == "sem_acao"]
    pend = [x for x in fila_torre]
    a = []
    if prin["atingiu"]:
        a.append(("ok", f"{prin['nome']}: {prin['valor']:g}{prin['unidade']}, na meta ({prin['meta']:g}{prin['unidade']})."))
    else:
        a.append(("atencao", f"{prin['nome']}: {prin['valor']:g}{prin['unidade']} (meta {prin['meta']:g}"
                             f"{prin['unidade']}). Faltam {faltam} conversa(s) com meta vencida para bater."))
    if sem_acao:
        nomes = ", ".join(d["nome"].split()[0] for d in sem_acao[:4]) + ("…" if len(sem_acao) > 4 else "")
        a.append(("atencao", f"{len(sem_acao)} pessoa(s) em risco sem nenhuma ação em andamento: {nomes}."))
    if pend:
        a.append(("atencao", f"{len(pend)} rascunho(s) esperando aprovação humana; nada sai sem ela."))
    for m in metricas:
        if m["id"] != principal and not m["atingiu"]:
            a.append(("atencao", f"{m['nome']}: {m['valor']:g} {m['unidade']} (meta "
                                 f"{'≥' if m['sentido'] == 'maior' else '≤'} {m['meta']:g})."))
    ordem = {n: i for i, n in enumerate(NIVEIS)}
    a.sort(key=lambda x: ordem[x[0]])
    alertas = [{"nivel": n, "texto": t[:220]} for n, t in a]
    saude = "verde" if prin["atingiu"] and not sem_acao else ("vermelho" if len(sem_acao) >= 3 and not prin["atingiu"]
                                                               else "amarelo")
    return {"saude": saude, "principal": principal, "metricas": metricas, "faltam": faltam,
            "decisoes": decisoes, "pendentes": pend, "alertas": alertas}


def _saude_de(alertas):
    if any(a["nivel"] == "critico" for a in alertas):
        return "vermelho"
    if any(a["nivel"] == "atencao" for a in alertas):
        return "amarelo"
    return "verde"


def calcular(catalogo, estado, audit, fila, enviados, quebra, cfg, agora, metricas, principal, conversa,
             decisoes, pode) -> dict:
    t = torre(catalogo, estado, audit, fila, enviados, quebra, cfg, agora, pode["controlar"])
    al_ag = alertas_agentes(t)
    t["saude"] = _saude_de(al_ag)
    n = missao(metricas, principal, conversa, decisoes, t["fila"])
    ordem = {s: i for i, s in enumerate(SAUDE)}
    d = {"gerado_em": aware(agora).isoformat(timespec="seconds"),
         "saude": min(t["saude"], n["saude"], key=lambda s: ordem[s]),
         "alertas": al_ag, "agentes": t, "negocio": n, "pode": pode}
    validar(d, ESQUEMA, "$comando")
    return d


def resumo_texto(d: dict) -> list:
    """Linhas curtas para o terminal (demo)."""
    t, n = d["agentes"], d["negocio"]
    li = [f"Saúde geral: {d['saude'].upper()} · agentes {t['saude']} · negócio {n['saude']}",
          "Agent Control Tower:"]
    for w in t["workflows"]:
        if w["leitura"]:
            continue
        u = w["ultima"]
        li.append(f"  [{w['semaforo']:>12}] {w['id']:<20} ok {w['ok']} · erros {w['erros']} · bloqueados "
                  f"{w['bloqueados']}" + (f" · última {u['status']} ({u['gatilho']})" if u else "")
                  + (f" · próximo {w['proximo']}" if w["proximo"] else ""))
    li.append(f"  fila: {len(t['fila'])} aprovação(ões), {sum(1 for x in t['fila'] if x['vencida'])} fora do SLA "
              f"de {t['sla_horas']:g} h, {sum(1 for x in t['fila'] if x['escalada'])} escalada(s)")
    li += [f"  [{a['nivel']}] {a['texto']}" for a in d["alertas"]]
    li.append("Mission Control (negócio):")
    for m in n["metricas"]:
        li.append(f"  {m['nome']}: {m['valor']:g} {m['unidade']} (meta {m['meta']:g}) "
                  f"{'ok' if m['atingiu'] else 'fora'}")
    li.append(f"  faltam {n['faltam']} conversa(s) para a meta · {len(n['decisoes'])} pessoa(s) na fila de decisão")
    for x in n["decisoes"][:5]:
        li.append(f"    {x['nome']:<18} {x['situacao']:<18} -> {x['proxima']['rotulo']}")
    li += [f"  [{a['nivel']}] {a['texto']}" for a in n["alertas"]]
    return li
