"""Painel web local: python3 -m agentic_app.serve [--porta 8765]

Só 127.0.0.1. Usuário da demo vem do cabeçalho X-Usuario (ana, rosa, bruno, dora).
As abas /executivo e /tendencias também aceitam ?usuario=dora / ?usuario=estela (um link não manda cabeçalho) — mesma confiança da demo.
Na sua empresa, troque isso pelo login corporativo (SSO) — ver docs/PASSO-A-PASSO.md.

A lógica fica em `tratar(...)`, função pura que os testes chamam sem abrir socket.
"""
import argparse
import html
import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .apps.coaching import montar
from .relatorio import render_executivo_html, render_tendencias_html
from .seguranca import PermissaoNegada
from .workflow import ErroWorkflow

PAINEL = Path(__file__).resolve().parent / "painel.html"
_APP = None


def app():
    global _APP
    if _APP is None:
        _APP = montar()
    return _APP


def _json(status, obj):
    return status, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode()


def estado(a, uid):
    return {
        "usuario": uid,
        "usuarios": [{"id": u.id, "nome": u.nome, "papeis": list(u.papeis)}
                     for u in a.usuarios.values() if u.id != "sistema"],
        "painel": a.painel(),
        "pendentes": a.fila.pendentes(),
        "sugestoes": a.sugestoes,
        "componentes": a.gatilhos.componentes,
        "workflows": {w: {"titulo": s["titulo"], "resultado": s["resultado_de_negocio"],
                          "executar": s["seguranca"]["executar"], "identidade": s["seguranca"]["identidade"],
                          "nos": [f"{n['id']}:{n['tipo']}" for n in s["nos"]]}
                      for w, s in a.motor.workflows.items()},
    }


NEGADO_HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Acesso negado</title>
<style>:root{{--bg:#0c0c10;--txt:#e9e9ee;--mut:#9a9aa6}}@media (prefers-color-scheme: light){{:root{{--bg:#f6f7f9;
--txt:#1a1a22;--mut:#5b5b68}}}}body{{margin:0;background:var(--bg);color:var(--txt);font:16px/1.5 system-ui;padding:40px 16px}}
p{{color:var(--mut)}}</style></head><body><h1>Acesso negado</h1><p>{msg}</p>
<p>Este painel é só para {quem}. A tentativa ficou registrada no audit log.</p></body></html>"""


def tratar(metodo, caminho, corpo=b"", uid="ana", a=None):
    a = a or app()
    url = urlparse(caminho)
    rota = url.path.rstrip("/") or "/"
    try:
        dados = json.loads(corpo or b"{}")
        if metodo == "GET" and rota == "/":
            return 200, "text/html; charset=utf-8", PAINEL.read_bytes()
        if metodo == "GET" and rota == "/api/estado":
            return _json(200, estado(a, uid))
        if metodo == "GET" and rota in ("/executivo", "/api/executivo"):
            quem = parse_qs(url.query).get("usuario", [uid])[0]
            try:
                r = a.executivo(a.usuario(quem), gatilho="manual:painel")
            except PermissaoNegada as e:
                if rota == "/executivo":
                    return 403, "text/html; charset=utf-8", NEGADO_HTML.format(msg=html.escape(str(e)), quem="diretoria e admin").encode()
                raise
            if rota == "/api/executivo":
                return _json(200, r["saida"])
            return 200, "text/html; charset=utf-8", render_executivo_html(r["saida"]).encode()
        if metodo == "GET" and rota in ("/tendencias", "/api/tendencias"):
            quem = parse_qs(url.query).get("usuario", [uid])[0]
            try:
                r = a.tendencias(a.usuario(quem), gatilho="manual:painel")
            except PermissaoNegada as e:
                if rota == "/tendencias":
                    return 403, "text/html; charset=utf-8", NEGADO_HTML.format(
                        msg=html.escape(str(e)), quem="estratégia, diretoria e admin").encode()
                raise
            if rota == "/api/tendencias":
                return _json(200, r["saida"])
            return 200, "text/html; charset=utf-8", render_tendencias_html(r["saida"]).encode()
        if metodo == "GET" and rota == "/api/audit":
            return _json(200, a.audit.ler()[-50:])
        if metodo == "GET" and rota.startswith("/saida/"):
            nome = rota.split("/")[-1]
            if nome not in ("relatorio.html", "relatorio.pdf"):  # executivo.* só pela rota /executivo (RBAC)
                return _json(404, {"erro": "arquivo não publicado"})
            arq = a.pasta / nome
            if not arq.exists():
                return _json(404, {"erro": "gere o relatório primeiro"})
            tipo = "application/pdf" if nome.endswith(".pdf") else "text/html; charset=utf-8"
            return 200, tipo, arq.read_bytes()
        if metodo != "POST":
            return _json(404, {"erro": "rota não encontrada"})
        usuario = a.usuario(uid)
        partes = rota.strip("/").split("/")
        if partes[:2] == ["api", "workflow"] and len(partes) == 3:
            r = a.motor.executar(partes[2], dados.get("entrada", {}), usuario, gatilho="manual:painel")
            if partes[2] == "proximos_passos":
                a.guardar_sugestoes(r)
            return _json(200, r)
        if partes[:2] == ["api", "acoes"] and len(partes) == 4:
            if partes[3] == "aprovar":
                return _json(200, a.fila.aprovar(partes[2], usuario, dados.get("edicoes")))
            if partes[3] == "rejeitar":
                return _json(200, a.fila.rejeitar(partes[2], usuario, dados.get("motivo", "")))
        if partes[:2] == ["api", "sugestoes"] and len(partes) == 4 and partes[3] == "executar":
            return _json(200, a.executar_sugestao(partes[2], usuario))
        if rota == "/api/agendador/tick":
            return _json(200, [r["run_id"] for r in a.gatilhos.tick(datetime.fromisoformat(dados["agora"]))])
        if partes[:2] == ["api", "eventos"] and len(partes) == 3:
            return _json(200, a.gatilhos.emitir(partes[2], dados))
        return _json(404, {"erro": "rota não encontrada"})
    except PermissaoNegada as e:
        return _json(403, {"erro": str(e)})
    except (ErroWorkflow, ValueError) as e:
        return _json(400, {"erro": str(e)})
    except (KeyError, StopIteration) as e:
        return _json(404, {"erro": f"não encontrado: {e}"})


class Handler(BaseHTTPRequestHandler):
    def _responder(self, metodo):
        n = int(self.headers.get("content-length") or 0)
        corpo = self.rfile.read(n) if n else b""
        status, tipo, saida = tratar(metodo, self.path, corpo, self.headers.get("X-Usuario", "ana"))
        self.send_response(status)
        self.send_header("content-type", tipo)
        self.send_header("content-length", str(len(saida)))
        self.end_headers()
        self.wfile.write(saida)

    def do_GET(self):
        self._responder("GET")

    def do_POST(self):
        self._responder("POST")

    def log_message(self, fmt, *args):
        pass


def main():
    p = argparse.ArgumentParser(description="Painel do agentic-app (só 127.0.0.1)")
    p.add_argument("--porta", type=int, default=int(os.environ.get("AGENTIC_PORTA", 8765)))
    args = p.parse_args()
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), Handler)
    print(f"agentic-app no ar: http://127.0.0.1:{args.porta}  (Ctrl+C para parar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
