"""Página do Centro de Comando: duas abas (Agentes = Agent Control Tower, Negócio = Mission Control).

HTML único, CSS e JS inline, sem dependência. Os botões chamam as rotas POST de serve.py com o
cabeçalho X-Usuario; o servidor decide (RBAC) e tudo fica no audit. Botão sem permissão aparece
desabilitado com o motivo, e mesmo assim o servidor confere de novo.
"""
import html
import json

SEM_COR = {"verde": "var(--ok)", "amarelo": "var(--warn)", "vermelho": "var(--bad)",
           "pausado": "var(--mut)", "sem_execucao": "var(--line)"}
SEM_ROT = {"verde": "ok", "amarelo": "atenção", "vermelho": "falha", "pausado": "pausado",
           "sem_execucao": "sem execução"}
NIVEL_COR = {"critico": "var(--bad)", "atencao": "var(--warn)", "ok": "var(--ok)"}
NIVEL_ROT = {"critico": "crítico", "atencao": "atenção", "ok": "ok"}
SIT_ROT = {"sem_acao": "nenhuma ação", "rejeitado": "rascunho rejeitado", "rascunho_pendente": "rascunho esperando",
           "enviado": "e-mail enviado"}
SIT_COR = {"sem_acao": "var(--bad)", "rejeitado": "var(--warn)", "rascunho_pendente": "var(--warn)",
           "enviado": "var(--ok)"}
STATUS_ROT = {"atrasado": "meta vencida", "atencao": "atenção", "em_dia": "em dia"}


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _f(v):
    return f"{v:g}" if isinstance(v, float) else str(v)


def _tag(cor, texto):
    return f'<span class="tag" style="border-color:{cor};color:{cor}">{_e(texto)}</span>'


def _bt(rotulo, acao, alvo, pode, motivo="", pri=False, extra=""):
    """Botão de ação. Sem permissão: desabilitado, com o motivo no title."""
    dis = "" if pode else f' disabled title="{_e(motivo)}"'
    return (f'<button class="{"pri" if pri else ""}" data-acao="{_e(acao)}" data-alvo="{_e(alvo)}"{extra}{dis}>'
            f'{_e(rotulo)}</button>')


def _alertas(lista):
    if not lista:
        return '<p class="mut">Nada pedindo atenção.</p>'
    return '<ul class="alertas">' + "".join(
        f'<li>{_tag(NIVEL_COR[a["nivel"]], NIVEL_ROT[a["nivel"]])} {_e(a["texto"])}</li>' for a in lista) + "</ul>"


def _hora(ts):
    return _e((ts or "")[5:16].replace("T", " "))


def _aba_agentes(d):
    t, pode = d["agentes"], d["pode"]
    ctl, c = t["controle"], t["custo"]
    sem_ctl = "só operação e admin controlam agentes"
    linhas = []
    for w in t["workflows"]:
        u = w["ultima"]
        ult = (f'{_hora(u["ts"])} · {_e(u["status"])}<br><small>{_e(u["gatilho"])} · {_e(u["usuario"])}</small>'
               if u else '<small>nunca rodou</small>')
        if w["estado"] == "pausado":
            p = w["pausa"] or {}
            ult += f'<br><small>pausado por {_e(p.get("por"))}{": " + _e(p["motivo"]) if p.get("motivo") else ""}</small>'
        botoes = []
        if not w["leitura"]:
            if w["estado"] == "ativo":
                botoes.append(_bt("Pausar", "pausar", w["id"], pode["controlar"], sem_ctl))
            else:
                botoes.append(_bt("Retomar", "retomar", w["id"], pode["controlar"], sem_ctl, pri=True))
            if w["proximo"]:
                botoes.append(_bt("Rodar agora", "rodar", w["id"], w["pode_rodar_agora"],
                                  sem_ctl if not pode["controlar"] else "retome antes de rodar"))
            rx = w["reexecutar"]
            if rx:
                ok = rx["pode"] and pode["controlar"] and w["estado"] == "ativo"
                motivo = rx["motivo"] or (sem_ctl if not pode["controlar"] else "retome antes de reexecutar")
                botoes.append(_bt("Reexecutar última", "reexecutar", rx["run_id"], ok, motivo))
        cor = SEM_COR[w["semaforo"]]
        bloq = f" · {w['bloqueados']} bloqueado" if w["bloqueados"] else ""
        linhas.append(
            f'<tr><td><span class="luz" style="background:{cor}"></span>{_tag(cor, SEM_ROT[w["semaforo"]])}</td>'
            f'<td><b>{_e(w["titulo"])}</b><br><code>{_e(w["id"])}</code>{" <small>· leitura</small>" if w["leitura"] else ""}</td>'
            f'<td>{w["ok"]} ok · {w["erros"]} erro · {w["negados"]} negado'
            f'{bloq}</td>'
            f'<td>{ult}</td><td>{_e(w["proximo"] or "—")}</td>'
            f'<td><div class="row">{"".join(botoes) or "<small>só leitura</small>"}</div></td></tr>')
    fila = "".join(
        f'<tr><td><code>{_e(x["id"])}</code><br><small>{_e(x["workflow"])}</small></td><td>{_e(x["para"])}</td>'
        f'<td>{_tag("var(--bad)" if x["vencida"] else "var(--mut)", _f(x["idade_h"]) + " h")}'
        f'{" " + _tag("var(--bad)", "fora do SLA") if x["vencida"] else ""}</td>'
        f'<td>{_tag("var(--warn)", "escalada por " + x["escalada_info"]["por"]) if x["escalada"] else ""}'
        f'{"" if x["escalada"] else _bt("Escalar", "escalar", x["id"], pode["controlar"], sem_ctl)}</td></tr>'
        for x in t["fila"]) or '<tr><td colspan="4" class="mut">Fila vazia.</td></tr>'
    probs = "".join(
        f'<tr><td>{_hora(p["ts"])}</td><td><code>{_e(p["workflow"])}</code><br><small>{_e(p["run_id"] or "")}</small></td>'
        f'<td>{_tag(SEM_COR["vermelho"] if p["tipo"] == "erro" else SEM_COR["amarelo"], p["tipo"])}'
        f'<br><small>{_e(p["detalhe"][:120])}</small></td>'
        f'<td>{_bt("Reexecutar", "reexecutar", p["run_id"], p["reexecutar"]["pode"] and pode["controlar"], p["reexecutar"]["motivo"] or sem_ctl) if p["run_id"] else ""}</td></tr>'
        for p in t["problemas"]) or '<tr><td colspan="4" class="mut">Nenhuma falha, bloqueio ou acesso negado.</td></tr>'
    feed = "".join(f'<li><small>{_hora(e["ts"])}</small> {_e(e["texto"])}</li>' for e in t["eventos"]) \
        or '<li class="mut">Sem eventos ainda.</li>'
    integra = ctl["corrente_integra"]
    return f"""
<section class="card largo"><h2>Alertas de operação</h2>{_alertas(d['alertas'])}</section>
<section class="card largo"><h2>Agentes e workflows</h2>
<p class="sub">Semáforo pela última execução, falhas e aprovações fora do SLA. Pausado = disparo fica no audit e não roda.</p>
<div class="tab"><table><tr><th>Estado</th><th>Workflow</th><th>Execuções</th><th>Última</th><th>Próximo disparo</th><th>Ações</th></tr>
{''.join(linhas)}</table></div></section>
<section class="card largo"><h2>Fila de aprovação (por idade)</h2>
<p class="sub">SLA {_f(t['sla_horas'])} h. Escalar avisa quem aprova; operação nunca aprova nem envia.</p>
<div class="tab"><table><tr><th>Ação</th><th>Para</th><th>Idade</th><th></th></tr>{fila}</table></div></section>
<section class="card largo"><h2>Falhas, bloqueios e negados</h2>
<div class="tab"><table><tr><th>Quando</th><th>Workflow</th><th>O quê</th><th></th></tr>{probs}</table></div></section>
<section class="card"><h2>Controle</h2>
<div class="num"><div><b style="color:{'var(--ok)' if integra else 'var(--bad)'}">{'ÍNTEGRA' if integra else 'QUEBRADA'}</b>
<span>corrente do audit ({ctl['linhas_audit']} linhas)</span></div>
<div><b style="color:{'var(--ok)' if ctl['pct_com_aprovacao'] >= 100 else 'var(--bad)'}">{_f(ctl['pct_com_aprovacao'])}%</b>
<span>ações externas com aprovação</span></div>
<div><b>{ctl['negados']}</b><span>acessos negados</span></div>
<div><b>{c['chamadas']}</b><span>chamadas de LLM · {_e(c['moeda'])} {c['custo_total']:.2f}</span></div></div></section>
<section class="card"><h2>Últimos eventos</h2><ul class="feed">{feed}</ul></section>"""


def _aba_negocio(d):
    n, pode = d["negocio"], d["pode"]
    prin = next(m for m in n["metricas"] if m["id"] == n["principal"])
    outras = [m for m in n["metricas"] if m is not prin]
    tiles = "".join(
        f'<div class="kpi"><span>{_e(m["nome"])}</span><b>{_f(m["valor"])}<small> {_e(m["unidade"])}</small></b>'
        f'<em>meta {"≥" if m["sentido"] == "maior" else "≤"} {_f(m["meta"])} · '
        f'{_tag("var(--ok)", "na meta") if m["atingiu"] else _tag("var(--bad)", "fora da meta")}</em></div>'
        for m in outras)
    pct = max(0.0, min(100.0, float(prin["valor"])))
    meta = max(0.0, min(100.0, float(prin["meta"])))
    barra = (f'<svg viewBox="0 0 400 30" width="100%" role="img" aria-label="{_f(prin["valor"])} de meta {_f(prin["meta"])}">'
             f'<rect x="0" y="8" width="400" height="14" rx="7" fill="var(--line)"/>'
             f'<rect x="0" y="8" width="{4 * pct:.0f}" height="14" rx="7" fill="var(--amb)"/>'
             f'<line x1="{4 * meta:.0f}" x2="{4 * meta:.0f}" y1="2" y2="28" stroke="var(--txt)" stroke-width="2"/></svg>')
    sem_ap = "só quem aprova (gestor, RH) decide rascunhos"
    dec = []
    for x in n["decisoes"]:
        p = x["proxima"]
        if p["tipo"] == "acionar":
            ok = pode["acionar"].get(p["workflow"], False)
            bt = _bt(p["rotulo"], "acionar", p["workflow"], ok, f"seu papel não executa {p['workflow']}", pri=True,
                     extra=f" data-entrada='{_e(json.dumps(p['entrada'], ensure_ascii=False))}'")
        elif p["tipo"] == "aprovar":
            bt = (_bt("Aprovar", "aprovar", p["acao_id"], pode["aprovar"], sem_ap, pri=True)
                  + _bt("Rejeitar", "rejeitar", p["acao_id"], pode["aprovar"], sem_ap))
        else:
            bt = f'<small>{_e(p["rotulo"])}</small>'
        dec.append(
            f'<tr><td><b>{_e(x["nome"])}</b><br>{_tag("var(--bad)" if x["status"] == "atrasado" else "var(--warn)", STATUS_ROT[x["status"]])}</td>'
            f'<td><small>{_e("; ".join(x["motivos"]))}</small></td>'
            f'<td>{_tag(SIT_COR[x["situacao"]], SIT_ROT[x["situacao"]])}</td><td><div class="row">{bt}</div></td></tr>')
    dec_html = "".join(dec) or '<tr><td colspan="4" class="mut">Ninguém em risco.</td></tr>'
    pend = "".join(
        f'<tr><td><code>{_e(x["id"])}</code></td><td>{_e(x["para"])}</td><td>{_f(x["idade_h"])} h</td>'
        f'<td><div class="row">{_bt("Aprovar", "aprovar", x["id"], pode["aprovar"], sem_ap, pri=True)}'
        f'{_bt("Rejeitar", "rejeitar", x["id"], pode["aprovar"], sem_ap)}</div></td></tr>'
        for x in n["pendentes"]) or '<tr><td colspan="4" class="mut">Nenhum rascunho esperando.</td></tr>'
    return f"""
<section class="card largo"><h2>Alertas de negócio</h2>{_alertas(n['alertas'])}</section>
<section class="card largo"><h2>Métrica do canvas</h2>
<div class="grade" style="margin-top:0"><div><span class="mut">{_e(prin['nome'])}</span>
<div class="grande">{_f(prin['valor'])}{_e(prin['unidade'])}</div>
<p>{_tag('var(--ok)', 'na meta') if prin['atingiu'] else _tag('var(--bad)', 'fora da meta')}
<small>meta {_f(prin['meta'])}{_e(prin['unidade'])} · {_e(prin.get('detalhe', ''))}</small></p>
<p><b>Faltam {n['faltam']}</b> <span class="mut">conversa(s) com meta vencida para bater a meta.</span></p></div>
<div>{barra}<p class="sub">Barra = valor atual · traço = meta.</p></div></div>
<div class="kpis">{tiles}</div></section>
<section class="card largo"><h2>Fila de decisão: quem precisa de ação</h2>
<p class="sub">Primeiro quem está sem nenhuma ação. Acionar roda o workflow com o SEU papel; o e-mail ainda passa por aprovação.</p>
<div class="tab"><table><tr><th>Pessoa</th><th>Por quê</th><th>Situação</th><th>Próxima ação</th></tr>{dec_html}</table></div></section>
<section class="card largo"><h2>Rascunhos esperando aprovação</h2>
<p class="sub">Aprovar aqui envia como está. Para editar o texto, use o painel principal.</p>
<div class="tab"><table><tr><th>Ação</th><th>Para</th><th>Idade</th><th></th></tr>{pend}</table></div></section>"""


def render_comando_html(d: dict, uid: str) -> str:
    cor = {"verde": "var(--ok)", "amarelo": "var(--warn)", "vermelho": "var(--bad)"}
    rot = {"verde": "tudo certo", "amarelo": "atenção", "vermelho": "ação urgente"}
    t, n = d["agentes"], d["negocio"]
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Centro de Comando</title>
<style>
:root{{--bg:#0c0c10;--bg2:#14141b;--card:#16161e;--line:#272730;--txt:#e9e9ee;--mut:#9a9aa6;--amb:#FACC15;
--ok:#4ade80;--warn:#f59e0b;--bad:#f87171;--on:#1a1206;--fill:#FACC15}}
@media (prefers-color-scheme: light){{:root{{--bg:#f6f7f9;--bg2:#eceef2;--card:#fff;--line:#e1e3ea;--txt:#1a1a22;
--mut:#5b5b68;--amb:#a16207;--ok:#15803d;--warn:#b45309;--bad:#b91c1c}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 Inter,system-ui,sans-serif}}
header{{position:sticky;top:0;z-index:2;background:var(--bg2);border-bottom:1px solid var(--line);padding:10px 16px;
display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
header b{{font-family:Sora,system-ui;color:var(--amb)}} .mut{{color:var(--mut)}} small{{color:var(--mut)}}
main{{max-width:1200px;margin:0 auto;padding:16px}}
h1{{font-family:Sora,system-ui,sans-serif;margin:.1em 0;font-size:clamp(1.4rem,3vw,2rem)}}
h2{{font-family:Sora,system-ui,sans-serif;font-size:1.05rem;margin:0 0 6px}}
.sub{{color:var(--mut);font-size:.85rem;margin:0 0 10px}}
.chip{{color:var(--amb);font-size:.75rem;letter-spacing:.14em;text-transform:uppercase;font-weight:700}}
.abas{{display:flex;gap:8px;margin:14px 0 4px;flex-wrap:wrap}}
.abas button{{font:700 .95rem Sora,system-ui;padding:.6em 1em}}
.abas button[aria-selected=true]{{background:var(--fill);color:var(--on);border-color:var(--fill)}}
.painel{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px;margin-top:14px}}
.painel[hidden]{{display:none}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;min-width:0}}
.largo{{grid-column:1/-1}}
.grade{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}}
button{{font:600 .85rem Sora,system-ui;border-radius:10px;border:1px solid var(--line);background:transparent;
color:var(--txt);padding:.45em .8em;cursor:pointer}}
button.pri{{background:var(--fill);color:var(--on);border-color:var(--fill)}}
button:disabled{{opacity:.45;cursor:not-allowed}}
.row{{display:flex;gap:6px;flex-wrap:wrap;align-items:center}}
.tag{{border:1px solid;border-radius:999px;padding:1px 9px;font-size:.75rem;white-space:nowrap;font-weight:600}}
.luz{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}}
.tab{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;min-width:560px}}
td,th{{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;font-size:.88rem;vertical-align:top}}
th{{color:var(--mut);font-weight:600}} code{{font-family:"JetBrains Mono",monospace;font-size:.8rem}}
.alertas,.feed{{list-style:none;margin:0;padding:0}} .alertas li,.feed li{{padding:6px 0;border-bottom:1px solid var(--line)}}
.alertas li:last-child,.feed li:last-child{{border:none}}
.grande{{font:800 2.6rem Sora,system-ui;color:var(--amb);line-height:1.1}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px}}
.kpi{{border:1px solid var(--line);border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:4px}}
.kpi span{{color:var(--mut);font-size:.85rem}} .kpi b{{font:800 1.5rem Sora,system-ui;color:var(--amb)}}
.kpi em{{font-style:normal;font-size:.82rem}}
.num{{display:flex;gap:18px;flex-wrap:wrap}} .num div b{{display:block;font:800 1.3rem Sora,system-ui}}
.num div span{{color:var(--mut);font-size:.8rem}}
.saude{{font:800 1rem Sora,system-ui}}
#msg{{min-height:1.3em;font-size:.88rem;margin-top:6px}} #msg.err{{color:var(--bad)}}
input.motivo{{font:inherit;color:var(--txt);background:var(--bg);border:1px solid var(--line);border-radius:10px;
padding:.4em .6em;min-width:220px;flex:1}}
@media (max-width:640px){{.painel{{grid-template-columns:1fr}}}}
</style></head><body>
<header><b>Centro de Comando</b><span class="mut">agentic-app · dados fictícios · entrou como <code>{_e(uid)}</code></span>
<span style="flex:1"></span>
<a href="/" style="color:var(--amb)">Painel do app</a>
<label class="mut"><input type="checkbox" id="vivo"> ao vivo (30 s)</label>
<button id="atualizar">Atualizar</button></header>
<main>
<div class="chip">Agent Control Tower · Mission Control</div>
<h1>O que está acontecendo agora, e o que falta para a meta</h1>
<p class="mut">Saúde geral: <span class="saude" style="color:{cor[d['saude']]}">{rot[d['saude']].upper()}</span>
· agentes {_tag(cor[t['saude']], rot[t['saude']])} · negócio {_tag(cor[n['saude']], rot[n['saude']])}
· gerado em {_e(d['gerado_em'][:16].replace('T', ' '))}. Cada consulta e cada ação ficam no audit log.</p>
<div class="row"><input class="motivo" id="motivo" placeholder="Motivo (opcional) para pausar, escalar ou rejeitar" aria-label="Motivo"></div>
<div id="msg" role="status"></div>
<div class="abas" role="tablist">
<button role="tab" id="t-agentes" aria-controls="p-agentes" aria-selected="true">Agentes · Control Tower</button>
<button role="tab" id="t-negocio" aria-controls="p-negocio" aria-selected="false">Negócio · Mission Control</button></div>
<div class="painel" id="p-agentes" role="tabpanel" aria-labelledby="t-agentes">{_aba_agentes(d)}</div>
<div class="painel" id="p-negocio" role="tabpanel" aria-labelledby="t-negocio" hidden>{_aba_negocio(d)}</div>
<p class="mut" style="font-size:.82rem;margin-top:18px">workflow <code>centro_comando</code> · ver: operação, admin, gestor,
diretoria · controlar agentes: operação e admin · aprovar: gestor e RH.</p>
</main>
<script>
const q = new URLSearchParams(location.search), uid = q.get("usuario") || "{_e(uid)}";
const ROTAS = {{pausar: a => `/api/comando/pausar/${{a}}`, retomar: a => `/api/comando/retomar/${{a}}`,
  rodar: a => `/api/comando/rodar/${{a}}`, reexecutar: a => `/api/comando/reexecutar/${{a}}`,
  escalar: a => `/api/comando/escalar/${{a}}`, acionar: a => `/api/workflow/${{a}}`,
  aprovar: a => `/api/acoes/${{a}}/aprovar`, rejeitar: a => `/api/acoes/${{a}}/rejeitar`}};
function aba(id) {{
  for (const n of ["agentes", "negocio"]) {{
    document.getElementById("p-" + n).hidden = n !== id;
    document.getElementById("t-" + n).setAttribute("aria-selected", n === id);
  }}
  history.replaceState(null, "", "#" + id);
}}
document.getElementById("t-agentes").onclick = () => aba("agentes");
document.getElementById("t-negocio").onclick = () => aba("negocio");
if (location.hash === "#negocio") aba("negocio");
function msg(t, erro) {{ const m = document.getElementById("msg"); m.textContent = t; m.className = erro ? "err" : ""; }}
document.querySelectorAll("button[data-acao]").forEach(b => b.onclick = async () => {{
  const acao = b.dataset.acao, alvo = b.dataset.alvo, motivo = document.getElementById("motivo").value;
  const corpo = acao === "acionar" ? {{entrada: JSON.parse(b.dataset.entrada || "{{}}")}}
              : acao === "aprovar" ? {{edicoes: {{}}}} : {{motivo}};
  b.disabled = true; msg("Executando " + acao + "…");
  try {{
    const r = await fetch(ROTAS[acao](encodeURIComponent(alvo)), {{method: "POST",
      headers: {{"content-type": "application/json", "X-Usuario": uid}}, body: JSON.stringify(corpo)}});
    const j = await r.json();
    if (!r.ok) throw new Error(j.erro || r.status);
    msg("Feito: " + acao + " " + alvo + (j.run_id ? " · run " + j.run_id : "") + ". Atualizando…");
    setTimeout(() => location.reload(), 600);
  }} catch (e) {{ msg("Não deu: " + e.message, true); b.disabled = false; }}
}});
document.getElementById("atualizar").onclick = () => location.reload();
const vivo = document.getElementById("vivo");
try {{ vivo.checked = localStorage.getItem("agentic-vivo") === "1"; }} catch (e) {{}}
vivo.onchange = () => {{ try {{ localStorage.setItem("agentic-vivo", vivo.checked ? "1" : "0"); }} catch (e) {{}} }};
setInterval(() => {{ if (vivo.checked && !document.hidden) location.reload(); }}, 30000);
</script></body></html>
"""
