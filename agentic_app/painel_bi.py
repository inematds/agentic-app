"""Esqueleto comum dos quatro painéis (Agentes, Negócio, Executivo, Tendências).

Layout de BI "visão geral → detalhe": navegação única no topo, filtros na lateral (viram um bloco recolhível
no celular), cartões de número, gráficos e, embaixo, o detalhe com as ações. Filtro é parâmetro de URL (GET):
o servidor recalcula e cada clique num gráfico é um link que acrescenta o filtro. Sem biblioteca, sem CDN.
"""
import html
from urllib.parse import urlencode

PAINEIS = [("agentes", "/comando", "Agentes", "Control Tower"),
           ("negocio", "/comando/negocio", "Negócio", "Mission Control"),
           ("executivo", "/executivo", "Executivo", "diretoria"),
           ("tendencias", "/tendencias", "Tendências", "estratégia")]


def _e(x):
    return html.escape(str(x if x is not None else ""))


class Url:
    """Monta links preservando usuário, `agora` e os filtros atuais."""

    def __init__(self, base, fixos: dict, filtros: dict):
        self.base, self.fixos, self.filtros = base, {k: v for k, v in fixos.items() if v}, dict(filtros)

    def __call__(self, **mudar):
        q = {**self.filtros, **mudar}
        q = {**self.fixos, **{k: v for k, v in q.items() if v}}
        return self.base + ("?" + urlencode(q) if q else "")

    def alternar(self, chave, valor):
        """Clicar de novo no que já está filtrado tira o filtro."""
        return self(**{chave: "" if self.filtros.get(chave) == valor else valor})


def kpi(rotulo, valor, sub="", tom=None, href=None, delta=None):
    cor = {"ok": "var(--ok)", "atencao": "var(--warn)", "critico": "var(--bad)"}.get(tom)
    icone = {"ok": "●", "atencao": "▲", "critico": "■"}.get(tom, "")
    d = ""
    if delta is not None:
        d = f'<small class="delta">{_e(delta)}</small>'
    tag = f'<span class="tom" style="color:{cor}">{icone}</span> ' if cor else ""
    corpo = (f'<span class="rot">{tag}{_e(rotulo)}</span><b>{valor}</b>'
             f'<small>{sub}</small>{d}')
    if href:
        return f'<a class="kpi link" href="{_e(href)}">{corpo}</a>'
    return f'<div class="kpi">{corpo}</div>'


def card(titulo, conteudo, sub="", largo=False, id_=""):
    i = f' id="{_e(id_)}"' if id_ else ""
    return (f'<section class="card{" largo" if largo else ""}"{i}><h2>{_e(titulo)}</h2>'
            f'{f"<p class=sub>{sub}</p>" if sub else ""}{conteudo}</section>')


def select(nome, rotulo, opcoes, atual):
    ops = "".join(f'<option value="{_e(v)}"{" selected" if v == atual else ""}>{_e(r)}</option>' for v, r in opcoes)
    return f'<label>{_e(rotulo)}<select name="{_e(nome)}">{ops}</select></label>'


def alertas(lista, cores=None):
    cor = {"critico": "var(--bad)", "atencao": "var(--warn)", "ok": "var(--ok)"}
    rot = {"critico": "crítico", "atencao": "atenção", "ok": "ok"}
    if not lista:
        return '<p class="mut">Nada pedindo atenção.</p>'
    return '<ul class="alertas">' + "".join(
        f'<li><span class="tag" style="border-color:{cor[a["nivel"]]};color:{cor[a["nivel"]]}">{rot[a["nivel"]]}</span> '
        f'{_e(a["texto"])}</li>' for a in lista) + "</ul>"


def ativos(url: Url, rotulos: dict):
    """Chips dos filtros ativos, cada um com link para tirar."""
    chips = [f'<a class="chipf" href="{_e(url(**{k: ""}))}" title="tirar filtro">{_e(rotulos.get(k, k))}: '
             f'{_e(v)} ✕</a>' for k, v in url.filtros.items() if v and k in rotulos]
    return f'<div class="chips">{"".join(chips)}</div>' if chips else ""


CSS = """
:root{--bg:#0c0c10;--bg2:#14141b;--card:#16161e;--line:#272730;--txt:#e9e9ee;--mut:#9a9aa6;--amb:#FACC15;
--ok:#4ade80;--warn:#f59e0b;--bad:#f87171;--on:#1a1206;--fill:#FACC15}
@media (prefers-color-scheme: light){:root{--bg:#f6f7f9;--bg2:#eceef2;--card:#fff;--line:#e1e3ea;--txt:#1a1a22;
--mut:#5b5b68;--amb:#a16207;--ok:#15803d;--warn:#b45309;--bad:#b91c1c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 Inter,system-ui,sans-serif}
a{color:inherit}
header.topo{position:sticky;top:0;z-index:3;background:var(--bg2);border-bottom:1px solid var(--line);padding:8px 16px;
display:flex;gap:10px;align-items:center;flex-wrap:wrap}
header.topo b.marca{font-family:Sora,system-ui;color:var(--amb)}
nav.paineis{display:flex;gap:6px;flex-wrap:wrap}
nav.paineis a{font:700 .85rem Sora,system-ui;text-decoration:none;border:1px solid var(--line);border-radius:10px;padding:.45em .8em}
nav.paineis a small{font-weight:500;color:var(--mut);margin-left:4px}
nav.paineis a[aria-current=page]{background:var(--fill);color:var(--on);border-color:var(--fill)}
nav.paineis a[aria-current=page] small{color:var(--on)}
.mut{color:var(--mut)} small{color:var(--mut)}
.layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:16px;max-width:1360px;margin:0 auto;padding:16px}
aside.filtros{position:sticky;top:64px;align-self:start;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
aside.filtros h2{font:700 .95rem Sora,system-ui;margin:0 0 8px}
aside.filtros label{display:block;font-size:.8rem;color:var(--mut);margin:10px 0 0}
aside.filtros select{display:block;width:100%;margin-top:4px;font:inherit;font-size:.9rem;color:var(--txt);background:var(--bg);
border:1px solid var(--line);border-radius:10px;padding:.4em .5em}
aside.filtros .limpar{display:inline-block;margin-top:12px;font-size:.85rem}
aside.filtros details summary{display:none}
main.conteudo{min-width:0}
h1{font-family:Sora,system-ui,sans-serif;margin:.1em 0;font-size:clamp(1.3rem,2.6vw,1.8rem)}
h2{font-family:Sora,system-ui,sans-serif;font-size:1rem;margin:0 0 6px}
.chip{color:var(--amb);font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;font-weight:700}
.sub{color:var(--mut);font-size:.84rem;margin:0 0 10px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.chipf{font-size:.8rem;border:1px solid var(--amb);border-radius:999px;padding:2px 10px;text-decoration:none}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:10px;margin:12px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;display:flex;flex-direction:column;
gap:2px;text-decoration:none;min-width:0}
.kpi.link:hover{border-color:var(--amb)}
.kpi .rot{font-size:.8rem;color:var(--mut)} .kpi b{font:800 1.6rem/1.15 Sora,system-ui;color:var(--txt)}
.kpi b small{font:600 .9rem Inter,system-ui} .kpi .delta{font-size:.78rem}
.grade{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;min-width:0}
.largo{grid-column:1/-1}
.bloco{margin-top:12px}
.sv{font:12px Inter,system-ui,sans-serif;fill:var(--txt)} .sv.b{font-weight:700} .sv.mut{fill:var(--mut)}
.sv.grande{font:800 24px Sora,system-ui;fill:var(--txt)}
a.alvo{cursor:pointer} a.alvo:hover path,a.alvo:hover rect:not([fill=transparent]){opacity:.85}
.leg{display:flex;gap:12px;flex-wrap:wrap;font-size:.8rem;color:var(--mut);margin:6px 0 0}
.leg i,.rosca i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.rosca{display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.rosca ul{list-style:none;margin:0;padding:0;flex:1;min-width:150px}
.rosca li{padding:3px 0;border-bottom:1px solid var(--line);font-size:.86rem}
.rosca li a,.rosca li{display:flex;gap:6px;align-items:center;text-decoration:none}
.rosca li span{flex:1} .rosca li small{width:3em;text-align:right}
button{font:600 .82rem Sora,system-ui;border-radius:10px;border:1px solid var(--line);background:transparent;
color:var(--txt);padding:.4em .75em;cursor:pointer}
button.pri{background:var(--fill);color:var(--on);border-color:var(--fill)}
button:disabled{opacity:.45;cursor:not-allowed}
.row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.tag{border:1px solid;border-radius:999px;padding:1px 9px;font-size:.74rem;white-space:nowrap;font-weight:600}
.luz{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}
.tab{overflow-x:auto} table{width:100%;border-collapse:collapse;min-width:560px}
td,th{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left;font-size:.86rem;vertical-align:top}
th{color:var(--mut);font-weight:600} code{font-family:"JetBrains Mono",monospace;font-size:.78rem}
.alertas,.feed{list-style:none;margin:0;padding:0} .alertas li,.feed li{padding:6px 0;border-bottom:1px solid var(--line)}
.alertas li:last-child,.feed li:last-child{border:none}
#msg{min-height:1.3em;font-size:.86rem;margin:4px 0} #msg.err{color:var(--bad)}
input.motivo{font:inherit;color:var(--txt);background:var(--bg);border:1px solid var(--line);border-radius:10px;
padding:.4em .6em;width:100%;margin-top:4px}
footer{color:var(--mut);font-size:.8rem;margin:18px 0 8px}
@media (max-width:860px){.layout{grid-template-columns:1fr;padding:12px}
aside.filtros{position:static} aside.filtros details summary{display:block;font:700 .95rem Sora,system-ui;cursor:pointer}
aside.filtros details:not([open]) .campos{display:none} aside.filtros h2{display:none}
.grade{grid-template-columns:1fr}
.card{overflow-x:auto} .card svg[viewBox^="0 0 1000"]{min-width:760px} .card svg[viewBox^="0 0 640"]{min-width:560px}}
"""

JS = """
const q = new URLSearchParams(location.search), uid = q.get("usuario") || "__UID__";
document.querySelectorAll("aside.filtros select").forEach(s => s.onchange = () => s.form.submit());
const ROTAS = {pausar: a => `/api/comando/pausar/${a}`, retomar: a => `/api/comando/retomar/${a}`,
  rodar: a => `/api/comando/rodar/${a}`, reexecutar: a => `/api/comando/reexecutar/${a}`,
  escalar: a => `/api/comando/escalar/${a}`, acionar: a => `/api/workflow/${a}`,
  aprovar: a => `/api/acoes/${a}/aprovar`, rejeitar: a => `/api/acoes/${a}/rejeitar`};
function msg(t, erro) { const m = document.getElementById("msg"); if (!m) return; m.textContent = t; m.className = erro ? "err" : ""; }
document.querySelectorAll("button[data-acao]").forEach(b => b.onclick = async () => {
  const acao = b.dataset.acao, alvo = b.dataset.alvo, mot = document.getElementById("motivo");
  const motivo = mot ? mot.value : "";
  const corpo = acao === "acionar" ? {entrada: JSON.parse(b.dataset.entrada || "{}")}
              : acao === "aprovar" ? {edicoes: {}} : {motivo};
  b.disabled = true; msg("Executando " + acao + "…");
  try {
    const r = await fetch(ROTAS[acao](encodeURIComponent(alvo)), {method: "POST",
      headers: {"content-type": "application/json", "X-Usuario": uid}, body: JSON.stringify(corpo)});
    const j = await r.json();
    if (!r.ok) throw new Error(j.erro || r.status);
    msg("Feito: " + acao + " " + alvo + (j.run_id ? " · run " + j.run_id : "") + ". Atualizando…");
    setTimeout(() => location.reload(), 600);
  } catch (e) { msg("Não deu: " + e.message, true); b.disabled = false; }
});
const vivo = document.getElementById("vivo");
if (vivo) {
  try { vivo.checked = localStorage.getItem("agentic-vivo") === "1"; } catch (e) {}
  vivo.onchange = () => { try { localStorage.setItem("agentic-vivo", vivo.checked ? "1" : "0"); } catch (e) {} };
  setInterval(() => { if (vivo.checked && !document.hidden) location.reload(); }, 30000);
}
"""


def pagina(*, titulo, ativo, uid, chip, h1, sub, filtros_html, kpis_html, corpo_html, url_limpar, agora="",
           rodape="", ao_vivo=False, extra_filtros=""):
    q = {"usuario": uid, **({"agora": agora} if agora else {})}
    nav = "".join(
        f'<a href="{_e(base + "?" + urlencode(q))}"{" aria-current=page" if k == ativo else ""}>{_e(r)}'
        f'<small>{_e(s)}</small></a>' for k, base, r, s in PAINEIS)
    ocultos = "".join(f'<input type="hidden" name="{k}" value="{_e(v)}">' for k, v in q.items())
    vivo = '<label class="mut"><input type="checkbox" id="vivo"> ao vivo (30 s)</label>' if ao_vivo else ""
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(titulo)}</title><style>{CSS}</style></head><body>
<header class="topo"><b class="marca">agentic-app</b><nav class="paineis" aria-label="Painéis">{nav}</nav>
<span style="flex:1"></span><span class="mut" style="font-size:.82rem">entrou como <code>{_e(uid)}</code> · dados fictícios</span>
{vivo}<a href="/" class="mut" style="font-size:.82rem">painel do app</a></header>
<div class="layout">
<aside class="filtros"><form method="get"><details open><summary>Filtros</summary><h2>Filtros</h2><div class="campos">
{ocultos}{filtros_html}{extra_filtros}
<a class="limpar mut" href="{_e(url_limpar)}">Limpar filtros</a></div></details></form></aside>
<main class="conteudo">
<div class="chip">{_e(chip)}</div><h1>{_e(h1)}</h1><p class="sub">{sub}</p>
{kpis_html}
{corpo_html}
<footer>{rodape}</footer>
</main></div>
<script>{JS.replace("__UID__", _e(uid))}</script></body></html>
"""
