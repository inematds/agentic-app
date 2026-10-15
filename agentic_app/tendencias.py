"""Painel de tendências — "para onde está indo?" (o executivo responde "está entregando agora?").

Entrada: uma série semanal de snapshots dos indicadores (histórico de exemplo + snapshots gravados pelo
próprio app toda semana). Saída: variação semana a semana e no período, média móvel, ritmo (regressão linear
simples), projeção até a meta, sinais antecipados, comparação entre pessoas e cenários "e se".

Tudo determinístico, só biblioteca padrão. O LLM (opcional) só redige a narrativa A PARTIR destes números;
nunca calcula nada.

Regras (documentadas em docs/ARQUITETURA.md):
- ritmo = inclinação da reta de mínimos quadrados (x = semanas desde o 1º ponto, y = valor), por semana.
- projeção = a partir do ÚLTIMO valor, no ritmo: semanas = (meta - último) / ritmo; data = última data + semanas×7
  (arredondado para cima). Só projeta com pelo menos `min_pontos` semanas; senão diz "histórico insuficiente".
- sinal antecipado = N movimentos seguidos no sentido ruim no fim da série (N = `quedas_seguidas_alerta`).
- cenário "e se": regra explícita do app (ver `cenario_mais_1a1`), sem previsão "mágica".
"""
import json
import math
from datetime import date, timedelta
from pathlib import Path

from .esquema import validar

CAMPOS_SNAPSHOT = ("metas_concluidas", "engajamento_medio", "pessoas_em_risco", "conversa_7d", "uns_1a1_7d",
                   "execucoes", "taxa_sem_edicao", "chamadas_llm", "custo", "eventos_risco")

_num = {"type": "number"}
ESQUEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["data_referencia", "horizonte_fim", "pontos", "semanas", "exemplo", "metricas", "pessoas",
                 "cenarios", "sinais"],
    "properties": {
        "data_referencia": {"type": "string", "minLength": 10}, "horizonte_fim": {"type": "string", "minLength": 10},
        "pontos": {"type": "integer", "minimum": 0}, "semanas": {"type": "array", "items": {"type": "string"}},
        "exemplo": {"type": "boolean"}, "narrativa": {"type": "string"},
        "metricas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "nome", "grupo", "unidade", "sentido", "serie", "media_movel", "ultimo",
                         "var_semana", "var_periodo", "ritmo_semana", "quedas_seguidas", "projecao"],
            "properties": {
                "id": {"type": "string"}, "nome": {"type": "string"},
                "grupo": {"type": "string", "enum": ["resultado", "adocao", "custo", "risco"]},
                "unidade": {"type": "string"}, "sentido": {"type": "string", "enum": ["maior", "menor", "neutro"]},
                "meta": _num, "serie": {"type": "array", "items": _num}, "media_movel": {"type": "array", "items": _num},
                "ultimo": _num, "var_semana": _num, "var_periodo": _num, "ritmo_semana": _num,
                "quedas_seguidas": {"type": "integer", "minimum": 0},
                "projecao": {"type": "object", "required": ["status", "texto"], "properties": {
                    "status": {"type": "string", "enum": ["atingida", "atinge", "nao_atinge", "rompe", "mantem",
                                                          "sem_meta", "insuficiente"]},
                    "data": {"type": "string"}, "texto": {"type": "string", "minLength": 10}}},
            }}},
        "pessoas": {"type": "array"}, "cenarios": {"type": "array"},
        "sinais": {"type": "array", "items": {"type": "object", "required": ["nivel", "texto"], "properties": {
            "nivel": {"type": "string", "enum": ["critico", "atencao", "ok"]}, "texto": {"type": "string"}}}},
    },
}


# ------------------------------------------------------------------ matemática simples
def media_movel(serie, janela):
    return [round(sum(serie[max(0, i - janela + 1):i + 1]) / len(serie[max(0, i - janela + 1):i + 1]), 2)
            for i in range(len(serie))]


def regressao(xs, ys):
    """Mínimos quadrados: devolve (inclinação, intercepto)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return b, my - b * mx


def movimentos_ruins_seguidos(serie, sentido):
    """Quantos movimentos seguidos no sentido ruim no FIM da série (queda se 'maior', alta se 'menor')."""
    if sentido == "neutro":
        return 0
    n = 0
    for a, b in zip(reversed(serie[:-1]), reversed(serie[1:])):
        if (b < a) if sentido == "maior" else (b > a):
            n += 1
        else:
            break
    return n


def _br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _f(v):
    if isinstance(v, float):
        return f"{v:.1f}".replace(".0", "") if abs(v - round(v)) < 0.05 else f"{v:.1f}"
    return str(v)


def projetar(ultimo, ritmo, meta, sentido, ultima_data: date, fim: date, rotulo_fim: str, unidade=""):
    """Projeção a partir do último valor, no ritmo atual. Ver docstring do módulo."""
    u = unidade if unidade == "%" else f" {unidade}" if unidade else ""
    ur = " p.p." if unidade == "%" else u  # ritmo de % é em pontos percentuais
    atingiu = ultimo >= meta if sentido == "maior" else ultimo <= meta
    a_favor = ritmo > 0 if sentido == "maior" else ritmo < 0
    if atingiu:
        if a_favor or ritmo == 0:
            return {"status": "atingida", "texto": f"Meta de {_f(meta)}{u} já atingida e o ritmo não piora."}
        semanas = (meta - ultimo) / ritmo
        quando = ultima_data + timedelta(days=math.ceil(semanas * 7))
        if quando > fim:
            return {"status": "mantem", "data": "",
                    "texto": f"Na meta de {_f(meta)}{u}, mas piorando {_f(abs(ritmo))}{ur}/semana; segura até o "
                             f"{rotulo_fim} ({_br(fim)})."}
        return {"status": "rompe", "data": _br(quando),
                "texto": f"Ainda na meta, mas no ritmo atual ({_f(ritmo)}{ur}/semana) sai da meta de {_f(meta)}{u} "
                         f"em {_br(quando)}."}
    if not a_favor:
        return {"status": "nao_atinge", "data": "",
                "texto": f"No ritmo atual ({_f(ritmo)}{ur}/semana) a meta de {_f(meta)}{u} não é atingida: "
                         "o número anda no sentido contrário."}
    semanas = (meta - ultimo) / ritmo
    quando = ultima_data + timedelta(days=math.ceil(semanas * 7))
    if quando > fim:
        return {"status": "nao_atinge", "data": _br(quando),
                "texto": f"No ritmo atual ({_f(ritmo)}{ur}/semana), a meta de {_f(meta)}{u} só seria atingida em "
                         f"{_br(quando)}: não é atingida até o {rotulo_fim} ({_br(fim)})."}
    return {"status": "atinge", "data": _br(quando),
            "texto": f"No ritmo atual ({_f(ritmo)}{ur}/semana), a meta de {_f(meta)}{u} é atingida em {_br(quando)}."}


# ------------------------------------------------------------------ histórico
def snapshot_de(executivo: dict, uns_1a1_7d: int) -> dict:
    """Uma linha do histórico a partir do dict do painel executivo (1.1.0). Chave = segunda-feira da semana.

    Desde 1.4.0, execuções, rascunhos, chamadas, custo e negados vêm da janela dos ÚLTIMOS 7 DIAS (`visao`,
    calculada pelo próprio workflow do snapshot). Antes vinham acumulados desde o início, e a série subia sempre.
    """
    m = {x["id"]: x["valor"] for x in executivo["negocio"]["metricas"]}
    r, ctl = executivo["operacao"]["rascunhos"], executivo["controle"]
    decididos = r["aprovados_sem_edicao"] + r["aprovados_com_edicao"] + r["rejeitados"]
    v = executivo.get("visao")
    if v:
        k, ds = v["kpis"], v["desfecho"]
        dec = ds["sem_edicao"] + ds["com_edicao"] + ds["rejeitado"]
        ref = date.fromisoformat(executivo["data_referencia"])
        semana = ref - timedelta(days=ref.weekday())
        return {"semana": semana.isoformat(),
                "metas_concluidas": m.get("metas_concluidas", 0), "engajamento_medio": m.get("engajamento_medio", 0),
                "pessoas_em_risco": m.get("pessoas_em_risco", 0), "conversa_7d": m.get("conversa_7d", 0),
                "uns_1a1_7d": uns_1a1_7d, "execucoes": k["execucoes"],
                "taxa_sem_edicao": round(100 * ds["sem_edicao"] / dec, 1) if dec else 0.0,
                "chamadas_llm": k["chamadas_llm"], "custo": k["custo"],
                "eventos_risco": k["negados"] + ctl["ferramentas_barradas"] + (0 if ctl["corrente_integra"] else 1)}
    ref = date.fromisoformat(executivo["data_referencia"])
    semana = ref - timedelta(days=ref.weekday())  # segunda-feira da semana: um ponto por semana
    return {"semana": semana.isoformat(),
            "metas_concluidas": m.get("metas_concluidas", 0), "engajamento_medio": m.get("engajamento_medio", 0),
            "pessoas_em_risco": m.get("pessoas_em_risco", 0), "conversa_7d": m.get("conversa_7d", 0),
            "uns_1a1_7d": uns_1a1_7d, "execucoes": executivo["operacao"]["execucoes"],
            "taxa_sem_edicao": round(100 * r["aprovados_sem_edicao"] / decididos, 1) if decididos else 0.0,
            "chamadas_llm": executivo["custo"]["chamadas"], "custo": executivo["custo"]["custo_total"],
            "eventos_risco": ctl["negados"] + ctl["ferramentas_barradas"] + (0 if ctl["corrente_integra"] else 1)}


def gravar_snapshot(linha: dict, arquivo) -> dict:
    """Acrescenta (ou substitui, se a semana já existe) uma linha em historico.jsonl."""
    arq = Path(arquivo)
    linhas = ler_vivo(arq)
    linhas = [l for l in linhas if l["semana"] != linha["semana"]] + [linha]
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text("".join(json.dumps(l, ensure_ascii=False, sort_keys=True) + "\n"
                           for l in sorted(linhas, key=lambda l: l["semana"])), encoding="utf-8")
    return linha


def ler_vivo(arquivo) -> list:
    arq = Path(arquivo)
    if not arq.exists():
        return []
    return [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]


def juntar(exemplo: list, vivo: list) -> list:
    """Histórico = exemplo + snapshots reais; snapshot real da mesma semana vence."""
    por_semana = {l["semana"]: l for l in exemplo}
    por_semana.update({l["semana"]: l for l in vivo})
    return [por_semana[s] for s in sorted(por_semana)]


# ------------------------------------------------------------------ cenário "e se"
def cenario_mais_1a1(ultimo, ritmo, uns_hoje, uns_cenario, pessoas_com_meta_vencida):
    """Regra explícita do app de coaching:
    cada conversa 1:1 a mais por semana com alguém que tem meta vencida cobre essa pessoa inteira; com P pessoas
    nessa situação, cada conversa extra vale 100/P pontos na cobertura (teto 100%). Depois do salto, o número
    segue no mesmo ritmo de hoje. Não é previsão: é a conta da regra.
    """
    if pessoas_com_meta_vencida <= 0:
        return ultimo
    salto = (uns_cenario - uns_hoje) * 100 / pessoas_com_meta_vencida
    return round(min(100.0, max(0.0, ultimo + salto)), 1)


# ------------------------------------------------------------------ análise
def analisar(historico: list, cfg: dict, pessoas: list = (), pessoas_com_meta_vencida: int = 0,
             data_referencia: str = "", exemplo: bool = False) -> dict:
    fim = date.fromisoformat(cfg["horizonte_fim"])
    rotulo_fim = cfg.get("rotulo_horizonte", "fim do horizonte")
    minimo, janela, limite_quedas = cfg.get("min_pontos", 4), cfg.get("janela_media_movel", 4), \
        cfg.get("quedas_seguidas_alerta", 3)
    datas = [date.fromisoformat(l["semana"]) for l in historico]
    xs = [(d - datas[0]).days / 7 for d in datas] if datas else []
    metricas, sinais = [], []
    for m in cfg["metricas"]:
        serie = [float(l[m["id"]]) for l in historico if m["id"] in l]
        n = len(serie)
        item = {"id": m["id"], "nome": m["nome"], "grupo": m["grupo"], "unidade": m["unidade"],
                "sentido": m["sentido"], "serie": serie, "media_movel": media_movel(serie, janela) if serie else [],
                "ultimo": serie[-1] if serie else 0.0,
                "var_semana": round(serie[-1] - serie[-2], 2) if n >= 2 else 0.0,
                "var_periodo": round(serie[-1] - serie[0], 2) if n >= 2 else 0.0,
                "ritmo_semana": 0.0, "quedas_seguidas": movimentos_ruins_seguidos(serie, m["sentido"])}
        if "meta" in m:
            item["meta"] = m["meta"]
        if n < minimo:
            item["projecao"] = {"status": "insuficiente",
                                "texto": f"Histórico insuficiente: {n} semana(s), mínimo {minimo}. Sem projeção."}
        else:
            b, _ = regressao(xs[-n:], serie)
            item["ritmo_semana"] = round(b, 3)
            if "meta" in m and m["sentido"] != "neutro":
                item["projecao"] = projetar(serie[-1], round(b, 3), m["meta"], m["sentido"], datas[-1], fim,
                                            rotulo_fim, m["unidade"])
            else:
                item["projecao"] = {"status": "sem_meta",
                                    "texto": f"Sem meta definida; ritmo de {_f(round(b, 2))} {m['unidade']}/semana."}
        if item["quedas_seguidas"] >= limite_quedas:
            mov = "caindo" if m["sentido"] == "maior" else "subindo"
            sinais.append(("atencao", f"Sinal antecipado: {m['nome'].lower()} {mov} há {item['quedas_seguidas']} "
                                      f"semanas seguidas (de {_f(serie[-1 - item['quedas_seguidas']])} para "
                                      f"{_f(serie[-1])})."))
        st = item["projecao"]["status"]
        if st == "rompe":
            sinais.append(("atencao", f"{m['nome']}: {item['projecao']['texto']}"))
        elif st == "nao_atinge" and m["grupo"] == "resultado":
            sinais.append(("atencao", f"{m['nome']}: {item['projecao']['texto']}"))
        elif st == "atinge":
            sinais.append(("ok", f"{m['nome']}: {item['projecao']['texto']}"))
        if m["grupo"] == "risco" and "limite" in m and serie and serie[-1] > m["limite"]:
            sinais.append(("critico", f"{m['nome']}: {_f(serie[-1])} na última semana, acima do limite de "
                                      f"{_f(m['limite'])}."))
        metricas.append(item)

    # comparação entre pessoas (séries curtas do próprio app: engajamento das últimas semanas)
    comp = []
    for p in pessoas:
        s = [float(v) for v in p["serie"]]
        b, _ = regressao(list(range(len(s))), s) if len(s) >= 2 else (0.0, 0.0)
        q = movimentos_ruins_seguidos(s, "maior")
        comp.append({"id": p["id"], "nome": p["nome"], "serie": s, "ritmo": round(b, 2), "quedas_seguidas": q})
    comp.sort(key=lambda p: (p["ritmo"], p["id"]))
    em_queda = [p for p in comp if p["quedas_seguidas"] >= limite_quedas]
    if em_queda:
        nomes = ", ".join(p["nome"].split()[0] for p in em_queda)
        sinais.append(("atencao", f"Engajamento caindo {limite_quedas} semanas seguidas em {len(em_queda)} pessoa(s): "
                                  f"{nomes}."))

    cenarios = []
    por_id = {m["id"]: m for m in metricas}
    uns = [float(l["uns_1a1_7d"]) for l in historico if "uns_1a1_7d" in l]
    for c in cfg.get("cenarios", []):
        alvo = por_id.get(c["metrica"])
        mcfg = next((m for m in cfg["metricas"] if m["id"] == c["metrica"]), None)
        if not alvo or not mcfg or not uns:
            continue
        if alvo["projecao"]["status"] == "insuficiente":
            cenarios.append({"id": c["id"], "descricao": c["descricao"], "texto": alvo["projecao"]["texto"]})
            continue
        novo = cenario_mais_1a1(alvo["ultimo"], alvo["ritmo_semana"], uns[-1], c["valor"], pessoas_com_meta_vencida)
        proj = projetar(novo, alvo["ritmo_semana"], mcfg["meta"], mcfg["sentido"], datas[-1], fim, rotulo_fim,
                        mcfg["unidade"])
        cenarios.append({"id": c["id"], "descricao": c["descricao"], "alavanca_hoje": uns[-1], "alavanca": c["valor"],
                         "valor_hoje": alvo["ultimo"], "valor_cenario": novo, "projecao": proj,
                         "texto": f"{c['descricao']}: {_f(alvo['ultimo'])}% vira {_f(novo)}%. {proj['texto']}"})

    ordem = {"critico": 0, "atencao": 1, "ok": 2}
    sinais.sort(key=lambda s: ordem[s[0]])
    d = {"data_referencia": data_referencia or (historico[-1]["semana"] if historico else ""),
         "horizonte_fim": cfg["horizonte_fim"], "pontos": len(historico), "semanas": [l["semana"] for l in historico],
         "exemplo": exemplo, "metricas": metricas, "pessoas": comp, "cenarios": cenarios,
         "sinais": [{"nivel": n, "texto": t} for n, t in sinais]}
    validar(d, ESQUEMA, "$tendencias")
    return d


def fatos_para_narrativa(d: dict) -> dict:
    """Frases prontas, todas com números do código, para o nó LLM (redigir) costurar."""
    m = {x["id"]: x for x in d["metricas"]}
    princ = m.get("conversa_7d") or d["metricas"][0]
    def u(x):
        return x["unidade"] if x["unidade"] == "%" else f" {x['unidade']}"
    partes = [f"{x['nome'].lower()} de {_f(x['serie'][0])}{u(x)} para {_f(x['ultimo'])}{u(x)}"
              for x in d["metricas"] if x["grupo"] == "resultado" and len(x["serie"]) >= 2]
    outros = [s["texto"] for s in d["sinais"] if princ["projecao"]["texto"] not in s["texto"]]
    return {"pontos": d["pontos"],
            "periodo": f"Em {d['pontos']} semanas: " + "; ".join(partes) + "." if partes else "",
            "principal": f"{princ['nome']}: {princ['projecao']['texto']}",
            "sinais": " ".join(outros[:2]),
            "cenario": d["cenarios"][0]["texto"] if d["cenarios"] else ""}


def resumo_texto(d: dict) -> list:
    linhas = [f"Histórico: {d['pontos']} semanas ({d['semanas'][0] if d['semanas'] else '-'} a "
              f"{d['semanas'][-1] if d['semanas'] else '-'}){' · inclui dado de EXEMPLO' if d['exemplo'] else ''}"]
    for x in d["metricas"]:
        linhas.append(f"  {x['nome']}: {_f(x['ultimo'])} {x['unidade']} · semana {x['var_semana']:+g} · período "
                      f"{x['var_periodo']:+g} · ritmo {x['ritmo_semana']:+g}/sem -> {x['projecao']['texto']}")
    for c in d["cenarios"]:
        linhas.append(f"  E se: {c['texto']}")
    linhas.append("Sinais:")
    linhas += [f"  [{s['nivel']}] {s['texto']}" for s in d["sinais"]]
    return linhas
