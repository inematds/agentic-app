"""Simula semanas de operação do app de referência: python3 -m agentic_app.simular [--semanas 8]

Não inventa linha de audit: roda os workflows de verdade pelo motor, com um RELÓGIO SIMULADO (o audit grava a
hora simulada). Gestora pedindo follow-up, RH respondendo perguntas, e-mails chegando (alguns de remetente
desconhecido, que falham), agendados de segunda e sexta, aprovações e rejeições com atraso, um colaborador
barrado, uma pausa no Centro de Comando e uma escalada. Determinístico (semente fixa), sem rede, FakeLLM.

Serve para os painéis terem o que mostrar (gráficos por dia, por hora, fila por idade). Os dados são
fictícios e a saída diz isso. Numa empresa, o audit real faz este papel.
"""
import argparse
import random
from datetime import datetime, timedelta

from . import config
from .apps.coaching import montar
from .seguranca import PermissaoNegada
from .workflow import ErroWorkflow

PERGUNTAS = ["Quantos dias de férias eu tenho?", "Posso dividir minhas férias em 15 e 15 dias, pedindo com 40 dias de antecedência?",
             "Vou adotar uma criança, quantos dias de licença tenho?", "Onde vejo meu holerite?",
             "Posso dividir minhas férias em 10 e 10 dias, pedindo com 15 dias de antecedência?",
             "Qual o prazo para pedir férias?"]


class Relogio:
    """Hora simulada (com fuso local). O AuditLog chama o objeto para carimbar cada linha."""

    def __init__(self, t: datetime):
        self.t = t

    def __call__(self):
        return self.t.isoformat(timespec="seconds")

    def ir(self, dia: datetime, hora: int, minuto: int = 0):
        self.t = dia.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        return self.t.replace(tzinfo=None)


def simular(pasta, semanas=8, fim=None, semente=42):
    fim = fim or datetime(2026, 10, 15, 17, 30).astimezone()
    rng = random.Random(semente)
    inicio = (fim - timedelta(weeks=semanas)).replace(hour=0, minute=0, second=0, microsecond=0)
    inicio -= timedelta(days=inicio.weekday())  # começa numa segunda-feira
    rel = Relogio(inicio)
    app = montar(pasta, relogio=rel)
    u = app.usuario
    ids = [p["id"] for p in app.equipe["liderados"]]
    cont = {"execucoes": 0, "falhas": 0, "negados": 0, "bloqueados": 0, "aprovadas": 0, "rejeitadas": 0}

    def rodar(f, *a, **k):
        try:
            r = f(*a, **k)
            cont["execucoes"] += 1
            return r
        except PermissaoNegada:
            cont["negados"] += 1
        except ErroWorkflow as e:
            cont["bloqueados" if "pausado" in str(e) else "falhas"] += 1
        return None

    def decidir(hoje):
        for i in list(app.fila.pendentes()):
            if rng.random() < 0.55:
                rel.ir(hoje, rng.randint(13, 17), rng.randint(0, 59))
                x = rng.random()
                if x < 0.16:
                    app.fila.rejeitar(i["id"], u("ana"), "já conversamos pessoalmente")
                    cont["rejeitadas"] += 1
                elif x < 0.40:
                    app.fila.aprovar(i["id"], u("ana"), {"corpo": i["payload"]["corpo"] + "\n\n(ajustado pela gestora)"})
                    cont["aprovadas"] += 1
                else:
                    app.fila.aprovar(i["id"], u("ana" if i["workflow"] != "assistente_rh" else "rosa"))
                    cont["aprovadas"] += 1

    dia = inicio
    semana_pausa = max(1, semanas - 3)
    while dia.date() <= fim.date():
        wd, n_sem = dia.weekday(), (dia - inicio).days // 7
        if wd < 5:
            if dia > inicio:
                decidir(dia)  # o que ficou pendente dos dias anteriores (decisão à tarde)
            if wd == 0:
                app.gatilhos.tick(rel.ir(dia, 7))
                r = app.gatilhos.tick(rel.ir(dia, 8))
                cont["execucoes"] += len(r)
                for x in r:
                    if x["workflow"] == "proximos_passos":
                        app.guardar_sugestoes(x)
                rel.ir(dia, 9, rng.randint(10, 50))
                for s in app.sugestoes[:rng.randint(1, 2)]:
                    rodar(app.executar_sugestao, s["id"], u("ana"))
            if wd == 1:
                rel.ir(dia, 10, rng.randint(0, 40))
                rodar(app.motor.executar, "followup_metas", {}, u("ana"))
            if n_sem == semana_pausa and wd == 2:
                rel.ir(dia, 11, 5)
                app.pausar("assistente_rh", u("otavio"), "resposta de férias com regra desatualizada")
            if n_sem == semana_pausa and wd == 3 and app.controle.pausado("assistente_rh"):
                rel.ir(dia, 9, 30)
                app.retomar("assistente_rh", u("otavio"))
            for _ in range(rng.randint(1, 4)):
                rel.ir(dia, rng.randint(8, 18), rng.randint(0, 59))
                quem = rng.choice(["bruno", "rosa", "rosa"])
                alvo = "bruno" if quem == "bruno" else rng.choice(ids)
                rodar(app.motor.executar, "assistente_rh", {"colaborador_id": alvo, "pergunta": rng.choice(PERGUNTAS)}, u(quem))
            for _ in range(rng.choice([0, 1, 1, 2])):
                rel.ir(dia, rng.randint(7, 20), rng.randint(0, 59))
                rem = rng.choice(ids) if rng.random() > 0.12 else "desconhecido"
                rodar(app.gatilhos.emitir, "email.recebido",
                      {"de": f"{rem}@exemplo.com", "remetente_id": rem, "corpo": rng.choice(PERGUNTAS)})
            if rng.random() < 0.08:
                rel.ir(dia, rng.randint(9, 17), rng.randint(0, 59))
                rodar(app.motor.executar, "followup_metas", {}, u("bruno"))
            if wd == 4:
                cont["execucoes"] += len(app.gatilhos.tick(rel.ir(dia, 17)))
        dia += timedelta(days=1)
    rel.ir(fim, fim.hour, fim.minute)
    pend = app.fila.pendentes()
    if pend:
        app.escalar(pend[0]["id"], u("otavio"), "esperando há mais de um dia")
    return app, fim, cont


def main():
    p = argparse.ArgumentParser(description="Simula semanas de operação (dados fictícios, relógio simulado)")
    p.add_argument("--semanas", type=int, default=8)
    args = p.parse_args()
    pasta = config.pasta_saida()
    for arq in ("audit.jsonl", "caixa_saida.jsonl", "aprovacoes.json", "sugestoes.json", "historico.jsonl", "comando.json"):
        (pasta / arq).unlink(missing_ok=True)
    app, fim, c = simular(pasta, args.semanas)
    agora = fim.isoformat(timespec="minutes")
    print(f"Simulação de {args.semanas} semanas (FICTÍCIA, relógio simulado) gravada em {pasta}/")
    print(f"  {c['execucoes']} execuções ok · {c['falhas']} falhas · {c['negados']} negados · {c['bloqueados']} bloqueados "
          f"por pausa · {c['aprovadas']} aprovadas · {c['rejeitadas']} rejeitadas · {len(app.fila.pendentes())} pendentes")
    print(f"  audit: {len(app.audit.ler())} linhas, corrente íntegra: {app.audit.verificar_corrente()}")
    q = f"agora={agora.replace('+', '%2B')}"
    print("Painéis (python3 -m agentic_app.serve):")
    print(f"  http://127.0.0.1:8765/comando?usuario=otavio&{q}")
    print(f"  http://127.0.0.1:8765/comando/negocio?usuario=ana&{q}")
    print(f"  http://127.0.0.1:8765/executivo?usuario=dora&{q}")
    print(f"  http://127.0.0.1:8765/tendencias?usuario=estela")


if __name__ == "__main__":
    main()
