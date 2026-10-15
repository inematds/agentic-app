"""Visão geral → detalhe: filtros e agregações dos painéis (só biblioteca padrão, determinístico).

Os quatro painéis usam o mesmo padrão de BI: cartões de número no topo, filtros na lateral, gráficos no meio e o
detalhe (com as ações) embaixo, filtrado pelo que se clicou. Aqui fica só o cálculo; o desenho está em
`graficos.py` e `painel_bi.py`.

Filtros chegam como texto da URL e são normalizados por `normalizar(...)`: valor desconhecido vira o padrão, nunca erro.
"""
from datetime import datetime, timedelta

PERIODOS = {"7d": ("últimos 7 dias", 7), "30d": ("últimos 30 dias", 30), "8s": ("últimas 8 semanas", 56),
            "tudo": ("tudo", None)}
GATILHOS = {"clique": "clique", "horario": "horário", "evento": "evento", "comando": "Centro de Comando"}
SITUACOES_EXEC = {"ok": "ok", "negado": "negado", "pausado": "pausado", "falha": "falha"}
DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def normalizar(f: dict, workflows=(), padrao_periodo="8s") -> dict:
    f = dict(f or {})
    return {
        "periodo": f.get("periodo") if f.get("periodo") in PERIODOS else padrao_periodo,
        "workflow": f.get("workflow") if f.get("workflow") in workflows else "",
        "gatilho": f.get("gatilho") if f.get("gatilho") in GATILHOS else "",
        "situacao": f.get("situacao") if f.get("situacao") in SITUACOES_EXEC else "",
        "dia": f.get("dia") if isinstance(f.get("dia"), str) and len(f.get("dia", "")) == 10 else "",
    }


def tipo_gatilho(g: str) -> str:
    g = g or "manual"
    if g.startswith("comando:"):
        return "comando"
    if g.startswith("agendado"):
        return "horario"
    if g.startswith("evento"):
        return "evento"
    return "clique"


def situacao(l: dict) -> str:
    if l.get("evento") == "workflow.negado":
        return "negado"
    return {"ok": "ok", "erro": "falha", "negado": "negado", "pausado": "pausado"}.get(l.get("status"), "falha")


def _local(ts: str) -> datetime:
    """Hora local sem fuso (o dia e a hora do gráfico são os de quem olha o painel)."""
    d = datetime.fromisoformat(ts)
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def _agora_local(agora: datetime) -> datetime:
    return agora.astimezone().replace(tzinfo=None) if agora.tzinfo else agora


def janela(f: dict, agora: datetime, audit: list):
    """(início, fim) do período em hora local. 'tudo' começa no primeiro registro."""
    fim = _agora_local(agora)
    dias = PERIODOS[f["periodo"]][1]
    if dias is None:
        tss = [_local(l["ts"]) for l in audit if l.get("ts")]
        ini = min(tss) if tss else fim
        return ini.replace(hour=0, minute=0, second=0, microsecond=0), fim
    return (fim - timedelta(days=dias - 1)).replace(hour=0, minute=0, second=0, microsecond=0), fim


def _mediana(xs):
    xs = sorted(xs)
    if not xs:
        return 0.0
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def execucoes(audit: list, ignorar=()) -> list:
    """Linhas de execução (inclusive negadas por papel), fora as leituras de painel."""
    return [l for l in audit if l.get("evento") in ("workflow.executado", "workflow.negado")
            and l.get("workflow") not in ignorar and l.get("ts")]


def filtrar(linhas: list, f: dict, ini: datetime, fim: datetime, sem=()) -> list:
    """Aplica os filtros; `sem` lista filtros a ignorar (o gráfico de um filtro mostra todas as opções dele)."""
    out = []
    for l in linhas:
        t = _local(l["ts"])
        if not (ini <= t <= fim):
            continue
        if f["workflow"] and "workflow" not in sem and l.get("workflow") != f["workflow"]:
            continue
        if f["gatilho"] and "gatilho" not in sem and tipo_gatilho(l.get("gatilho")) != f["gatilho"]:
            continue
        if f["situacao"] and "situacao" not in sem and situacao(l) != f["situacao"]:
            continue
        if f["dia"] and "dia" not in sem and t.strftime("%Y-%m-%d") != f["dia"]:
            continue
        out.append(l)
    return out


def _conta(linhas):
    c = {k: 0 for k in SITUACOES_EXEC}
    for l in linhas:
        c[situacao(l)] += 1
    return c


def operacao(audit: list, fila: list, f: dict, agora: datetime, sla_h: float = 24, ignorar=(),
             custo_tab=None, detalhe_max=60) -> dict:
    """Agregados da operação dos agentes no filtro: cartões, séries e o detalhe filtrado."""
    base = execucoes(audit, ignorar)
    ini, fim = janela(f, agora, audit)
    linhas = filtrar(base, f, ini, fim)
    c = _conta(linhas)
    tentativas = c["ok"] + c["falha"] + c["negado"]

    # período anterior do mesmo tamanho (para a variação nos cartões)
    var = None
    if PERIODOS[f["periodo"]][1]:
        dur = fim - ini
        ant = filtrar(base, f, ini - dur - timedelta(seconds=1), ini - timedelta(seconds=1))
        ca = _conta(ant)
        var = {"execucoes": len(linhas) - len(ant),
               "sucesso_pp": round((100 * c["ok"] / tentativas if tentativas else 0)
                                   - (100 * ca["ok"] / (ca["ok"] + ca["falha"] + ca["negado"])
                                      if (ca["ok"] + ca["falha"] + ca["negado"]) else 0), 1)}

    # séries (cada gráfico ignora o próprio filtro para mostrar as alternativas)
    dias = []
    d = ini
    while d.date() <= fim.date():
        dias.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    por_dia = {x: {k: 0 for k in SITUACOES_EXEC} for x in dias}
    for l in filtrar(base, f, ini, fim, sem=("dia",)):
        k = _local(l["ts"]).strftime("%Y-%m-%d")
        if k in por_dia:
            por_dia[k][situacao(l)] += 1
    por_hora = {h: {k: 0 for k in SITUACOES_EXEC} for h in range(24)}
    for l in linhas:
        por_hora[_local(l["ts"]).hour][situacao(l)] += 1
    por_wf = {}
    for l in filtrar(base, f, ini, fim, sem=("workflow",)):
        por_wf.setdefault(l["workflow"], {k: 0 for k in SITUACOES_EXEC})[situacao(l)] += 1
    por_g = {k: 0 for k in GATILHOS}
    for l in filtrar(base, f, ini, fim, sem=("gatilho",)):
        por_g[tipo_gatilho(l.get("gatilho"))] += 1
    por_sit = _conta(filtrar(base, f, ini, fim, sem=("situacao",)))

    # fila e rascunhos (proposta = ts da execução que propôs)
    proposta_em, wf_da = {}, {}
    for l in audit:
        if l.get("evento") == "workflow.executado":
            for a in l.get("propostas", []):
                proposta_em[a] = _local(l["ts"])
                wf_da[a] = l["workflow"]
    agora_l = _agora_local(agora)
    faixas = [("<4 h", 0, 4), (f"4–{sla_h:g} h", 4, sla_h), (f"{sla_h:g}–{2 * sla_h:g} h", sla_h, 2 * sla_h),
              (f">{2 * sla_h:g} h", 2 * sla_h, float("inf"))]
    idade = {r: 0 for r, _, _ in faixas}
    pend = [i for i in fila if i["status"] == "aguardando_aprovacao"
            and (not f["workflow"] or i["workflow"] == f["workflow"])]
    fora_sla = 0
    for i in pend:
        h = (agora_l - proposta_em[i["id"]]).total_seconds() / 3600 if i["id"] in proposta_em else 0
        fora_sla += h > sla_h
        for r, a, b in faixas:
            if a <= h < b:
                idade[r] += 1
    desfecho = {"sem_edicao": 0, "com_edicao": 0, "rejeitado": 0, "pendente": 0}
    tempos = []
    decisao_em = {l["acao"]: _local(l["ts"]) for l in audit if l.get("evento") == "acao.executada"}
    for i in fila:
        t = proposta_em.get(i["id"])
        if t is None or not (ini <= t <= fim) or (f["workflow"] and wf_da.get(i["id"]) != f["workflow"]):
            continue
        if i["status"] == "executada":
            desfecho["com_edicao" if i.get("editado") else "sem_edicao"] += 1
            if i["id"] in decisao_em:
                tempos.append((decisao_em[i["id"]] - t).total_seconds() / 3600)
        elif i["status"] == "rejeitada":
            desfecho["rejeitado"] += 1
        else:
            desfecho["pendente"] += 1

    chamadas, custo = 0, 0.0
    tab = (custo_tab or {}).get("modelos", {})
    for l in linhas:
        llm = l.get("llm") or {}
        tk = llm.get("tokens_estimados", 0)
        n_run = sum((llm.get("chamadas") or {}).values())
        for m, n in (llm.get("chamadas") or {}).items():
            chamadas += n
            p = tab.get(m, {})
            custo += n * p.get("por_chamada", 0) + (tk * n / n_run if n_run else 0) / 1000 * p.get("por_1k_tokens", 0)

    detalhe = [{"run_id": l.get("run_id"), "ts": l["ts"], "workflow": l["workflow"], "situacao": situacao(l),
                "gatilho": l.get("gatilho"), "tipo_gatilho": tipo_gatilho(l.get("gatilho")),
                "usuario": l.get("usuario"), "erro": l.get("erro") or l.get("motivo") or ""}
               for l in reversed(linhas)][:detalhe_max]
    return {
        "filtros": f, "periodo_rotulo": PERIODOS[f["periodo"]][0],
        "inicio": ini.strftime("%Y-%m-%d"), "fim": fim.strftime("%Y-%m-%d"),
        "kpis": {"execucoes": len(linhas), "ok": c["ok"], "falhas": c["falha"], "negados": c["negado"],
                 "bloqueados": c["pausado"], "sucesso": round(100 * c["ok"] / tentativas, 1) if tentativas else 0.0,
                 "fila": len(pend), "fora_sla": fora_sla, "mediana_aprovar_h": round(_mediana(tempos), 1),
                 "aprovacoes_medidas": len(tempos), "chamadas_llm": chamadas, "custo": round(custo, 4),
                 "moeda": (custo_tab or {}).get("moeda", "USD"), "variacao": var},
        "por_dia": [{"dia": x, **por_dia[x]} for x in dias],
        "por_hora": [{"hora": h, **por_hora[h]} for h in range(24)],
        "por_workflow": dict(sorted(por_wf.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))),
        "por_gatilho": por_g, "por_situacao": por_sit,
        "fila_idade": idade, "desfecho": desfecho, "detalhe": detalhe,
    }


# ------------------------------------------------------------------ negócio (filtros de render)
SITUACOES_PESSOA = {"sem_acao": "nenhuma ação", "rejeitado": "rascunho rejeitado",
                    "rascunho_pendente": "rascunho esperando", "enviado": "e-mail enviado"}
STATUS_PESSOA = {"atrasado": "meta vencida", "atencao": "atenção"}
MOTIVOS = {"meta": "meta vencida", "1a1": "sem 1:1 há +30 dias", "engajamento": "engajamento caindo"}


def motivos_de(d: dict) -> set:
    m = set()
    if d.get("atrasadas"):
        m.add("meta")
    if d.get("dias_sem_1a1", 0) > 30:
        m.add("1a1")
    if any("engajamento caiu" in x for x in d.get("motivos", [])):
        m.add("engajamento")
    return m


def normalizar_negocio(f: dict) -> dict:
    f = dict(f or {})
    return {"situacao": f.get("situacao") if f.get("situacao") in SITUACOES_PESSOA else "",
            "status": f.get("status") if f.get("status") in STATUS_PESSOA else "",
            "motivo": f.get("motivo") if f.get("motivo") in MOTIVOS else ""}


def filtrar_decisoes(decisoes: list, f: dict, sem=()) -> list:
    out = []
    for d in decisoes:
        if f["situacao"] and "situacao" not in sem and d["situacao"] != f["situacao"]:
            continue
        if f["status"] and "status" not in sem and d["status"] != f["status"]:
            continue
        if f["motivo"] and "motivo" not in sem and f["motivo"] not in motivos_de(d):
            continue
        out.append(d)
    return out
