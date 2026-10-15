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
