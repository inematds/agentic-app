"""Páginas do Centro de Comando no layout de BI (painel_bi): Agentes (/comando) e Negócio (/comando/negocio).

Visão geral → detalhe: cartões, filtros na lateral, gráficos clicáveis (cada clique acrescenta um filtro) e, embaixo,
o detalhe com as ações. Os botões chamam as rotas POST de serve.py com o cabeçalho X-Usuario; o servidor decide
(RBAC) e tudo fica no audit. Botão sem permissão aparece desabilitado com o motivo, e o servidor confere de novo.
"""
import html
import json

from . import graficos as G
from . import visao as V
from .painel_bi import Url, alertas, ativos, card, kpi, pagina, select

SEM_COR = {"verde": "var(--ok)", "amarelo": "var(--warn)", "vermelho": "var(--bad)",
           "pausado": "var(--mut)", "sem_execucao": "var(--line)"}
SEM_ROT = {"verde": "ok", "amarelo": "atenção", "vermelho": "falha", "pausado": "pausado",
           "sem_execucao": "sem execução"}
SIT_COR = {"ok": "var(--ok)", "negado": "var(--warn)", "pausado": "var(--mut)", "falha": "var(--bad)"}
PES_COR = {"sem_acao": "var(--bad)", "rejeitado": "var(--warn)", "rascunho_pendente": "var(--mut)",
           "enviado": "var(--ok)"}
STATUS_ROT = {"atrasado": "meta vencida", "atencao": "atenção", "em_dia": "em dia"}
SAUDE_COR = {"verde": "var(--ok)", "amarelo": "var(--warn)", "vermelho": "var(--bad)"}
SAUDE_ROT = {"verde": "tudo certo", "amarelo": "atenção", "vermelho": "ação urgente"}
SEM_CTL = "só operação e admin controlam agentes"
SEM_AP = "só quem aprova (gestor, RH) decide rascunhos"


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _f(v):
    return G._f(v)


def _tag(cor, texto):
    return f'<span class="tag" style="border-color:{cor};color:{cor}">{_e(texto)}</span>'


def _bt(rotulo, acao, alvo, pode, motivo="", pri=False, extra=""):
    dis = "" if pode else f' disabled title="{_e(motivo)}"'
    return (f'<button class="{"pri" if pri else ""}" data-acao="{_e(acao)}" data-alvo="{_e(alvo)}"{extra}{dis}>'
            f'{_e(rotulo)}</button>')


def _hora(ts):
    return _e((ts or "")[5:16].replace("T", " "))


def _saude(d):
    t, n = d["agentes"], d["negocio"]
    return (f'Saúde geral: <b style="color:{SAUDE_COR[d["saude"]]}">{SAUDE_ROT[d["saude"]].upper()}</b> · agentes '
            f'{_tag(SAUDE_COR[t["saude"]], SAUDE_ROT[t["saude"]])} · negócio {_tag(SAUDE_COR[n["saude"]], SAUDE_ROT[n["saude"]])}'
            f' · gerado em {_e(d["gerado_em"][:16].replace("T", " "))}. Cada consulta e cada ação ficam no audit log.')


# ------------------------------------------------------------------ Agentes (Agent Control Tower)
def render_agentes_html(d: dict, uid: str, agora: str = "") -> str:
    t, pode = d["agentes"], d["pode"]
    v = t["visao"]
    f, k = v["filtros"], v["kpis"]
    url = Url("/comando", {"usuario": uid, "agora": agora}, f)
    wf_ids = [w["id"] for w in t["workflows"] if not w["leitura"]]

    var = k["variacao"]
    d_exec = f"{var['execucoes']:+d} vs período anterior" if var else None
    d_suc = f"{var['sucesso_pp']:+.1f} p.p. vs período anterior" if var else None
    kpis = '<div class="kpis">' + "".join([
        kpi("Execuções", _f(k["execucoes"]), v["periodo_rotulo"], delta=d_exec, href=url(situacao="")),
        kpi("Sucesso", f'{_f(k["sucesso"])}<small>%</small>', f'{k["ok"]} ok de {k["ok"] + k["falhas"] + k["negados"]}',
            tom="ok" if k["sucesso"] >= 95 else "atencao", delta=d_suc),
        kpi("Falhas", _f(k["falhas"]), "clique para ver", tom="critico" if k["falhas"] else "ok",
            href=url.alternar("situacao", "falha")),
        kpi("Negados e bloqueados", _f(k["negados"] + k["bloqueados"]), f'{k["negados"]} negados · {k["bloqueados"]} pausados',
            tom="atencao" if k["negados"] + k["bloqueados"] else None, href=url.alternar("situacao", "negado")),
        kpi("Fila de aprovação", _f(k["fila"]), f'{k["fora_sla"]} fora do SLA de {_f(t["sla_horas"])} h',
            tom="critico" if k["fora_sla"] else ("atencao" if k["fila"] else "ok"), href="#fila"),
        kpi("Até aprovar", f'{_f(k["mediana_aprovar_h"])}<small> h</small>',
            f'mediana de {k["aprovacoes_medidas"]} aprovação(ões)'),
        kpi("Chamadas de LLM", _f(k["chamadas_llm"]), f'{_e(k["moeda"])} {k["custo"]:.2f} no período'),
    ]) + "</div>"

    filtros = (select("periodo", "Período", [(c, r) for c, (r, _) in V.PERIODOS.items()], f["periodo"])
               + select("workflow", "Workflow", [("", "todos")] + [(w, w) for w in wf_ids], f["workflow"])
               + select("gatilho", "Gatilho", [("", "todos")] + list(V.GATILHOS.items()), f["gatilho"])
               + select("situacao", "Situação", [("", "todas")] + list(V.SITUACOES_EXEC.items()), f["situacao"])
               + (f'<input type="hidden" name="dia" value="{_e(f["dia"])}">' if f["dia"] else ""))
    chips = ativos(url, {"workflow": "workflow", "gatilho": "gatilho", "situacao": "situação", "dia": "dia"})

    dias = [x["dia"] for x in v["por_dia"]]
    passo = max(1, len(dias) // 8)
    g_dia = G.colunas(dias, G.STATUS_SERIES, {x["dia"]: x for x in v["por_dia"]}, largura=1000, altura=220,
                      href=lambda c: url.alternar("dia", c), destaque=f["dia"],
                      rotulos_x={c: f"{c[8:10]}/{c[5:7]}" for i, c in enumerate(dias) if i % passo == 0})
    horas = list(range(24))
    g_hora = G.colunas(horas, G.STATUS_SERIES, {x["hora"]: x for x in v["por_hora"]}, altura=200, largura=440,
                       rotulos_x={h: f"{h}h" for h in horas if h % 3 == 0})
    g_wf = G.barras([(w, w, c) for w, c in v["por_workflow"].items()], G.STATUS_SERIES,
                    href=lambda c: url.alternar("workflow", c), destaque=f["workflow"], largura_rot=150, largura=440)
    cor_g = {"clique": "var(--amb)", "horario": "var(--txt)", "evento": "var(--mut)", "comando": "var(--warn)"}
    g_gat = G.rosca([(c, r, v["por_gatilho"][c], cor_g[c]) for c, r in V.GATILHOS.items()],
                    href=lambda c: url.alternar("gatilho", c), centro="execuções", destaque=f["gatilho"])
    g_sit = G.rosca([(c, r, v["por_situacao"][c], SIT_COR[c]) for c, r in V.SITUACOES_EXEC.items()],
                    href=lambda c: url.alternar("situacao", c), centro="execuções", destaque=f["situacao"])
    fx = list(v["fila_idade"].items())
    g_fila = G.barras([(r, r, {"dentro" if i < 2 else "fora": n}) for i, (r, n) in enumerate(fx)],
                      [("dentro", "dentro do SLA", "var(--ok)"), ("fora", "fora do SLA", "var(--bad)")], largura_rot=80,
                      largura=440)
    ds = v["desfecho"]
    g_desf = G.rosca([("sem_edicao", "aprovado sem edição", ds["sem_edicao"], "var(--ok)"),
                      ("com_edicao", "aprovado com edição", ds["com_edicao"], "var(--amb)"),
                      ("pendente", "esperando", ds["pendente"], "var(--mut)"),
                      ("rejeitado", "rejeitado", ds["rejeitado"], "var(--bad)")], centro="rascunhos")

    graficos = ('<div class="grade bloco">'
                + card("Execuções por dia", g_dia, "Clique num dia para ver só ele. Cor = situação.", largo=True)
                + card("Por workflow", g_wf, "Clique para filtrar o workflow.")
                + card("Por hora do dia", g_hora, "Quando os agentes trabalham (no filtro atual).")
                + card("Por gatilho", g_gat, "Clique, horário, evento ou Centro de Comando.")
                + card("Situação", g_sit, "Clique para filtrar.")
                + card("Fila de aprovação por idade", g_fila, f"SLA de {_f(t['sla_horas'])} h.")
                + card("Desfecho dos rascunhos", g_desf, "Rascunhos propostos no período.")
                + "</div>")

    # ---- detalhe
    linhas = []
    for w in t["workflows"]:
        if f["workflow"] and w["id"] != f["workflow"]:
            continue
        u = w["ultima"]
        ult = (f'{_hora(u["ts"])} · {_e(u["status"])}<br><small>{_e(u["gatilho"])} · {_e(u["usuario"])}</small>'
               if u else '<small>nunca rodou</small>')
        if w["estado"] == "pausado":
            p = w["pausa"] or {}
            ult += f'<br><small>pausado por {_e(p.get("por"))}{": " + _e(p["motivo"]) if p.get("motivo") else ""}</small>'
        botoes = []
        if not w["leitura"]:
            botoes.append(_bt("Pausar", "pausar", w["id"], pode["controlar"], SEM_CTL) if w["estado"] == "ativo"
                          else _bt("Retomar", "retomar", w["id"], pode["controlar"], SEM_CTL, pri=True))
            if w["proximo"]:
                botoes.append(_bt("Rodar agora", "rodar", w["id"], w["pode_rodar_agora"],
                                  SEM_CTL if not pode["controlar"] else "retome antes de rodar"))
            rx = w["reexecutar"]
            if rx:
                ok = rx["pode"] and pode["controlar"] and w["estado"] == "ativo"
                botoes.append(_bt("Reexecutar última", "reexecutar", rx["run_id"], ok,
                                  rx["motivo"] or (SEM_CTL if not pode["controlar"] else "retome antes de reexecutar")))
        cor = SEM_COR[w["semaforo"]]
        bloq = f" · {w['bloqueados']} bloqueado" if w["bloqueados"] else ""
        linhas.append(
            f'<tr><td><span class="luz" style="background:{cor}"></span>{_tag(cor, SEM_ROT[w["semaforo"]])}</td>'
            f'<td><a href="{_e(url.alternar("workflow", w["id"]))}"><b>{_e(w["titulo"])}</b></a><br><code>{_e(w["id"])}</code>'
            f'{" <small>· leitura</small>" if w["leitura"] else ""}</td>'
            f'<td>{w["ok"]} ok · {w["erros"]} erro · {w["negados"]} negado{bloq}</td>'
            f'<td>{ult}</td><td>{_e(w["proximo"] or "—")}</td>'
            f'<td><div class="row">{"".join(botoes) or "<small>só leitura</small>"}</div></td></tr>')
    execs = "".join(
        f'<tr><td>{_hora(x["ts"])}</td><td><code>{_e(x["workflow"])}</code><br><small>{_e(x["run_id"])}</small></td>'
        f'<td>{_tag(SIT_COR[x["situacao"]], x["situacao"])}<br><small>{_e(x["erro"][:110])}</small></td>'
        f'<td><small>{_e(x["gatilho"])}<br>{_e(x["usuario"])}</small></td><td>'
        + (_bt("Reexecutar", "reexecutar", x["run_id"], x["reexecutar"]["pode"] and pode["controlar"],
               x["reexecutar"]["motivo"] or SEM_CTL) if x.get("reexecutar") else "")
        + "</td></tr>" for x in v["detalhe"]) or '<tr><td colspan="5" class="mut">Nenhuma execução no filtro.</td></tr>'
    fila = "".join(
        f'<tr><td><code>{_e(x["id"])}</code><br><small>{_e(x["workflow"])}</small></td><td>{_e(x["para"])}</td>'
        f'<td>{_tag("var(--bad)" if x["vencida"] else "var(--mut)", _f(x["idade_h"]) + " h")}'
        f'{" " + _tag("var(--bad)", "fora do SLA") if x["vencida"] else ""}</td>'
        f'<td>{_tag("var(--warn)", "escalada por " + x["escalada_info"]["por"]) if x["escalada"] else ""}'
        f'{"" if x["escalada"] else _bt("Escalar", "escalar", x["id"], pode["controlar"], SEM_CTL)}</td></tr>'
        for x in t["fila"] if not f["workflow"] or x["workflow"] == f["workflow"]) \
        or '<tr><td colspan="4" class="mut">Fila vazia.</td></tr>'
    feed = "".join(f'<li><small>{_hora(e["ts"])}</small> {_e(e["texto"])}</li>' for e in t["eventos"]
                   if not f["workflow"] or e.get("workflow") == f["workflow"]) or '<li class="mut">Sem eventos.</li>'
    ctl, c = t["controle"], t["custo"]
    integra = ctl["corrente_integra"]
    controle = (f'<div class="kpis" style="margin:0">'
                + kpi("Corrente do audit", "ÍNTEGRA" if integra else "QUEBRADA", f'{ctl["linhas_audit"]} linhas',
                      tom="ok" if integra else "critico")
                + kpi("Ações externas com aprovação", f'{_f(ctl["pct_com_aprovacao"])}<small>%</small>',
                      f'{ctl["acoes_com_aprovacao"]} de {ctl["acoes_externas"]}',
                      tom="ok" if ctl["pct_com_aprovacao"] >= 100 else "critico")
                + kpi("Custo total de LLM", f'{_e(c["moeda"])} {c["custo_total"]:.2f}', f'{c["chamadas"]} chamadas desde o início')
                + "</div>")
    detalhe = ('<div class="grade bloco">'
               + card("Alertas de operação", alertas(d["alertas"]), largo=True)
               + card("Agentes e workflows", f'<div class="tab"><table><tr><th>Estado</th><th>Workflow</th><th>Execuções</th>'
                      f'<th>Última</th><th>Próximo disparo</th><th>Ações</th></tr>{"".join(linhas)}</table></div>',
                      "Semáforo pela última execução, falhas e aprovações fora do SLA. Pausado = o disparo fica no audit e não roda.",
                      largo=True)
               + card("Execuções no filtro", f'<div class="tab"><table><tr><th>Quando</th><th>Workflow</th><th>Situação</th>'
                      f'<th>Gatilho / quem</th><th></th></tr>{execs}</table></div>',
                      f"As {len(v['detalhe'])} mais recentes do filtro. Reexecutar só refaz agendado ou entrada vazia.",
                      largo=True)
               + card("Fila de aprovação", f'<div class="tab"><table><tr><th>Ação</th><th>Para</th><th>Idade</th><th></th></tr>'
                      f'{fila}</table></div>', "Escalar avisa quem aprova; operação nunca aprova nem envia.", largo=True,
                      id_="fila")
               + card("Controle", controle)
               + card("Últimos eventos", f'<ul class="feed">{feed}</ul>')
               + "</div>")
    motivo = ('<label>Motivo (pausar, escalar)<input class="motivo" id="motivo" '
              'placeholder="opcional" form="nada"></label>')
    return pagina(titulo="Centro de Comando · Agentes", ativo="agentes", uid=uid, agora=agora,
                  chip="Centro de Comando · Agent Control Tower",
                  h1="O que os agentes estão fazendo agora", sub=_saude(d),
                  filtros_html=filtros, extra_filtros=motivo,
                  kpis_html=chips + kpis + '<div id="msg" role="status"></div>',
                  corpo_html=graficos + detalhe, url_limpar=Url("/comando", {"usuario": uid, "agora": agora}, {})(),
                  ao_vivo=True,
                  rodape="workflow centro_comando · ver: operação, admin, gestor, diretoria · controlar: operação e admin.")


# ------------------------------------------------------------------ Negócio (Mission Control)
def render_negocio_html(d: dict, uid: str, agora: str = "", filtros=None) -> str:
    n, pode = d["negocio"], d["pode"]
    f = V.normalizar_negocio(filtros)
    url = Url("/comando/negocio", {"usuario": uid, "agora": agora}, f)
    todas = n["decisoes"]
    lista = V.filtrar_decisoes(todas, f)
    prin = next(m for m in n["metricas"] if m["id"] == n["principal"])
    outras = [m for m in n["metricas"] if m is not prin]
    sem_acao = sum(1 for x in todas if x["situacao"] == "sem_acao")
    kpis = '<div class="kpis">' + "".join(
        [kpi(prin["nome"], f'{_f(prin["valor"])}<small>{_e(prin["unidade"])}</small>',
             f'meta {_f(prin["meta"])}{_e(prin["unidade"])} · {_e(prin.get("detalhe", ""))}',
             tom="ok" if prin["atingiu"] else "critico"),
         kpi("Faltam para a meta", _f(n["faltam"]), "conversas com meta vencida", tom="ok" if not n["faltam"] else "atencao"),
         kpi("Sem nenhuma ação", _f(sem_acao), "pessoas em risco", tom="critico" if sem_acao else "ok",
             href=url.alternar("situacao", "sem_acao")),
         kpi("Rascunhos esperando", _f(len(n["pendentes"])), "aprovação humana", tom="atencao" if n["pendentes"] else "ok",
             href="#rascunhos")]
        + [kpi(m["nome"], f'{_f(m["valor"])}<small> {_e(m["unidade"])}</small>',
               f'meta {"≥" if m["sentido"] == "maior" else "≤"} {_f(m["meta"])}', tom="ok" if m["atingiu"] else "atencao")
           for m in outras]) + "</div>"
    filtros_html = (select("situacao", "Situação", [("", "todas")] + list(V.SITUACOES_PESSOA.items()), f["situacao"])
                    + select("status", "Risco", [("", "todos")] + list(V.STATUS_PESSOA.items()), f["status"])
                    + select("motivo", "Motivo", [("", "todos")] + list(V.MOTIVOS.items()), f["motivo"]))
    chips = ativos(url, {"situacao": "situação", "status": "risco", "motivo": "motivo"})

    h = n["historico"]
    serie = [x for x in h["serie"]]
    g_hist = G.linha([f"{s[8:10]}/{s[5:7]}" for s in h["semanas"]], [(prin["nome"], serie, "var(--amb)", False)],
                     meta=(prin["meta"], f"meta {_f(prin['meta'])}{prin['unidade']}"), unidade=prin["unidade"],
                     rotulos_x_cada=max(1, len(serie) // 6), largura=1000, altura=220)
    base_sit = V.filtrar_decisoes(todas, f, sem=("situacao",))
    g_sit = G.rosca([(c, r, sum(1 for x in base_sit if x["situacao"] == c), PES_COR[c]) for c, r in V.SITUACOES_PESSOA.items()],
                    href=lambda c: url.alternar("situacao", c), centro="pessoas", destaque=f["situacao"])
    base_mot = V.filtrar_decisoes(todas, f, sem=("motivo",))
    g_mot = G.barras([(c, r, sum(1 for x in base_mot if c in V.motivos_de(x))) for c, r in V.MOTIVOS.items()],
                     href=lambda c: url.alternar("motivo", c), destaque=f["motivo"], largura_rot=150, largura=440)
    em_risco = {x["id"] for x in lista}
    pessoas = sorted(n["pessoas"], key=lambda p: p["engajamento"])
    g_eng = G.barras([(p["id"], p["nome"].split()[0], {"risco" if p["id"] in em_risco else ("fora" if p["status"] != "em_dia" else "ok"):
                                                       p["engajamento"]}) for p in pessoas],
                     [("ok", "em dia", "var(--ok)"), ("fora", "em risco (fora do filtro)", "var(--mut)"),
                      ("risco", "em risco (no filtro)", "var(--bad)")], largura_rot=90, largura=1000)
    graficos = ('<div class="grade bloco">'
                + card(f"{prin['nome']} por semana", g_hist,
                       ("Histórico de EXEMPLO (fictício, rotulado) + snapshots reais de segunda 07:00. " if h["exemplo"] else "")
                       + "Traço = meta.", largo=True)
                + card("Pessoas em risco por situação", g_sit, "Clique para filtrar a fila de decisão.")
                + card("Motivos de risco", g_mot, "Uma pessoa pode ter mais de um motivo. Clique para filtrar.")
                + card("Engajamento por pessoa", g_eng, "Todas as pessoas da equipe, do menor para o maior.", largo=True)
                + "</div>")

    dec = []
    for x in lista:
        p = x["proxima"]
        if p["tipo"] == "acionar":
            bt = _bt(p["rotulo"], "acionar", p["workflow"], pode["acionar"].get(p["workflow"], False),
                     f"seu papel não executa {p['workflow']}", pri=True,
                     extra=f" data-entrada='{_e(json.dumps(p['entrada'], ensure_ascii=False))}'")
        elif p["tipo"] == "aprovar":
            bt = (_bt("Aprovar", "aprovar", p["acao_id"], pode["aprovar"], SEM_AP, pri=True)
                  + _bt("Rejeitar", "rejeitar", p["acao_id"], pode["aprovar"], SEM_AP))
        else:
            bt = f'<small>{_e(p["rotulo"])}</small>'
        dec.append(
            f'<tr><td><b>{_e(x["nome"])}</b><br>{_tag("var(--bad)" if x["status"] == "atrasado" else "var(--warn)", STATUS_ROT[x["status"]])}</td>'
            f'<td><small>{_e("; ".join(x["motivos"]))}</small></td>'
            f'<td>{_tag(PES_COR[x["situacao"]], V.SITUACOES_PESSOA[x["situacao"]])}</td><td><div class="row">{bt}</div></td></tr>')
    dec_html = "".join(dec) or '<tr><td colspan="4" class="mut">Ninguém no filtro.</td></tr>'
    pend = "".join(
        f'<tr><td><code>{_e(x["id"])}</code></td><td>{_e(x["para"])}</td><td>{_f(x["idade_h"])} h</td>'
        f'<td><div class="row">{_bt("Aprovar", "aprovar", x["id"], pode["aprovar"], SEM_AP, pri=True)}'
        f'{_bt("Rejeitar", "rejeitar", x["id"], pode["aprovar"], SEM_AP)}</div></td></tr>'
        for x in n["pendentes"]) or '<tr><td colspan="4" class="mut">Nenhum rascunho esperando.</td></tr>'
    detalhe = ('<div class="grade bloco">'
               + card("Alertas de negócio", alertas(n["alertas"]), largo=True)
               + card("Fila de decisão: quem precisa de ação",
                      f'<div class="tab"><table><tr><th>Pessoa</th><th>Por quê</th><th>Situação</th><th>Próxima ação</th></tr>'
                      f'{dec_html}</table></div>',
                      f"{len(lista)} de {len(todas)} pessoa(s). Primeiro quem está sem nenhuma ação. Acionar roda o workflow "
                      "com o SEU papel; o e-mail ainda passa por aprovação.", largo=True)
               + card("Rascunhos esperando aprovação",
                      f'<div class="tab"><table><tr><th>Ação</th><th>Para</th><th>Idade</th><th></th></tr>{pend}</table></div>',
                      "Aprovar aqui envia como está. Para editar o texto, use o painel do app.", largo=True, id_="rascunhos")
               + "</div>")
    motivo = '<label>Motivo (rejeitar)<input class="motivo" id="motivo" placeholder="opcional" form="nada"></label>'
    return pagina(titulo="Centro de Comando · Negócio", ativo="negocio", uid=uid, agora=agora,
                  chip="Centro de Comando · Mission Control", h1="O resultado do canvas, ao vivo, e quem precisa de ação",
                  sub=_saude(d), filtros_html=filtros_html, extra_filtros=motivo,
                  kpis_html=chips + kpis + '<div id="msg" role="status"></div>', corpo_html=graficos + detalhe,
                  url_limpar=Url("/comando/negocio", {"usuario": uid, "agora": agora}, {})(), ao_vivo=True,
                  rodape="workflow centro_comando · aprovar: gestor e RH · acionar: quem executa o workflow.")
