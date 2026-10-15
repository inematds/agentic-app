"""Painel executivo — a visão de quem patrocina o app (diretoria).

Pergunta: "o app está entregando o resultado de negócio prometido no canvas, com segurança e a que custo?"

Tudo sai de dados que o framework já grava: métricas do app, audit.jsonl (hash encadeado), fila de
aprovações, caixa de saída e sugestões do agente de fundo. Nada é estimado por LLM: as frases de alerta
são montadas por regra, na ordem fixa abaixo. Só biblioteca padrão.

Função central: `calcular(...)` -> dict validado por `ESQUEMA` (esquema.py).
"""
from datetime import datetime

from .esquema import validar

NIVEIS = ("critico", "atencao", "ok")

_num = {"type": "number"}
_int = {"type": "integer", "minimum": 0}
_obj = {"type": "object"}
_pct = {"type": "number", "minimum": 0, "maximum": 100}

ESQUEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["data_referencia", "negocio", "operacao", "controle", "custo", "alertas"],
    "properties": {
        "data_referencia": {"type": "string", "minLength": 10},
        "negocio": {
            "type": "object", "required": ["principal", "metricas"],
            "properties": {
                "principal": {"type": "string"},
                "regra": {"type": "string"},
                "metricas": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["id", "nome", "unidade", "valor", "meta", "sentido", "atingiu", "serie"],
                    "properties": {
                        "id": {"type": "string"}, "nome": {"type": "string", "minLength": 3},
                        "unidade": {"type": "string"}, "valor": _num, "meta": _num, "linha_base": _num,
                        "sentido": {"type": "string", "enum": ["maior", "menor"]},
                        "atingiu": {"type": "boolean"},
                        "serie": {"type": "array", "items": _num},
                        "rotulos_serie": {"type": "array", "items": {"type": "string"}},
                        "detalhe": {"type": "string"},
                    }}},
            }},
        "operacao": {
            "type": "object", "additionalProperties": False,
            "required": ["execucoes", "por_workflow", "por_gatilho", "rascunhos", "tempo_ate_aprovacao", "sugestoes"],
            "properties": {
                "execucoes": _int, "erros": _int, "por_workflow": _obj,
                "por_gatilho": {"type": "object", "required": ["clique", "horario", "evento"],
                                "properties": {"clique": _int, "horario": _int, "evento": _int}},
                "rascunhos": {"type": "object", "required": ["propostos", "aprovados_sem_edicao", "aprovados_com_edicao",
                                                             "rejeitados", "pendentes", "taxa_aprovacao",
                                                             "taxa_edicao", "taxa_rejeicao"],
                              "properties": {"propostos": _int, "aprovados_sem_edicao": _int,
                                             "aprovados_com_edicao": _int, "rejeitados": _int, "pendentes": _int,
                                             "taxa_aprovacao": _pct, "taxa_edicao": _pct, "taxa_rejeicao": _pct}},
                "tempo_ate_aprovacao": {"type": "object", "required": ["amostras", "mediana_min"],
                                        "properties": {"amostras": _int, "mediana_min": {"type": "number", "minimum": 0}}},
                "sugestoes": {"type": "object", "required": ["geradas", "executadas", "taxa"],
                              "properties": {"geradas": _int, "executadas": _int, "taxa": _pct}},
            }},
        "controle": {
            "type": "object", "additionalProperties": False,
            "required": ["negados", "negados_por_papel", "ferramentas_barradas", "corrente_integra",
                         "linhas_audit", "quebra_na_linha", "acoes_externas", "acoes_com_aprovacao",
                         "pct_com_aprovacao"],
            "properties": {
                "negados": _int, "negados_por_papel": _obj, "ferramentas_barradas": _int,
                "corrente_integra": {"type": "boolean"}, "linhas_audit": _int, "quebra_na_linha": _int,
                "acoes_externas": _int, "acoes_com_aprovacao": _int, "pct_com_aprovacao": _pct,
            }},
        "custo": {
            "type": "object", "additionalProperties": False,
            "required": ["chamadas", "tokens_estimados", "por_workflow", "por_modelo", "custo_total", "moeda"],
            "properties": {"chamadas": _int, "tokens_estimados": _int, "por_workflow": _obj, "por_modelo": _obj,
                           "custo_total": {"type": "number", "minimum": 0}, "moeda": {"type": "string"}}},
        "visao": {"type": "object"},
        "alertas": {"type": "array", "minItems": 3, "items": {
            "type": "object", "additionalProperties": False, "required": ["nivel", "texto"],
            "properties": {"nivel": {"type": "string", "enum": list(NIVEIS)},
                           "texto": {"type": "string", "minLength": 10, "maxLength": 220}}}},
    },
}

MAX_ALERTAS = 5


def _pct_de(parte, todo):
    return round(100 * parte / todo, 1) if todo else 0.0


def _tipo_gatilho(g: str) -> str:
    """manual / manual:painel / sugestao:* = clique · agendado:* = horário · evento:* = evento."""
    g = g or "manual"
    if g.startswith("agendado"):
        return "horario"
    if g.startswith("evento"):
        return "evento"
    return "clique"


def _ts(s):
    return datetime.fromisoformat(s)


def _fmt(v):
    return f"{v:g}" if isinstance(v, float) else str(v)


def metrica(cfg: dict, valor, serie=None, rotulos=None, detalhe="") -> dict:
    atingiu = valor >= cfg["meta"] if cfg["sentido"] == "maior" else valor <= cfg["meta"]
    m = {"id": cfg["id"], "nome": cfg["nome"], "unidade": cfg["unidade"], "valor": valor, "meta": cfg["meta"],
         "sentido": cfg["sentido"], "atingiu": atingiu, "serie": list(serie or [valor])}
    if "linha_base" in cfg:
        m["linha_base"] = cfg["linha_base"]
    if rotulos:
        m["rotulos_serie"] = list(rotulos)
    if detalhe:
        m["detalhe"] = detalhe
    return m


_metrica = metrica  # nome antigo (1.1.0)


# ------------------------------------------------------------------ blocos
def bloco_operacao(audit: list, fila: list, sugestoes: list, ignorar=()) -> dict:
    execs = [l for l in audit if l.get("evento") == "workflow.executado" and l.get("workflow") not in ignorar]
    ok = [l for l in execs if l.get("status") == "ok"]
    por_wf, por_g = {}, {"clique": 0, "horario": 0, "evento": 0}
    for l in ok:
        por_wf[l["workflow"]] = por_wf.get(l["workflow"], 0) + 1
        por_g[_tipo_gatilho(l.get("gatilho"))] += 1

    sem_ed = sum(1 for i in fila if i["status"] == "executada" and not i.get("editado"))
    com_ed = sum(1 for i in fila if i["status"] == "executada" and i.get("editado"))
    rej = sum(1 for i in fila if i["status"] == "rejeitada")
    pend = sum(1 for i in fila if i["status"] == "aguardando_aprovacao")
    decididos = sem_ed + com_ed + rej

    # tempo até aprovação: hora da execução que PROPÔS a ação -> hora de acao.executada
    proposta_em = {}
    for l in execs:
        for a in l.get("propostas", []):
            proposta_em[a] = l["ts"]
    tempos = sorted((_ts(l["ts"]) - _ts(proposta_em[l["acao"]])).total_seconds() / 60
                    for l in audit if l.get("evento") == "acao.executada" and l.get("acao") in proposta_em)
    mediana = 0.0
    if tempos:
        meio = len(tempos) // 2
        mediana = tempos[meio] if len(tempos) % 2 else (tempos[meio - 1] + tempos[meio]) / 2
    sug_exec = len({l["gatilho"] for l in ok if str(l.get("gatilho", "")).startswith("sugestao:")})
    return {
        "execucoes": len(ok), "erros": sum(1 for l in execs if l.get("status") == "erro"),
        "por_workflow": dict(sorted(por_wf.items())), "por_gatilho": por_g,
        "rascunhos": {"propostos": len(fila), "aprovados_sem_edicao": sem_ed, "aprovados_com_edicao": com_ed,
                      "rejeitados": rej, "pendentes": pend,
                      "taxa_aprovacao": _pct_de(sem_ed + com_ed, decididos),
                      "taxa_edicao": _pct_de(com_ed, sem_ed + com_ed),
                      "taxa_rejeicao": _pct_de(rej, decididos)},
        "tempo_ate_aprovacao": {"amostras": len(tempos), "mediana_min": round(max(0.0, mediana), 1)},
        "sugestoes": {"geradas": len(sugestoes), "executadas": sug_exec,
                      "taxa": _pct_de(min(sug_exec, len(sugestoes)), len(sugestoes))},
    }


def bloco_controle(audit: list, fila: list, enviados: list, quebra_na_linha: int) -> dict:
    negados, por_papel = 0, {}
    for l in audit:
        if l.get("evento") in ("workflow.negado", "acao.negada", "comando.negado"):
            negados += 1
            for p in l.get("papeis", []) or ["sem papel"]:
                por_papel[p] = por_papel.get(p, 0) + 1
    barradas = sum(1 for l in audit if l.get("evento") == "workflow.executado" and l.get("status") == "negado"
                   and "ferramenta fora do escopo" in str(l.get("erro", "")))
    # 100% das ações externas com aprovação: cada envio da caixa precisa de um acao.executada
    # no audit E de um item 'executada' com aprovador na fila.
    aprovadas_fila = {i["id"] for i in fila if i["status"] == "executada" and i.get("aprovado_por")}
    aprovadas = sum(1 for l in audit if l.get("evento") == "acao.executada" and l.get("aprovado_por")
                    and l.get("acao") in aprovadas_fila)
    externas = len(enviados)
    com_aprov = min(aprovadas, externas)
    return {
        "negados": negados, "negados_por_papel": dict(sorted(por_papel.items())), "ferramentas_barradas": barradas,
        "corrente_integra": quebra_na_linha == 0, "linhas_audit": len(audit), "quebra_na_linha": quebra_na_linha,
        "acoes_externas": externas, "acoes_com_aprovacao": com_aprov,
        "pct_com_aprovacao": _pct_de(com_aprov, externas) if externas else 100.0,
    }


def bloco_custo(audit: list, tabela: dict) -> dict:
    moeda = tabela.get("moeda", "USD")
    por_wf, por_modelo, tokens = {}, {}, 0
    for l in audit:
        if l.get("evento") != "workflow.executado":
            continue
        llm = l.get("llm")
        if llm is None:  # linha antiga (1.0.0): um nó LLM = uma chamada, sem tokens
            llm = {"chamadas": {}, "tokens_estimados": 0}
            for m in l.get("modelos", []):
                llm["chamadas"][m] = llm["chamadas"].get(m, 0) + 1
        n_run = sum(llm["chamadas"].values())
        if n_run:
            por_wf[l["workflow"]] = por_wf.get(l["workflow"], 0) + n_run
        tk_run = llm.get("tokens_estimados", 0)
        tokens += tk_run
        for m, n in llm["chamadas"].items():
            d = por_modelo.setdefault(m, {"chamadas": 0, "tokens_estimados": 0, "custo": 0.0})
            d["chamadas"] += n
            d["tokens_estimados"] += round(tk_run * n / n_run) if n_run else 0
    total = 0.0
    for m, d in por_modelo.items():
        preco = tabela.get("modelos", {}).get(m, {})
        d["custo"] = round(d["chamadas"] * preco.get("por_chamada", 0)
                           + d["tokens_estimados"] / 1000 * preco.get("por_1k_tokens", 0), 4)
        total += d["custo"]
    return {"chamadas": sum(d["chamadas"] for d in por_modelo.values()), "tokens_estimados": tokens,
            "por_workflow": dict(sorted(por_wf.items())), "por_modelo": dict(sorted(por_modelo.items())),
            "custo_total": round(total, 4), "moeda": moeda}


def alertas(negocio: dict, op: dict, ctl: dict, custo: dict, limiares: dict) -> list:
    """Regras fixas, em ordem de gravidade. Mesma entrada, mesmas frases."""
    a = []
    if not ctl["corrente_integra"]:
        a.append(("critico", f"Audit adulterado: a corrente de hash quebra na linha {ctl['quebra_na_linha']}. "
                             "Trate como incidente antes de confiar nos números."))
    if ctl["pct_com_aprovacao"] < 100:
        sem = ctl["acoes_externas"] - ctl["acoes_com_aprovacao"]
        a.append(("critico", f"{sem} de {ctl['acoes_externas']} ações externas saíram sem aprovação registrada "
                             f"({_fmt(ctl['pct_com_aprovacao'])}% com aprovação; o mínimo é 100%)."))
    prin = next(m for m in negocio["metricas"] if m["id"] == negocio["principal"])
    u = prin["unidade"]
    if prin["atingiu"]:
        a.append(("ok", f"Resultado de negócio na meta: {prin['nome'].lower()} em {_fmt(prin['valor'])}{u} "
                        f"(meta {_fmt(prin['meta'])}{u})."))
    else:
        base = f", linha de base {_fmt(prin['linha_base'])}{u}" if "linha_base" in prin else ""
        a.append(("atencao", f"Resultado abaixo da meta: {prin['nome'].lower()} em {_fmt(prin['valor'])}{u}; "
                             f"a meta é {_fmt(prin['meta'])}{u}{base}."))
    for m in negocio["metricas"]:
        if m["id"] != prin["id"] and not m["atingiu"] and m["sentido"] == "menor":
            a.append(("atencao", f"{m['nome']}: {_fmt(m['valor'])} {m['unidade']}, acima do limite de "
                                 f"{_fmt(m['meta'])}."))
    if ctl["ferramentas_barradas"]:
        a.append(("atencao", f"O escopo mínimo barrou {ctl['ferramentas_barradas']} pedido(s) de ferramenta fora "
                             "da política. Revise o prompt ou o modelo desse workflow."))
    r = op["rascunhos"]
    if r["taxa_rejeicao"] > limiares.get("taxa_rejeicao_max", 30) and (r["rejeitados"] + r["aprovados_sem_edicao"]
                                                                        + r["aprovados_com_edicao"]) >= 2:
        a.append(("atencao", f"{_fmt(r['taxa_rejeicao'])}% dos rascunhos decididos foram rejeitados "
                             f"(limite {limiares.get('taxa_rejeicao_max', 30)}%): o texto do agente precisa de ajuste."))
    if r["pendentes"]:
        a.append(("atencao", f"{r['pendentes']} rascunho(s) esperam aprovação humana; nenhum saiu sem revisão."))
    if ctl["corrente_integra"] and ctl["pct_com_aprovacao"] >= 100:
        neg = f" {ctl['negados']} acesso(s) negado(s), todos auditados." if ctl["negados"] else ""
        a.append(("ok", f"Controle em dia: corrente de hash íntegra e 100% das ações externas com aprovação.{neg}"))
    a.append(("ok", f"Uso de LLM: {custo['chamadas']} chamadas, ~{custo['tokens_estimados']} tokens estimados, "
                    f"custo {custo['moeda']} {custo['custo_total']:.2f}."))
    ordem = {n: i for i, n in enumerate(NIVEIS)}
    a.sort(key=lambda x: ordem[x[0]])  # sort é estável: dentro do nível, mantém a ordem das regras
    return [{"nivel": n, "texto": t} for n, t in a[:MAX_ALERTAS]]


def calcular(metricas_app: dict, audit: list, fila: list, enviados: list, sugestoes: list,
             indicadores: dict, quebra_na_linha: int = 0, data_referencia: str = "") -> dict:
    """metricas_app: {id: {"valor": x, "serie": [...], "rotulos": [...], "detalhe": "..."}} vindo do app."""
    mets = []
    for cfg in indicadores["metricas"]:
        v = metricas_app[cfg["id"]]
        mets.append(metrica(cfg, v["valor"], v.get("serie"), v.get("rotulos"), v.get("detalhe", "")))
    negocio = {"principal": indicadores["metrica_principal"], "metricas": mets,
               "regra": indicadores.get("regra_principal", "")}
    # o próprio painel é leitura, não operação de agente: fica fora das contagens (mas no audit)
    op = bloco_operacao(audit, fila, sugestoes, indicadores.get("ignorar_workflows", ()))
    ctl = bloco_controle(audit, fila, enviados, quebra_na_linha)
    custo = bloco_custo(audit, indicadores.get("custo_por_modelo", {}))
    d = {"data_referencia": data_referencia, "negocio": negocio, "operacao": op, "controle": ctl, "custo": custo,
         "alertas": alertas(negocio, op, ctl, custo, indicadores.get("limiares", {}))}
    validar(d, ESQUEMA, "$executivo")
    return d


def resumo_texto(d: dict) -> list:
    """Linhas curtas para o terminal (demo)."""
    prin = next(m for m in d["negocio"]["metricas"] if m["id"] == d["negocio"]["principal"])
    op, ctl, c = d["operacao"], d["controle"], d["custo"]
    r = op["rascunhos"]
    linhas = [f"Resultado: {prin['nome']} = {_fmt(prin['valor'])}{prin['unidade']} "
              f"(meta {_fmt(prin['meta'])}{prin['unidade']}, base {_fmt(prin.get('linha_base', 0))}) -> "
              f"{'ATINGIU' if prin['atingiu'] else 'NÃO ATINGIU'}"]
    for m in d["negocio"]["metricas"]:
        if m is not prin:
            linhas.append(f"  {m['nome']}: {_fmt(m['valor'])} {m['unidade']} (meta {_fmt(m['meta'])}) "
                          f"{'ok' if m['atingiu'] else 'fora'}")
    g = op["por_gatilho"]
    linhas += [
        f"Operação: {op['execucoes']} execuções · clique {g['clique']} · horário {g['horario']} · evento {g['evento']}",
        f"  por workflow: " + ", ".join(f"{k} {v}" for k, v in op["por_workflow"].items()),
        f"  rascunhos: {r['propostos']} propostos · {r['aprovados_sem_edicao']} aprovados sem edição · "
        f"{r['aprovados_com_edicao']} com edição · {r['rejeitados']} rejeitados · {r['pendentes']} pendentes "
        f"(aprovação {_fmt(r['taxa_aprovacao'])}%)",
        f"  sugestões do agente de fundo: {op['sugestoes']['executadas']}/{op['sugestoes']['geradas']} executadas",
        f"Controle: {ctl['negados']} acessos negados {ctl['negados_por_papel']} · ferramentas barradas "
        f"{ctl['ferramentas_barradas']} · corrente {'íntegra' if ctl['corrente_integra'] else 'QUEBRADA'} "
        f"({ctl['linhas_audit']} linhas) · ações externas com aprovação {ctl['acoes_com_aprovacao']}/"
        f"{ctl['acoes_externas']} ({_fmt(ctl['pct_com_aprovacao'])}%)",
        f"Custo: {c['chamadas']} chamadas de LLM " + str({m: v['chamadas'] for m, v in c['por_modelo'].items()})
        + f" · ~{c['tokens_estimados']} tokens · {c['moeda']} {c['custo_total']:.2f}",
        "Alertas:",
    ]
    linhas += [f"  [{a['nivel']}] {a['texto']}" for a in d["alertas"]]
    return linhas
