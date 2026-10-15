"""Pilar 9 — saída visual: relatório HTML (e PDF) em vez de parede de texto.

HTML: uma página só, CSS inline, barras em SVG, abre offline.
PDF: escritor mínimo (PDF 1.4, Helvetica, WinAnsi), sem dependência.
"""
import html
from pathlib import Path


def _e(x):
    return html.escape(str(x))


def _cor(status):
    return {"em_dia": "var(--ok)", "atencao": "var(--warn)", "atrasado": "var(--bad)"}[status]


ROTULO = {"em_dia": "em dia", "atencao": "atenção", "atrasado": "meta vencida"}


def render_html(d: dict) -> str:
    n = d["numeros"]
    kpis = [("Pessoas", n["total"]), ("Metas concluídas", f"{n['metas_concluidas']}/{n['metas_total']}"),
            ("Metas vencidas", n["metas_atrasadas"]), ("Engajamento médio", n["engajamento_medio"]),
            ("Sem 1:1 há +30 dias", n["pessoas_sem_1a1"])]
    tiles = "".join(f'<div class="kpi"><b>{_e(v)}</b><span>{_e(k)}</span></div>' for k, v in kpis)
    linhas = []
    for p in n["pessoas"]:
        w = max(2, int(p["progresso_medio"] * 2.4))
        linhas.append(
            f'<tr><td><b>{_e(p["nome"])}</b><br><small>{_e(p["cargo"])}</small></td>'
            f'<td style="white-space:nowrap"><svg width="250" height="16" role="img" aria-label="progresso {p["progresso_medio"]}%">'
            f'<rect width="240" height="12" y="2" rx="6" fill="var(--line)"/>'
            f'<rect width="{w}" height="12" y="2" rx="6" fill="{_cor(p["status"])}"/></svg> '
            f'{p["progresso_medio"]}%</td>'
            f'<td>{p["engajamento"]} <small>({p["tendencia"]:+d})</small></td>'
            f'<td>{p["dias_sem_1a1"]} dias</td>'
            f'<td><span class="tag" style="border-color:{_cor(p["status"])}">{ROTULO[p["status"]]}</span></td></tr>')
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(d['titulo'])} — {_e(d['data'])}</title>
<style>
:root{{--bg:#0c0c10;--card:#16161e;--line:#272730;--txt:#e9e9ee;--mut:#9a9aa6;--amb:#FACC15;
--ok:#4ade80;--warn:#f59e0b;--bad:#f87171}}
@media (prefers-color-scheme: light){{:root{{--bg:#f6f7f9;--card:#fff;--line:#e1e3ea;--txt:#1a1a22;--mut:#5b5b68;
--amb:#a16207;--ok:#15803d;--warn:#b45309;--bad:#b91c1c}}}}
@media print{{:root{{--bg:#fff;--card:#fff;--line:#ddd;--txt:#111;--mut:#555;--amb:#854d0e;--ok:#15803d;--warn:#b45309;--bad:#b91c1c}}}}
body{{margin:0;background:var(--bg);color:var(--txt);font:16px/1.55 Inter,system-ui,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:32px 16px}}
h1{{font-family:Sora,system-ui,sans-serif;margin:.2em 0}} .chip{{color:var(--amb);font-size:.75rem;letter-spacing:.14em;text-transform:uppercase;font-weight:700}}
.resumo{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;max-width:74ch}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}}
.kpi b{{display:block;font:800 1.8rem Sora,system-ui;color:var(--amb)}} .kpi span{{color:var(--mut);font-size:.9rem}}
.tabela{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;min-width:640px}}
td,th{{padding:10px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}
th{{color:var(--mut);font-weight:600;font-size:.85rem}} small{{color:var(--mut)}}
.tag{{border:1px solid;border-radius:999px;padding:2px 10px;font-size:.8rem;white-space:nowrap}}
footer{{color:var(--mut);font-size:.85rem;margin-top:24px}}
</style></head><body><main>
<div class="chip">Relatório gerado por workflow · {_e(d['data'])}</div>
<h1>{_e(d['titulo'])}</h1>
<p><small>Gestora: {_e(d['gestor'])}</small></p>
<p class="resumo">{_e(d['resumo'])}</p>
<div class="kpis">{tiles}</div>
<div class="tabela"><table><thead><tr><th>Pessoa</th><th>Progresso nas metas</th><th>Engajamento (variação 4 sem.)</th>
<th>Desde o último 1:1</th><th>Situação</th></tr></thead><tbody>{''.join(linhas)}</tbody></table></div>
<footer>Dados fictícios · agentic-app · workflow relatorio_equipe · cada execução registrada no audit log.</footer>
</main></body></html>
"""


def _pdf_texto(s):
    s = str(s).encode("cp1252", "replace").decode("cp1252")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_pdf(d: dict) -> bytes:
    """PDF A4 de uma página com KPIs e uma barra por pessoa."""
    n = d["numeros"]
    cmds = []

    def txt(x, y, s, tam=10, negrito=False):
        cmds.append(f"BT /{'F2' if negrito else 'F1'} {tam} Tf {x} {y} Td ({_pdf_texto(s)}) Tj ET")

    txt(40, 800, d["titulo"], 18, True)
    txt(40, 782, f"{d['data']}  -  Gestora: {d['gestor']}", 10)
    y = 760
    palavras, linha = d["resumo"].split(), ""
    for w in palavras:
        if len(linha) + len(w) > 95:
            txt(40, y, linha, 10); y -= 14; linha = ""
        linha += w + " "
    txt(40, y, linha, 10); y -= 26
    txt(40, y, f"Pessoas: {n['total']}   Metas concluidas: {n['metas_concluidas']}/{n['metas_total']}   "
               f"Metas vencidas: {n['metas_atrasadas']}   Engajamento medio: {n['engajamento_medio']}", 10, True)
    y -= 28
    cores = {"em_dia": "0.08 0.5 0.24", "atencao": "0.7 0.33 0.04", "atrasado": "0.72 0.11 0.11"}
    for p in n["pessoas"]:
        txt(40, y, p["nome"], 10, True)
        cmds.append(f"0.88 0.89 0.92 rg 200 {y - 2} 240 10 re f")
        cmds.append(f"{cores[p['status']]} rg 200 {y - 2} {max(2, int(p['progresso_medio'] * 2.4))} 10 re f 0 0 0 rg")
        txt(450, y, f"{p['progresso_medio']}%  {ROTULO[p['status']]}", 9)
        y -= 22
    txt(40, 40, "Dados ficticios - agentic-app - workflow relatorio_equipe", 8)
    return _montar_pdf(cmds)


def _montar_pdf(cmds) -> bytes:
    """PDF 1.4 de uma página A4 a partir dos comandos de desenho."""
    fluxo = "\n".join(cmds).encode("cp1252", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length " + str(len(fluxo)).encode() + b" >>\nstream\n" + fluxo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    saida = bytearray(b"%PDF-1.4\n")
    pos = []
    for i, o in enumerate(objs, 1):
        pos.append(len(saida))
        saida += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(saida)
    saida += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for p in pos:
        saida += f"{p:010d} 00000 n \n".encode()
    saida += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(saida)


def gerar_artefatos(dados: dict, pasta: Path, art: dict) -> list:
    pasta = Path(pasta)
    (pasta / art["html"]).write_text(render_html(dados), encoding="utf-8")
    arquivos = [art["html"]]
    if art.get("pdf"):
        (pasta / art["pdf"]).write_bytes(render_pdf(dados))
        arquivos.append(art["pdf"])
    return arquivos


# ====================================================================== painel executivo
NIVEL_ROT = {"critico": "crítico", "atencao": "atenção", "ok": "ok"}
NIVEL_COR = {"critico": "var(--bad)", "atencao": "var(--warn)", "ok": "var(--ok)"}


def _f(v):
    return f"{v:g}" if isinstance(v, float) else str(v)


def _barras(itens, largura=300, cor="var(--amb)", sufixo=""):
    """Barras horizontais em SVG: [(rótulo, valor)]."""
    if not itens:
        return '<p class="mut">Sem dados ainda.</p>'
    maior = max(v for _, v in itens) or 1
    alt = 26 * len(itens)
    linhas = []
    for i, (rot, v) in enumerate(itens):
        y = i * 26
        w = max(2, round((largura - 150) * v / maior))
        linhas.append(f'<text x="0" y="{y + 15}" class="sv">{_e(rot)}</text>'
                      f'<rect x="125" y="{y + 4}" width="{largura - 150}" height="14" rx="7" fill="var(--line)"/>'
                      f'<rect x="125" y="{y + 4}" width="{w}" height="14" rx="7" fill="{cor}"/>'
                      f'<text x="{125 + w + 6}" y="{y + 15}" class="sv b">{_f(v)}{sufixo}</text>')
    return (f'<svg viewBox="0 0 {largura + 30} {alt}" width="100%" role="img" '
            f'aria-label="{_e(", ".join(f"{r}: {_f(v)}" for r, v in itens))}">{"".join(linhas)}</svg>')


def _meta_svg(m):
    """Régua 0–100 (ou 0–max) com linha de base, valor atual e meta."""
    topo = max(100, m["valor"], m["meta"]) if m["unidade"] == "%" else max(m["valor"], m["meta"]) * 1.25 or 1
    x = lambda v: round(10 + 380 * v / topo)  # noqa: E731
    cor = "var(--ok)" if m["atingiu"] else "var(--warn)"
    base = ""
    if "linha_base" in m:
        base = (f'<rect x="10" y="44" width="{x(m["linha_base"]) - 10}" height="10" rx="5" fill="var(--mut)" opacity=".45"/>'
                f'<text x="10" y="72" class="sv">linha de base {_f(m["linha_base"])}{_e(m["unidade"])}</text>')
    return (f'<svg viewBox="0 0 400 80" width="100%" role="img" aria-label="{_e(m["nome"])}: {_f(m["valor"])} '
            f'de meta {_f(m["meta"])}">'
            f'<rect x="10" y="20" width="380" height="16" rx="8" fill="var(--line)"/>'
            f'<rect x="10" y="20" width="{max(4, x(m["valor"]) - 10)}" height="16" rx="8" fill="{cor}"/>'
            f'<line x1="{x(m["meta"])}" x2="{x(m["meta"])}" y1="12" y2="44" stroke="var(--txt)" stroke-width="2"/>'
            f'<text x="{min(x(m["meta"]), 330)}" y="9" class="sv b">meta {_f(m["meta"])}{_e(m["unidade"])}</text>'
            f'{base}</svg>')


def _linha_svg(serie, rotulos):
    if len(serie) < 2:
        return ""
    lo, hi = min(serie) - 2, max(serie) + 2
    pts = [(20 + i * 260 / (len(serie) - 1), 60 - 46 * (v - lo) / (hi - lo)) for i, v in enumerate(serie)]
    caminho = " ".join(f"{x:.0f},{y:.0f}" for x, y in pts)
    marcas = "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.5" fill="var(--amb)"/>'
                     f'<text x="{x:.0f}" y="{y - 8:.0f}" text-anchor="middle" class="sv">{_f(v)}</text>'
                     f'<text x="{x:.0f}" y="80" text-anchor="middle" class="sv mut">{_e(r)}</text>'
                     for (x, y), v, r in zip(pts, serie, rotulos or [""] * len(serie)))
    return (f'<svg viewBox="0 0 300 86" width="100%" role="img" aria-label="evolução: {_e(", ".join(map(_f, serie)))}">'
            f'<polyline points="{caminho}" fill="none" stroke="var(--amb)" stroke-width="2.5"/>{marcas}</svg>')


def _tag(ok, sim="atingiu", nao="não atingiu"):
    cor = "var(--ok)" if ok else "var(--warn)"
    return f'<span class="tag" style="border-color:{cor};color:{cor}">{sim if ok else nao}</span>'


def render_executivo_html(d: dict) -> str:
    neg, op, ctl, c = d["negocio"], d["operacao"], d["controle"], d["custo"]
    prin = next(m for m in neg["metricas"] if m["id"] == neg["principal"])
    outras = [m for m in neg["metricas"] if m is not prin]
    alertas = "".join(f'<li><span class="tag" style="border-color:{NIVEL_COR[a["nivel"]]};color:{NIVEL_COR[a["nivel"]]}">'
                      f'{NIVEL_ROT[a["nivel"]]}</span> {_e(a["texto"])}</li>' for a in d["alertas"])
    tiles = "".join(
        f'<div class="kpi"><span>{_e(m["nome"])}</span><b>{_f(m["valor"])}<small> {_e(m["unidade"])}</small></b>'
        f'<em>meta {"≥" if m["sentido"] == "maior" else "≤"} {_f(m["meta"])} · {_tag(m["atingiu"])}</em>'
        f'{_linha_svg(m["serie"], m.get("rotulos_serie"))}'
        f'<small class="mut">{_e(m.get("detalhe", ""))}</small></div>' for m in outras)
    r, g = op["rascunhos"], op["por_gatilho"]
    total_r = max(1, r["propostos"])
    pilha, x = [], 0
    for rot, v, cor in (("aprovados sem edição", r["aprovados_sem_edicao"], "var(--ok)"),
                        ("aprovados com edição", r["aprovados_com_edicao"], "var(--amb)"),
                        ("rejeitados", r["rejeitados"], "var(--bad)"),
                        ("pendentes", r["pendentes"], "var(--mut)")):
        w = 380 * v / total_r
        if v:
            pilha.append(f'<rect x="{10 + x:.0f}" y="6" width="{w:.0f}" height="22" fill="{cor}"/>')
        x += w
    legenda = (f'<p class="leg"><i style="background:var(--ok)"></i>{r["aprovados_sem_edicao"]} aprovados sem edição '
               f'<i style="background:var(--amb)"></i>{r["aprovados_com_edicao"]} com edição '
               f'<i style="background:var(--bad)"></i>{r["rejeitados"]} rejeitados '
               f'<i style="background:var(--mut)"></i>{r["pendentes"]} pendentes</p>')
    integra = ctl["corrente_integra"]
    modelos = "".join(f'<tr><td><code>{_e(m)}</code></td><td>{v["chamadas"]}</td><td>{v["tokens_estimados"]}</td>'
                      f'<td style="white-space:nowrap">{_e(c["moeda"])} {v["custo"]:.2f}</td></tr>' for m, v in c["por_modelo"].items())
    negados = ", ".join(f"{p}: {n}" for p, n in ctl["negados_por_papel"].items()) or "nenhum"
    t = op["tempo_ate_aprovacao"]
    tempo = f'{_f(t["mediana_min"])} min (mediana de {t["amostras"]})' if t["amostras"] else "sem aprovações ainda"
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painel executivo — {_e(d['data_referencia'])}</title>
<style>
:root{{--bg:#0c0c10;--card:#16161e;--line:#272730;--txt:#e9e9ee;--mut:#9a9aa6;--amb:#FACC15;
--ok:#4ade80;--warn:#f59e0b;--bad:#f87171}}
@media (prefers-color-scheme: light){{:root{{--bg:#f6f7f9;--card:#fff;--line:#e1e3ea;--txt:#1a1a22;--mut:#5b5b68;
--amb:#a16207;--ok:#15803d;--warn:#b45309;--bad:#b91c1c}}}}
@media print{{:root{{--bg:#fff;--card:#fff;--line:#ddd;--txt:#111;--mut:#555;--amb:#854d0e;--ok:#15803d;--warn:#b45309;--bad:#b91c1c}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 Inter,system-ui,sans-serif}}
main{{max-width:1120px;margin:0 auto;padding:28px 16px}}
h1{{font-family:Sora,system-ui,sans-serif;margin:.2em 0 .1em;font-size:clamp(1.5rem,3.4vw,2.1rem)}}
h2{{font-family:Sora,system-ui,sans-serif;font-size:1.05rem;margin:0 0 10px}}
.chip{{color:var(--amb);font-size:.75rem;letter-spacing:.14em;text-transform:uppercase;font-weight:700}}
.mut{{color:var(--mut)}} small{{color:var(--mut)}}
.grade{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin-top:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;min-width:0}}
.largo{{grid-column:1/-1}}
.alertas{{list-style:none;margin:0;padding:0}} .alertas li{{padding:7px 0;border-bottom:1px solid var(--line)}}
.alertas li:last-child{{border:none}}
.tag{{border:1px solid;border-radius:999px;padding:1px 9px;font-size:.75rem;white-space:nowrap;font-weight:600}}
.grande{{font:800 2.6rem Sora,system-ui;color:var(--amb);line-height:1}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px}}
.kpi{{border:1px solid var(--line);border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:4px}}
.kpi span{{color:var(--mut);font-size:.85rem}} .kpi b{{font:800 1.6rem Sora,system-ui;color:var(--amb)}}
.kpi em{{font-style:normal;font-size:.82rem}}
.num{{display:flex;gap:18px;flex-wrap:wrap;margin:6px 0 10px}} .num div b{{display:block;font:800 1.4rem Sora,system-ui}}
.num div span{{color:var(--mut);font-size:.8rem}}
.sv{{font:12px Inter,system-ui,sans-serif;fill:var(--txt)}} .sv.b{{font-weight:700}} .sv.mut{{fill:var(--mut)}}
.leg{{font-size:.82rem;color:var(--mut)}} .leg i{{display:inline-block;width:10px;height:10px;border-radius:3px;margin:0 4px 0 10px}}
.leg i:first-child{{margin-left:0}}
table{{width:100%;border-collapse:collapse}} td,th{{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left;font-size:.88rem}}
th{{color:var(--mut);font-weight:600}} code{{font-family:"JetBrains Mono",monospace;font-size:.82rem}}
.estado{{font:800 1.3rem Sora,system-ui}}
footer{{color:var(--mut);font-size:.82rem;margin-top:20px}}
</style></head><body><main>
<div class="chip">Painel executivo · {_e(d['data_referencia'])}</div>
<h1>O app está entregando o resultado prometido?</h1>
<p class="mut">Calculado do audit log, da fila de aprovações, da caixa de saída e dos dados do app. Nenhum número vem de LLM.</p>

<div class="grade">
<section class="card largo"><h2>Alertas executivos</h2><ul class="alertas">{alertas}</ul></section>

<section class="card largo"><h2>1 · Resultado de negócio (canvas)</h2>
<div class="grade" style="margin-top:0">
<div><span class="mut">{_e(prin['nome'])}</span>
<div class="grande">{_f(prin['valor'])}{_e(prin['unidade'])}</div>
<p>{_tag(prin['atingiu'])} <small>meta {_f(prin['meta'])}{_e(prin['unidade'])} · {_e(prin.get('detalhe', ''))}</small></p>
<p><small>{_e(neg.get('regra', ''))}</small></p></div>
<div>{_meta_svg(prin)}</div>
</div>
<div class="kpis">{tiles}</div></section>

<section class="card"><h2>2 · Operação dos agentes</h2>
<div class="num"><div><b>{op['execucoes']}</b><span>execuções</span></div>
<div><b>{_f(r['taxa_aprovacao'])}%</b><span>rascunhos aprovados</span></div>
<div><b>{op['sugestoes']['executadas']}/{op['sugestoes']['geradas']}</b><span>sugestões aceitas</span></div></div>
<p class="mut" style="margin:0 0 4px">Por workflow</p>
{_barras(list(op['por_workflow'].items()))}
<p class="mut" style="margin:10px 0 4px">Por gatilho</p>
{_barras([("clique", g['clique']), ("horário", g['horario']), ("evento", g['evento'])], cor="var(--mut)")}
<p class="mut" style="margin:10px 0 4px">Rascunhos ({r['propostos']} propostos) · tempo até aprovar: {tempo}</p>
<svg viewBox="0 0 400 34" width="100%" role="img" aria-label="rascunhos por desfecho"><rect x="10" y="6" width="380" height="22" rx="4" fill="var(--line)"/>{''.join(pilha)}</svg>
{legenda}</section>

<section class="card"><h2>3 · Controle e risco</h2>
<div class="num"><div><b class="estado" style="color:{'var(--ok)' if integra else 'var(--bad)'}">{'ÍNTEGRA' if integra else 'QUEBRADA'}</b>
<span>corrente de hash ({ctl['linhas_audit']} linhas{'' if integra else f", quebra na linha {ctl['quebra_na_linha']}"})</span></div>
<div><b style="color:{'var(--ok)' if ctl['pct_com_aprovacao'] >= 100 else 'var(--bad)'}">{_f(ctl['pct_com_aprovacao'])}%</b>
<span>ações externas com aprovação ({ctl['acoes_com_aprovacao']}/{ctl['acoes_externas']})</span></div></div>
<table><tr><th>Indicador</th><th>Valor</th></tr>
<tr><td>Acessos negados (todos auditados)</td><td>{ctl['negados']} <small>({_e(negados)})</small></td></tr>
<tr><td>Ferramentas barradas pelo escopo mínimo</td><td>{ctl['ferramentas_barradas']}</td></tr>
<tr><td>Execuções com erro</td><td>{op['erros']}</td></tr></table></section>

<section class="card"><h2>4 · Custo e uso de LLM</h2>
<div class="num"><div><b>{c['chamadas']}</b><span>chamadas de LLM</span></div>
<div><b>~{c['tokens_estimados']}</b><span>tokens (estimativa)</span></div>
<div><b>{_e(c['moeda'])} {c['custo_total']:.2f}</b><span>custo no período</span></div></div>
<table><tr><th>Modelo</th><th>Chamadas</th><th>Tokens est.</th><th>Custo</th></tr>{modelos}</table>
<p class="mut" style="margin:10px 0 4px">Chamadas por workflow</p>
{_barras(list(c['por_workflow'].items()))}
<p><small>Preços em templates/indicadores.json (padrão 0). Tokens = caracteres ÷ 4 quando o adaptador não informa.</small></p></section>
</div>
<footer>Dados fictícios · agentic-app · workflow painel_executivo · acesso: diretoria e admin · cada consulta fica no audit log.</footer>
</main></body></html>
"""


def render_executivo_pdf(d: dict) -> bytes:
    neg, op, ctl, c = d["negocio"], d["operacao"], d["controle"], d["custo"]
    cmds = []

    def txt(x, y, s, tam=10, negrito=False):
        cmds.append(f"BT /{'F2' if negrito else 'F1'} {tam} Tf {x} {y} Td ({_pdf_texto(s)}) Tj ET")

    txt(40, 800, "Painel executivo", 18, True)
    txt(40, 782, f"{d['data_referencia']}  -  calculado do audit log, da fila e dos dados do app (sem LLM)", 10)
    y = 752
    txt(40, y, "Alertas", 12, True); y -= 18
    for a in d["alertas"]:
        linha = f"[{NIVEL_ROT[a['nivel']]}] {a['texto']}"
        while linha:
            corte = linha[:100].rfind(" ") if len(linha) > 100 else len(linha)
            txt(40, y, linha[:corte], 9); y -= 13
            linha = linha[corte:].strip()
    y -= 10
    txt(40, y, "1. Resultado de negocio", 12, True); y -= 20
    for m in neg["metricas"]:
        topo = max(100, m["valor"], m["meta"]) if m["unidade"] == "%" else max(m["valor"], m["meta"]) * 1.25 or 1
        txt(40, y, m["nome"], 9, m["id"] == neg["principal"])
        cmds.append(f"0.88 0.89 0.92 rg 280 {y - 2} 180 10 re f")
        cor = "0.08 0.5 0.24" if m["atingiu"] else "0.7 0.33 0.04"
        cmds.append(f"{cor} rg 280 {y - 2} {max(2, round(180 * m['valor'] / topo))} 10 re f 0 0 0 rg")
        mx = 280 + round(180 * m["meta"] / topo)
        cmds.append(f"0 0 0 RG 1 w {mx} {y - 5} m {mx} {y + 11} l S")
        txt(468, y, f"{_f(m['valor'])} {m['unidade']} (meta {_f(m['meta'])})", 8)
        y -= 20
    y -= 8
    r, g = op["rascunhos"], op["por_gatilho"]
    txt(40, y, "2. Operacao dos agentes", 12, True); y -= 16
    for linha in (f"{op['execucoes']} execucoes  -  clique {g['clique']}, horario {g['horario']}, evento {g['evento']}",
                  "Por workflow: " + ", ".join(f"{k} {v}" for k, v in op["por_workflow"].items()),
                  f"Rascunhos: {r['propostos']} propostos, {r['aprovados_sem_edicao']} aprovados sem edicao, "
                  f"{r['aprovados_com_edicao']} com edicao, {r['rejeitados']} rejeitados, {r['pendentes']} pendentes",
                  f"Sugestoes do agente de fundo aceitas: {op['sugestoes']['executadas']}/{op['sugestoes']['geradas']}"):
        txt(40, y, linha, 9); y -= 13
    y -= 8
    txt(40, y, "3. Controle e risco", 12, True); y -= 16
    for linha in (f"Corrente de hash: {'integra' if ctl['corrente_integra'] else 'QUEBRADA na linha ' + str(ctl['quebra_na_linha'])}"
                  f" ({ctl['linhas_audit']} linhas)",
                  f"Acoes externas com aprovacao: {ctl['acoes_com_aprovacao']}/{ctl['acoes_externas']} "
                  f"({_f(ctl['pct_com_aprovacao'])}%)",
                  f"Acessos negados: {ctl['negados']} {ctl['negados_por_papel']}  -  ferramentas barradas: "
                  f"{ctl['ferramentas_barradas']}"):
        txt(40, y, linha, 9); y -= 13
    y -= 8
    txt(40, y, "4. Custo e uso de LLM", 12, True); y -= 16
    txt(40, y, f"{c['chamadas']} chamadas, ~{c['tokens_estimados']} tokens estimados, custo {c['moeda']} "
               f"{c['custo_total']:.2f}", 9); y -= 13
    for m, v in c["por_modelo"].items():
        txt(52, y, f"{m}: {v['chamadas']} chamadas, ~{v['tokens_estimados']} tokens, {c['moeda']} {v['custo']:.2f}", 9)
        y -= 13
    txt(40, 40, "Dados ficticios - agentic-app - workflow painel_executivo - acesso: diretoria e admin", 8)
    return _montar_pdf(cmds)


def gerar_executivo(dados: dict, pasta: Path, art: dict) -> list:
    pasta = Path(pasta)
    (pasta / art["html"]).write_text(render_executivo_html(dados), encoding="utf-8")
    arquivos = [art["html"]]
    if art.get("pdf"):
        (pasta / art["pdf"]).write_bytes(render_executivo_pdf(dados))
        arquivos.append(art["pdf"])
    return arquivos
