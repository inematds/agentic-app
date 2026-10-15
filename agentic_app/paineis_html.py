"""Páginas web do painel executivo e do de tendências no layout de BI (painel_bi).

O relatório HTML/PDF salvo em saida/ (relatorio.py) continua igual: é o documento para imprimir e arquivar.
Estas são as telas de uso diário: cartões, filtros, gráficos clicáveis e o detalhe.
"""
import html
from datetime import date, timedelta

from . import graficos as G
from . import visao as V
from .painel_bi import Url, alertas, ativos, card, kpi, pagina, select
from .relatorio import GRUPO_ROT, STATUS_COR, STATUS_ROT, _grafico_linha


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _f(v):
    return G._f(v)


def _semanas(por_dia):
    """Soma o 'por dia' em semanas (chave = segunda-feira)."""
    out = {}
    for x in por_dia:
        d = date.fromisoformat(x["dia"])
        seg = (d - timedelta(days=d.weekday())).isoformat()
        acc = out.setdefault(seg, {k: 0 for k in V.SITUACOES_EXEC})
        for k in V.SITUACOES_EXEC:
            acc[k] += x[k]
    return out


# ------------------------------------------------------------------ Executivo
def render_executivo_bi(d: dict, uid: str, agora: str = "") -> str:
    v = d["visao"]
    f, k = v["filtros"], v["kpis"]
    url = Url("/executivo", {"usuario": uid, "agora": agora}, f)
    neg, ctl, c = d["negocio"], d["controle"], d["custo"]
    prin = next(m for m in neg["metricas"] if m["id"] == neg["principal"])
    outras = [m for m in neg["metricas"] if m is not prin]
    var = k["variacao"]
    kpis = '<div class="kpis">' + "".join(
        [kpi(prin["nome"], f'{_f(prin["valor"])}<small>{_e(prin["unidade"])}</small>',
             f'meta {_f(prin["meta"])}{_e(prin["unidade"])} · base {_f(prin.get("linha_base", 0))}{_e(prin["unidade"])}',
             tom="ok" if prin["atingiu"] else "critico")]
        + [kpi(m["nome"], f'{_f(m["valor"])}<small> {_e(m["unidade"])}</small>',
               f'meta {"≥" if m["sentido"] == "maior" else "≤"} {_f(m["meta"])}', tom="ok" if m["atingiu"] else "atencao")
           for m in outras]
        + [kpi("Ações externas com aprovação", f'{_f(ctl["pct_com_aprovacao"])}<small>%</small>',
               f'{ctl["acoes_com_aprovacao"]} de {ctl["acoes_externas"]} · corrente {"íntegra" if ctl["corrente_integra"] else "QUEBRADA"}',
               tom="ok" if ctl["pct_com_aprovacao"] >= 100 and ctl["corrente_integra"] else "critico"),
           kpi("Execuções dos agentes", _f(k["execucoes"]), v["periodo_rotulo"],
               delta=f"{var['execucoes']:+d} vs período anterior" if var else None),
           kpi("Custo de LLM", f'{_e(k["moeda"])} {k["custo"]:.2f}', f'{k["chamadas_llm"]} chamadas no período')]) + "</div>"
    wfs = sorted({w for w in v["por_workflow"]} | ({f["workflow"]} if f["workflow"] else set()))
    filtros = (select("periodo", "Período", [(x, r) for x, (r, _) in V.PERIODOS.items()], f["periodo"])
               + select("workflow", "Workflow", [("", "todos")] + [(w, w) for w in wfs], f["workflow"]))
    chips = ativos(url, {"workflow": "workflow"})

    sem = _semanas(v["por_dia"])
    cats = sorted(sem)
    g_sem = G.colunas(cats, G.STATUS_SERIES, sem, rotulos_x={s: f"{s[8:10]}/{s[5:7]}" for s in cats}, largura=1000,
                      altura=220)
    eng = next((m for m in neg["metricas"] if m["id"] == "engajamento_medio"), None)
    g_eng = (G.linha(eng.get("rotulos_serie") or [str(i) for i in range(len(eng["serie"]))],
                     [(eng["nome"], eng["serie"], "var(--amb)", False)], meta=(eng["meta"], f"meta {_f(eng['meta'])}"),
                     largura=440) if eng else "")
    ds = v["desfecho"]
    g_desf = G.rosca([("sem_edicao", "aprovado sem edição", ds["sem_edicao"], "var(--ok)"),
                      ("com_edicao", "aprovado com edição", ds["com_edicao"], "var(--amb)"),
                      ("pendente", "esperando", ds["pendente"], "var(--mut)"),
                      ("rejeitado", "rejeitado", ds["rejeitado"], "var(--bad)")], centro="rascunhos")
    g_wf = G.barras([(w, w, x) for w, x in v["por_workflow"].items()], G.STATUS_SERIES,
                    href=lambda w: url.alternar("workflow", w), destaque=f["workflow"], largura=440)
    g_llm = G.barras([(w, w, n) for w, n in sorted(c["por_workflow"].items(), key=lambda kv: -kv[1])], largura=440)
    g_neg = G.barras([(p, p, n) for p, n in ctl["negados_por_papel"].items()], largura=440, largura_rot=110) \
        if ctl["negados_por_papel"] else '<p class="mut">Nenhum acesso negado.</p>'
    graficos = ('<div class="grade bloco">'
                + card("Execuções dos agentes por semana", g_sem, "Cor = situação. Período e workflow da lateral.", largo=True)
                + card("Uso por workflow", g_wf, "Clique para filtrar.")
                + card("Desfecho dos rascunhos", g_desf, "Propostos no período: o humano aprova, edita ou rejeita.")
                + card(eng["nome"] if eng else "Engajamento", g_eng, "Últimas semanas · traço = meta.")
                + card("Chamadas de LLM por workflow", g_llm, "Desde o início.")
                + card("Acessos negados por papel", g_neg, "Todos ficam no audit.")
                + "</div>")
    metas = "".join(
        f'<tr><td>{_e(m["nome"])}</td><td><b>{_f(m["valor"])}</b> {_e(m["unidade"])}</td>'
        f'<td>{"≥" if m["sentido"] == "maior" else "≤"} {_f(m["meta"])}</td><td>{_f(m.get("linha_base", "—"))}</td>'
        f'<td><span class="tag" style="border-color:{"var(--ok)" if m["atingiu"] else "var(--bad)"};'
        f'color:{"var(--ok)" if m["atingiu"] else "var(--bad)"}">{"na meta" if m["atingiu"] else "fora da meta"}</span></td>'
        f'<td><small>{_e(m.get("detalhe", ""))}</small></td></tr>' for m in neg["metricas"])
    modelos = "".join(f'<tr><td><code>{_e(m)}</code></td><td>{x["chamadas"]}</td><td>{x["tokens_estimados"]}</td>'
                      f'<td>{_e(c["moeda"])} {x["custo"]:.2f}</td></tr>' for m, x in c["por_modelo"].items())
    r = d["operacao"]["rascunhos"]
    controle = (f'<table><tr><th>Indicador</th><th>Valor</th></tr>'
                f'<tr><td>Corrente de hash do audit</td><td>{"íntegra" if ctl["corrente_integra"] else "QUEBRADA na linha " + str(ctl["quebra_na_linha"])} ({ctl["linhas_audit"]} linhas)</td></tr>'
                f'<tr><td>Acessos negados (todos auditados)</td><td>{ctl["negados"]}</td></tr>'
                f'<tr><td>Ferramentas barradas pelo escopo mínimo</td><td>{ctl["ferramentas_barradas"]}</td></tr>'
                f'<tr><td>Rascunhos: aprovação · edição · rejeição</td><td>{_f(r["taxa_aprovacao"])}% · {_f(r["taxa_edicao"])}% · {_f(r["taxa_rejeicao"])}%</td></tr>'
                f'</table>')
    detalhe = ('<div class="grade bloco">'
               + card("Alertas executivos", alertas(d["alertas"]), "Montados por regra, nunca por LLM.", largo=True)
               + card("Resultado de negócio (canvas)", f'<div class="tab"><table><tr><th>Métrica</th><th>Valor</th><th>Meta</th>'
                      f'<th>Base</th><th>Status</th><th>Detalhe</th></tr>{metas}</table></div>',
                      _e(neg.get("regra", "")), largo=True)
               + card("Controle e risco", f'<div class="tab">{controle}</div>')
               + card("Custo e uso de LLM", f'<div class="tab"><table><tr><th>Modelo</th><th>Chamadas</th><th>Tokens est.</th>'
                      f'<th>Custo</th></tr>{modelos}</table></div>', "Preços em indicadores.json (0 = modelo local).")
               + "</div>")
    return pagina(titulo="Painel executivo", ativo="executivo", uid=uid, agora=agora, chip="Painel executivo · diretoria",
                  h1="O app está entregando o resultado prometido?",
                  sub=f"Data de referência {_e(d['data_referencia'])}. Calculado do audit, da fila, da caixa de saída e dos "
                      "dados do app; nenhum número vem de LLM.",
                  filtros_html=filtros, kpis_html=chips + kpis, corpo_html=graficos + detalhe,
                  url_limpar=Url("/executivo", {"usuario": uid, "agora": agora}, {})(),
                  rodape="workflow painel_executivo · acesso: diretoria e admin · cada consulta fica no audit log.")


# ------------------------------------------------------------------ Tendências
SITU_PROJ = {"bom": "na meta ou chegando", "risco": "não chega ou piorando", "insuficiente": "histórico insuficiente"}


def _situ(m):
    s = m["projecao"]["status"]
    if s in ("atingida", "atinge"):
        return "bom"
    if s in ("nao_atinge", "rompe", "mantem"):
        return "risco"
    return "insuficiente" if s == "insuficiente" else "bom"


def render_tendencias_bi(d: dict, uid: str, filtros=None) -> str:
    q = dict(filtros or {})
    f = {"grupo": q.get("grupo") if q.get("grupo") in GRUPO_ROT else "",
         "projecao": q.get("projecao") if q.get("projecao") in SITU_PROJ else ""}
    url = Url("/tendencias", {"usuario": uid}, f)
    todas = d["metricas"]
    mets = [m for m in todas if (not f["grupo"] or m["grupo"] == f["grupo"])
            and (not f["projecao"] or _situ(m) == f["projecao"])]
    kpis = '<div class="kpis">' + "".join(
        kpi(m["nome"], f'{_f(m["ultimo"])}<small> {_e(m["unidade"])}</small>',
            f'{STATUS_ROT.get(m["projecao"]["status"], "")} · {m["ritmo_semana"]:+.2f}/semana',
            tom={"bom": "ok", "risco": "atencao"}.get(_situ(m)), delta=f'{m["var_semana"]:+g} na semana')
        for m in mets[:8]) + "</div>"
    filtros_html = (select("grupo", "Grupo", [("", "todos")] + list(GRUPO_ROT.items()), f["grupo"])
                    + select("projecao", "Projeção", [("", "todas")] + list(SITU_PROJ.items()), f["projecao"]))
    chips = ativos(url, {"grupo": "grupo", "projecao": "projeção"})
    base_g = [m for m in todas if not f["projecao"] or _situ(m) == f["projecao"]]
    g_grupo = G.barras([(g, r, sum(1 for m in base_g if m["grupo"] == g)) for g, r in GRUPO_ROT.items()],
                       href=lambda g: url.alternar("grupo", g), destaque=f["grupo"], largura=440, largura_rot=170)
    base_p = [m for m in todas if not f["grupo"] or m["grupo"] == f["grupo"]]
    cor_p = {"bom": "var(--ok)", "risco": "var(--warn)", "insuficiente": "var(--mut)"}
    g_proj = G.rosca([(s, r, sum(1 for m in base_p if _situ(m) == s), cor_p[s]) for s, r in SITU_PROJ.items()],
                     href=lambda s: url.alternar("projecao", s), centro="métricas", destaque=f["projecao"])
    linhas = "".join(card(m["nome"], _grafico_linha(m, d["semanas"], d["horizonte_fim"], largura=440),
                          f'<span class="tag" style="border-color:{STATUS_COR[m["projecao"]["status"]]};color:'
                          f'{STATUS_COR[m["projecao"]["status"]]}">{_e(STATUS_ROT[m["projecao"]["status"]])}</span> '
                          f'{_e(m["projecao"]["texto"])}') for m in mets) or card("Métricas", '<p class="mut">Nenhuma no filtro.</p>')
    cen = d.get("cenarios", [])
    g_cen = G.barras([(c["id"] + s, rot, val) for c in cen for s, rot, val in
                      (("h", f"hoje ({_f(c['alavanca_hoje'])})", c["valor_hoje"]),
                       ("c", f"com {_f(c['alavanca'])}", c["valor_cenario"]))], unidade="%", largura=440, largura_rot=120) \
        if cen else '<p class="mut">Sem cenário (histórico insuficiente).</p>'
    pes = sorted([p for p in d.get("pessoas", []) if p["quedas_seguidas"]], key=lambda p: -p["quedas_seguidas"])
    g_pes = G.barras([(p["id"], p["nome"].split()[0], p["quedas_seguidas"]) for p in pes], largura=440, largura_rot=90) \
        if pes else '<p class="mut">Ninguém com quedas seguidas.</p>'
    graficos = ('<div class="grade bloco">'
                + card("Métricas por grupo", g_grupo, "Clique para filtrar.")
                + card("Projeção até a meta", g_proj, f"Horizonte: {_e(d['horizonte_fim'])}. Clique para filtrar.")
                + linhas
                + card("Cenários \"e se\"", g_cen, " ".join(_e(c["texto"]) for c in cen))
                + card("Pessoas com quedas seguidas de engajamento", g_pes, "Semanas seguidas em queda (sinal antecipado).")
                + "</div>")
    tab = "".join(
        f'<tr><td>{_e(m["nome"])}</td><td>{_f(m["ultimo"])} {_e(m["unidade"])}</td><td>{m["ritmo_semana"]:+.2f}</td>'
        f'<td><span class="tag" style="border-color:{STATUS_COR[m["projecao"]["status"]]};color:{STATUS_COR[m["projecao"]["status"]]}">'
        f'{_e(STATUS_ROT[m["projecao"]["status"]])}</span></td><td><small>{_e(m["projecao"]["texto"])}</small></td></tr>'
        for m in mets)
    sinais = [{"nivel": s["nivel"], "texto": s["texto"]} for s in d.get("sinais", [])]
    exemplo = " Histórico com semanas de EXEMPLO (fictício, rotulado) + snapshots reais." if d.get("exemplo") else ""
    detalhe = ('<div class="grade bloco">'
               + card("Narrativa", f'<p>{_e(d.get("narrativa", ""))}</p>', "O LLM só costura frases com números calculados no código.", largo=True)
               + card("Sinais antecipados", alertas(sinais), largo=True)
               + card("Projeções", f'<div class="tab"><table><tr><th>Métrica</th><th>Último</th><th>Ritmo/semana</th>'
                      f'<th>Status</th><th>Projeção</th></tr>{tab}</table></div>', largo=True)
               + "</div>")
    return pagina(titulo="Tendências", ativo="tendencias", uid=uid, chip="Tendências · estratégia",
                  h1="Para onde os números estão indo",
                  sub=f"{d['pontos']} semanas de {_e(d['semanas'][0] if d['semanas'] else '')} a "
                      f"{_e(d['semanas'][-1] if d['semanas'] else '')}; ritmo por regressão linear.{exemplo}",
                  filtros_html=filtros_html, kpis_html=chips + kpis, corpo_html=graficos + detalhe,
                  url_limpar=Url("/tendencias", {"usuario": uid}, {})(),
                  rodape="workflow painel_tendencias · acesso: estratégia, diretoria e admin.")
