"""Demo ponta a ponta no terminal: python3 -m agentic_app.demo

Roda os 5 workflows do app de Coaching de gestor, mostra RBAC negando, aprovação com
edição, gatilho agendado, gatilho por evento, agente de fundo e gera saida/relatorio.html.
Tudo com FakeLLM (determinístico, sem rede). Use AGENTIC_LLM=ollama para o Ollama local.
"""
from datetime import datetime

from . import __version__, config
from .apps.coaching import montar
from .executivo import resumo_texto
from .seguranca import PermissaoNegada


def titulo(t):
    print(f"\n== {t} " + "=" * max(0, 66 - len(t)))


def main():
    pasta = config.pasta_saida()
    for arq in ("audit.jsonl", "caixa_saida.jsonl", "aprovacoes.json", "sugestoes.json"):
        (pasta / arq).unlink(missing_ok=True)
    app = montar(pasta)
    ana, bruno, sistema = app.usuario("ana"), app.usuario("bruno"), app.usuario("sistema")
    print(f"agentic-app {__version__} · LLM: {app.motor.llm.nome} · saída: {pasta}/")

    titulo("1. Resultado de negócio")
    print("Usuária: Ana, gestora de 12 pessoas. Decisão: com quem falar esta semana.")
    print("Métrica: % de metas vencidas que tiveram conversa em até 7 dias.")

    titulo("2. Painel de engajamento (dados, sem LLM)")
    p = app.painel()
    print(f"{p['total']} pessoas · {p['metas_total']} metas · {p['metas_concluidas']} concluídas · "
          f"{p['metas_atrasadas']} vencidas ({p['pessoas_atrasadas']} pessoas) · engajamento médio {p['engajamento_medio']}")

    titulo("3. RBAC: colaborador tenta rodar o follow-up da equipe")
    try:
        app.motor.executar("followup_metas", {}, bruno)
    except PermissaoNegada as e:
        print(f"negado e auditado: {e}")

    titulo("4. Componente 'follow-up' -> workflow followup_metas")
    r = app.motor.executar("followup_metas", {}, ana)
    print(f"run {r['run_id']} · nós: {' -> '.join(x['no'] + ':' + x['tipo'] for x in r['trilha'])}")
    print(f"{len(r['propostas'])} rascunhos aguardando aprovação; enviados até agora: {len(app.caixa.enviados())}")
    primeiro = r["propostas"][0]
    print("\n--- rascunho para", primeiro["payload"]["para"], "---\n" + primeiro["payload"]["corpo"])

    titulo("5. Humano no comando: Ana edita e aprova 1, rejeita 1")
    editado = primeiro["payload"]["corpo"].replace("Que tal 20 minutos", "Podemos tomar um café e usar 20 minutos")
    app.fila.aprovar(primeiro["id"], ana, {"corpo": editado})
    app.fila.rejeitar(r["propostas"][1]["id"], ana, "já conversamos ontem")
    print(f"enviados: {len(app.caixa.enviados())} (com edição) · pendentes: {len(app.fila.pendentes())}")

    titulo("6. Assistente de RH: política codificada, escopo mínimo")
    perguntas = [("carla", "Quantos dias de férias eu tenho?"),
                 ("bruno", "Posso dividir minhas férias em 10 e 10 dias, pedindo com 15 dias de antecedência?"),
                 ("elisa", "Vou adotar uma criança, quantos dias de licença tenho?"),
                 ("bruno", "Onde vejo meu holerite?")]
    for pessoa, q in perguntas:
        s = app.motor.executar("assistente_rh", {"colaborador_id": pessoa, "pergunta": q},
                               bruno if pessoa == "bruno" else app.usuario("rosa"))["saida"]
        extra = f" · ferramentas ofertadas: {s['ferramentas_ofertadas']}" if s.get("ferramenta") else ""
        print(f"[{s['categoria']} · {s['fonte']}{extra}]\n  P: {q}\n  R: {s['resposta']}")

    titulo("7. Gatilho agendado: segunda 08:00 -> agente de fundo")
    [rag] = app.gatilhos.tick(datetime(2026, 10, 19, 8, 0))
    sug = app.guardar_sugestoes(rag)
    print(f"run {rag['run_id']} · {len(sug)} sugestões de próximos passos:")
    for s in sug[:4]:
        print(f"  [p{s['prioridade']}] {s['titulo']}  -> {s['workflow']}")
    r2 = app.executar_sugestao(sug[0]["id"], ana)
    print(f"executou '{sug[0]['id']}': {len(r2['propostas'])} convite na fila (não enviado)")

    titulo("8. Gatilho por evento: e-mail recebido")
    [rev] = app.gatilhos.emitir("email.recebido", {"de": "lucas.martins@exemplo.com", "remetente_id": "lucas",
                                                  "corpo": "Oi RH, quantos dias de férias eu tenho direito?"})
    print(f"run {rev['run_id']} · resposta proposta para {rev['propostas'][0]['payload']['para']}: "
          f"{rev['saida']['resposta']}")

    titulo("9. Saída visual: relatório")
    rr = app.motor.executar("relatorio_equipe", {}, ana)
    print(rr["saida"]["resumo"])
    print("gerados:", ", ".join(f"{pasta}/{a}" for a in rr["saida"]["artefatos"]))

    titulo("Auditoria")
    linhas = app.audit.ler()
    execs = [l for l in linhas if l["evento"] == "workflow.executado"]
    print(f"{len(linhas)} linhas em {pasta}/audit.jsonl · {len(execs)} execuções de "
          f"{len({l['workflow'] for l in execs})} workflows · corrente de hash íntegra: {app.audit.verificar_corrente()}")
    print(f"e-mails enviados (simulado): {len(app.caixa.enviados())} em {pasta}/caixa_saida.jsonl · "
          f"aguardando aprovação: {len(app.fila.pendentes())}")
    titulo("10. Painel executivo (diretoria): resultado, controle e custo")
    try:
        app.executivo(bruno)
    except PermissaoNegada as e:
        print(f"negado e auditado: {e}")
    rex = app.executivo(app.usuario("dora"))
    for linha in resumo_texto(rex["saida"]):
        print(linha)
    print("gerados:", ", ".join(f"{pasta}/{a}" for a in rex["saida"]["artefatos"]))

    print("\nPainel web: python3 -m agentic_app.serve  ->  http://127.0.0.1:8765  "
          "(executivo: http://127.0.0.1:8765/executivo?usuario=dora)")


if __name__ == "__main__":
    main()
