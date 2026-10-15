"""Gráficos em SVG puro para os painéis (sem biblioteca, sem JS).

Regras de desenho (iguais em todos):
- barra/coluna até 24 px, ponta arredondada de 4 px e base reta; 2 px de vão na cor da superfície entre segmentos;
- linhas de 2 px, grade fina e sólida, texto sempre em tinta de texto (nunca na cor da série);
- toda marca tem <title> (tooltip ao passar o mouse) e, quando há `href`, vira link de filtro (clicar = detalhar);
- duas ou mais séries => legenda sempre; cor de status só para status (ok, negado, pausado, falha).

Ordem fixa das séries de status: ok -> negado -> pausado -> falha (laranja e vermelho nunca ficam lado a lado).
"""
import html

STATUS_SERIES = [("ok", "ok", "var(--ok)"), ("negado", "negado", "var(--warn)"),
                 ("pausado", "pausado", "var(--mut)"), ("falha", "falha", "var(--bad)")]


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _f(v):
    if isinstance(v, float):
        return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}".replace(",", ".")
    return str(v)


def _ticks(maximo):
    """Topo 'redondo' do eixo e 2 marcas intermediárias."""
    if maximo <= 0:
        return 1, [0, 1]
    passo = 1
    for p in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if maximo / p <= 4:
            passo = p
            break
    else:
        passo = 10 ** len(str(int(maximo)))
    topo = passo * -(-maximo // passo)
    return topo, [passo * i for i in range(int(topo // passo) + 1)]


def _barra_v(x, y, w, h, cor, arred=True):
    """Coluna com ponta arredondada (4 px) e base reta."""
    if h <= 0:
        return ""
    r = min(4, w / 2, h) if arred else 0
    if not r:
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{cor}"/>'
    return (f'<path d="M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} H{x + w - r:.1f} '
            f'Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z" fill="{cor}"/>')


def _barra_h(x, y, w, h, cor, arred=True):
    if w <= 0:
        return ""
    r = min(4, h / 2, w) if arred else 0
    if not r:
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{cor}"/>'
    return (f'<path d="M{x:.1f},{y:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} '
            f'V{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} H{x:.1f} Z" fill="{cor}"/>')


def legenda(series):
    """series: [(chave, rótulo, cor)]."""
    return '<p class="leg">' + "".join(f'<span><i style="background:{c}"></i>{_e(r)}</span>' for _, r, c in series) + "</p>"


def _link(conteudo, href, titulo):
    t = f"<title>{_e(titulo)}</title>"
    if href:
        return f'<a href="{_e(href)}" class="alvo">{t}{conteudo}</a>'
    return f"<g>{t}{conteudo}</g>"


def colunas(categorias, series, dados, href=None, altura=190, rotulos_x=None, unidade="", destaque=None, largura=640):
    """Colunas empilhadas. categorias: [chave]; series: [(chave, rótulo, cor)]; dados: {cat: {serie: n}}.

    href(cat) -> url de filtro; rotulos_x: {cat: texto} (só os que aparecem no eixo); destaque: cat selecionada.
    """
    n = len(categorias)
    if not n:
        return '<p class="mut">Sem dados no filtro.</p>'
    esq, dir_, topo, base = 36, largura - 8, 14, altura - 26
    totais = [sum(dados.get(c, {}).get(s[0], 0) for s in series) for c in categorias]
    vmax, marcas = _ticks(max(totais) or 1)
    banda = (dir_ - esq) / n
    w = min(24, banda * 0.72)
    Y = lambda v: base - (base - topo) * v / vmax  # noqa: E731
    partes = []
    for m in marcas:
        partes.append(f'<line x1="{esq}" x2="{dir_}" y1="{Y(m):.1f}" y2="{Y(m):.1f}" stroke="var(--line)" stroke-width="1"/>'
                      f'<text x="{esq - 6}" y="{Y(m) + 4:.1f}" text-anchor="end" class="sv mut">{_f(m)}</text>')
    for i, c in enumerate(categorias):
        x = esq + banda * i + (banda - w) / 2
        y_acum = base
        segs = []
        presentes = [s for s in series if dados.get(c, {}).get(s[0], 0)]
        for j, (k, rot, cor) in enumerate(presentes):
            v = dados[c][k]
            h = (base - topo) * v / vmax
            gap = 2 if j > 0 else 0
            segs.append(_barra_v(x, y_acum - h, w, max(0, h - gap), cor, arred=(j == len(presentes) - 1)))
            y_acum -= h
        detalhe = ", ".join(f"{rot} {dados.get(c, {}).get(k, 0)}" for k, rot, _ in series)
        rot_c = (rotulos_x or {}).get(c, c)
        alvo = f'<rect x="{esq + banda * i:.1f}" y="{topo}" width="{banda:.1f}" height="{base - topo}" fill="transparent"/>'
        if destaque == c:
            alvo = (f'<rect x="{esq + banda * i:.1f}" y="{topo}" width="{banda:.1f}" height="{base - topo}" '
                    f'fill="var(--amb)" opacity=".08"/>')
        partes.append(_link(alvo + "".join(segs), href(c) if href else None,
                            f"{rot_c}: {totais[i]}{unidade} ({detalhe})"))
        if rotulos_x is None or c in rotulos_x:
            partes.append(f'<text x="{x + w / 2:.1f}" y="{base + 16}" text-anchor="middle" class="sv mut">{_e(rot_c)}</text>')
    pico = max(range(n), key=lambda i: totais[i])
    if totais[pico]:
        xp = esq + banda * pico + banda / 2
        partes.append(f'<text x="{xp:.1f}" y="{Y(totais[pico]) - 5:.1f}" text-anchor="middle" class="sv b">'
                      f'{_f(totais[pico])}</text>')
    partes.append(f'<line x1="{esq}" x2="{dir_}" y1="{base}" y2="{base}" stroke="var(--mut)" stroke-width="1"/>')
    svg = (f'<svg viewBox="0 0 {largura} {altura}" width="100%" role="img" '
           f'aria-label="{_e(", ".join(f"{(rotulos_x or {}).get(c, c)} {t}" for c, t in zip(categorias, totais)))}">'
           f'{"".join(partes)}</svg>')
    return svg + (legenda(series) if len(series) > 1 else "")


def barras(itens, series=None, href=None, unidade="", destaque=None, largura_rot=150, largura=640):
    """Barras horizontais (empilhadas se `series`). itens: [(chave, rótulo, {serie: n} | n)]."""
    if not itens:
        return '<p class="mut">Sem dados no filtro.</p>'
    series = series or [("v", "", "var(--amb)")]
    linha_h = 30
    esq, dir_ = largura_rot, largura - 44
    altura = linha_h * len(itens) + 8
    def tot(v):
        return sum(v.values()) if isinstance(v, dict) else v
    vmax = max(tot(v) for _, _, v in itens) or 1
    partes = []
    for i, (k, rot, v) in enumerate(itens):
        y = 4 + i * linha_h
        h = min(18, linha_h - 10)
        vals = v if isinstance(v, dict) else {"v": v}
        presentes = [s for s in series if vals.get(s[0], 0)]
        x = esq
        segs = []
        for j, (sk, srot, cor) in enumerate(presentes):
            w = (dir_ - esq) * vals[sk] / vmax
            gap = 2 if j < len(presentes) - 1 else 0
            segs.append(_barra_h(x, y + (linha_h - h) / 2, max(0, w - gap), h, cor, arred=(j == len(presentes) - 1)))
            x += w
        sel = f'<rect x="0" y="{y}" width="{largura}" height="{linha_h}" fill="var(--amb)" opacity=".08"/>' \
            if destaque == k else f'<rect x="0" y="{y}" width="{largura}" height="{linha_h}" fill="transparent"/>'
        txt = (f'<text x="{esq - 8}" y="{y + linha_h / 2 + 4:.1f}" text-anchor="end" class="sv">{_e(rot)}</text>'
               f'<text x="{x + 6:.1f}" y="{y + linha_h / 2 + 4:.1f}" class="sv b">{_f(tot(v))}{_e(unidade)}</text>')
        detalhe = ", ".join(f"{srot} {vals.get(sk, 0)}" for sk, srot, _ in series if srot)
        partes.append(_link(sel + "".join(segs) + txt, href(k) if href else None,
                            f"{rot}: {_f(tot(v))}{unidade}" + (f" ({detalhe})" if detalhe else "")))
    svg = (f'<svg viewBox="0 0 {largura} {altura}" width="100%" role="img" '
           f'aria-label="{_e(", ".join(f"{r} {_f(tot(v))}" for _, r, v in itens))}">{"".join(partes)}</svg>')
    return svg + (legenda(series) if len(series) > 1 else "")


def rosca(itens, href=None, centro="", destaque=None):
    """Rosca com legenda que leva valor e %. itens: [(chave, rótulo, n, cor)]."""
    import math
    total = sum(n for _, _, n, _ in itens)
    if not total:
        return '<p class="mut">Sem dados no filtro.</p>'
    cx, cy, r, esp = 80, 80, 62, 20
    ang = -math.pi / 2
    partes = []
    vivos = [i for i in itens if i[2]]
    for k, rot, n, cor in vivos:
        frac = n / total
        a2 = ang + 2 * math.pi * frac
        if len(vivos) == 1:
            arco = (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{cor}" stroke-width="{esp}"/>')
        else:
            gap = 0.035
            x1, y1 = cx + r * math.cos(ang + gap / 2), cy + r * math.sin(ang + gap / 2)
            x2, y2 = cx + r * math.cos(a2 - gap / 2), cy + r * math.sin(a2 - gap / 2)
            grande = 1 if (a2 - ang) > math.pi else 0
            arco = (f'<path d="M{x1:.1f},{y1:.1f} A{r},{r} 0 {grande} 1 {x2:.1f},{y2:.1f}" fill="none" '
                    f'stroke="{cor}" stroke-width="{esp + (4 if destaque == k else 0)}"/>')
        partes.append(_link(arco, href(k) if href else None, f"{rot}: {n} ({100 * n / total:.0f}%)"))
        ang = a2
    partes.append(f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" class="sv grande">{_f(total)}</text>'
                  f'<text x="{cx}" y="{cy + 20}" text-anchor="middle" class="sv mut">{_e(centro)}</text>')
    svg = (f'<svg viewBox="0 0 160 160" width="160" height="160" role="img" '
           f'aria-label="{_e(", ".join(f"{r} {n}" for _, r, n, _ in itens))}">{"".join(partes)}</svg>')
    leg = "".join(
        f'<li>{"<a href=" + chr(34) + _e(href(k)) + chr(34) + ">" if href else ""}<i style="background:{c}"></i>'
        f'<span>{_e(r)}</span><b>{n}</b><small>{100 * n / total:.0f}%</small>{"</a>" if href else ""}</li>'
        for k, r, n, c in itens)
    return f'<div class="rosca">{svg}<ul>{leg}</ul></div>'


def linha(rotulos, series, altura=190, meta=None, unidade="", rotulos_x_cada=1, largura=640):
    """Linhas no mesmo eixo. series: [(rótulo, [valores], cor, tracejada)]; meta: (valor, rótulo)."""
    vals = [v for _, s, _, _ in series for v in s if v is not None] + ([meta[0]] if meta else [])
    if len(rotulos) < 2 or not vals:
        return '<p class="mut">Histórico insuficiente para desenhar.</p>'
    esq, dir_, topo, base = 40, largura - 40, 14, altura - 26
    # linha não precisa partir do zero: com faixa estreita (ex.: engajamento 74-80) o eixo começa perto dos dados
    mn, mx = min(vals), max(vals)
    if mn > 0 and (mx - mn) < 0.5 * mx:
        passo = _ticks(max(mx - mn, 1e-9) * 1.4)[1][1] or 1
        lo = passo * int((mn - (mx - mn) * 0.2) // passo)
        vmax = passo * -(-mx // passo)
        marcas = [lo + passo * i for i in range(int((vmax - lo) // passo) + 1)]
    else:
        lo = min(0, mn)
        vmax, marcas = _ticks(mx)
    n = len(rotulos)
    X = lambda i: esq + (dir_ - esq) * i / (n - 1)  # noqa: E731
    Y = lambda v: base - (base - topo) * (v - lo) / ((vmax - lo) or 1)  # noqa: E731
    partes = []
    for m in marcas:
        partes.append(f'<line x1="{esq}" x2="{dir_}" y1="{Y(m):.1f}" y2="{Y(m):.1f}" stroke="var(--line)" stroke-width="1"/>'
                      f'<text x="{esq - 6}" y="{Y(m) + 4:.1f}" text-anchor="end" class="sv mut">{_f(m)}</text>')
    if meta:
        partes.append(f'<line x1="{esq}" x2="{dir_}" y1="{Y(meta[0]):.1f}" y2="{Y(meta[0]):.1f}" stroke="var(--txt)" '
                      f'stroke-width="1.5" stroke-dasharray="6 4"/><text x="{esq + 6}" y="{Y(meta[0]) - 6:.1f}" '
                      f'class="sv b">{_e(meta[1])}</text>')
    for rot, s, cor, trac in series:
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(s) if v is not None)
        partes.append(f'<polyline points="{pts}" fill="none" stroke="{cor}" stroke-width="2" stroke-linejoin="round" '
                      f'stroke-linecap="round"{" stroke-dasharray=" + chr(34) + "4 4" + chr(34) if trac else ""}/>')
        for i, v in enumerate(s):
            if v is None:
                continue
            fim = i == len(s) - 1
            partes.append(f'<g><title>{_e(rotulos[i])} · {_e(rot)}: {_f(v)}{_e(unidade)}</title>'
                          f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{5 if fim else 9}" '
                          f'fill="{cor if fim else "transparent"}" stroke="{"var(--card)" if fim else "none"}" stroke-width="2"/></g>')
        if not trac:
            partes.append(f'<text x="{X(len(s) - 1) + 8:.1f}" y="{Y(s[-1]) + 4:.1f}" class="sv b">{_f(s[-1])}</text>')
    for i, r in enumerate(rotulos):
        if i % rotulos_x_cada == 0 or i == n - 1:
            partes.append(f'<text x="{X(i):.1f}" y="{base + 16}" text-anchor="middle" class="sv mut">{_e(r)}</text>')
    partes.append(f'<line x1="{esq}" x2="{dir_}" y1="{base}" y2="{base}" stroke="var(--mut)" stroke-width="1"/>')
    svg = (f'<svg viewBox="0 0 {largura} {altura}" width="100%" role="img" '
           f'aria-label="{_e("; ".join(f"{r}: " + ", ".join(_f(v) for v in s if v is not None) for r, s, _, _ in series))}">'
           f'{"".join(partes)}</svg>')
    return svg + (legenda([(r, r, c) for r, _, c, _ in series]) if len(series) > 1 else "")
