"""Centro de Comando (1.3.0): Agent Control Tower + Mission Control, com ações."""
import json
from datetime import datetime

from agentic_app import comando
from agentic_app.apps.coaching import montar
from agentic_app.esquema import validar
from agentic_app.seguranca import PermissaoNegada
from agentic_app.serve import tratar
from agentic_app.workflow import ErroWorkflow, WorkflowPausado
from tests.base import BaseApp, relogio_fixo
from tests.test_executivo import cenario_demo

DEPOIS = "2026-10-16T13:00:00+00:00"   # ~25 h depois do relógio fixo dos testes (12:00 do dia 15)
MESMO_DIA = "2026-10-15T13:00:00+00:00"


class TestCentroDeComando(BaseApp):
    def setUp(self):
        super().setUp()
        self.otavio, self.dora = self.app.usuario("otavio"), self.app.usuario("dora")
        cenario_demo(self.app)

    def cmd(self, quem=None, agora=DEPOIS):
        return self.app.comando(quem or self.otavio, agora=agora)["saida"]

    def wf(self, d, wid):
        return next(w for w in d["agentes"]["workflows"] if w["id"] == wid)

    # ---------------------------------------------------------------- acesso
    def test_quem_ve_e_quem_e_barrado(self):
        for u in (self.otavio, self.ana, self.dora):
            self.assertIn(self.cmd(u)["saude"], comando.SAUDE)
        for u in (self.bruno, self.app.usuario("estela")):
            with self.assertRaises(PermissaoNegada):
                self.cmd(u)
            ult = self.app.audit.ler()[-1]
            self.assertEqual((ult["evento"], ult["workflow"], ult["usuario"]), ("workflow.negado", "centro_comando", u.id))

    def test_botoes_seguem_o_papel_de_quem_ve(self):
        op, gestor = self.cmd(self.otavio)["pode"], self.cmd(self.ana)["pode"]
        self.assertEqual((op["controlar"], op["aprovar"]), (True, False))
        self.assertEqual((gestor["controlar"], gestor["aprovar"]), (False, True))
        self.assertFalse(op["acionar"]["convite_1a1"])
        self.assertTrue(gestor["acionar"]["convite_1a1"])

    def test_gestor_nao_controla_agentes_e_a_negativa_e_auditada(self):
        with self.assertRaises(PermissaoNegada):
            self.app.pausar("followup_metas", self.ana)
        ult = self.app.audit.ler()[-1]
        self.assertEqual((ult["evento"], ult["acao"], ult["usuario"]), ("comando.negado", "pausar", "ana"))
        self.assertFalse(self.app.controle.pausado("followup_metas"))
        neg = self.app.executivo(self.dora)["saida"]["controle"]["negados_por_papel"]
        self.assertEqual(neg.get("gestor"), 1)

    # ---------------------------------------------------------------- pausar / retomar
    def test_pausado_bloqueia_clique_e_registra(self):
        self.app.pausar("followup_metas", self.otavio, "texto saindo errado")
        with self.assertRaises(WorkflowPausado):
            self.app.motor.executar("followup_metas", {}, self.ana)
        ult = self.app.audit.ler()[-1]
        self.assertEqual((ult["evento"], ult["status"]), ("workflow.executado", "pausado"))
        w = self.wf(self.cmd(), "followup_metas")
        self.assertEqual((w["estado"], w["semaforo"], w["bloqueados"]), ("pausado", "pausado", 1))
        self.assertEqual(w["pausa"]["motivo"], "texto saindo errado")
        self.assertTrue(any("followup_metas está pausado" in a["texto"] for a in self.cmd()["alertas"]))
        with self.assertRaises(ValueError):
            self.app.pausar("followup_metas", self.otavio)  # já pausado
        self.app.retomar("followup_metas", self.otavio)
        self.assertEqual(self.app.motor.executar("followup_metas", {}, self.ana)["status"], "ok")

    def test_pausa_nao_derruba_os_outros_agendados(self):
        self.app.pausar("proximos_passos", self.otavio)
        self.assertEqual(self.app.gatilhos.tick(datetime(2026, 10, 26, 8, 0)), [])
        ult = self.app.audit.ler()[-1]
        self.assertEqual((ult["workflow"], ult["status"]), ("proximos_passos", "pausado"))
        [snap] = self.app.gatilhos.tick(datetime(2026, 10, 26, 7, 0))   # outro workflow agendado segue
        self.assertEqual(snap["workflow"], "snapshot_indicadores")
        self.app.retomar("proximos_passos", self.otavio)
        self.assertEqual(len(self.app.gatilhos.tick(datetime(2026, 11, 2, 8, 0))), 1)

    def test_pausa_sobrevive_a_reinicio(self):
        self.app.pausar("convite_1a1", self.otavio)
        outro = montar(self.pasta, relogio=relogio_fixo())
        self.assertTrue(outro.controle.pausado("convite_1a1"))

    # ---------------------------------------------------------------- rodar / reexecutar
    def test_rodar_agora_usa_o_usuario_do_gatilho(self):
        r = self.app.rodar_agora("proximos_passos", self.otavio)
        self.assertEqual(r["status"], "ok")
        ult = [l for l in self.app.audit.ler() if l.get("run_id") == r["run_id"]][-1]
        self.assertEqual((ult["usuario"], ult["gatilho"]), ("sistema", "comando:rodar:otavio"))
        self.assertEqual(self.app.sugestoes, r["saida"]["sugestoes"])
        with self.assertRaises(ValueError):
            self.app.rodar_agora("convite_1a1", self.otavio)  # sem gatilho agendado

    def test_reexecutar_so_o_que_nao_exige_guardar_entrada(self):
        runs = {l["workflow"]: l["run_id"] for l in self.app.audit.ler() if l.get("evento") == "workflow.executado"}
        r = self.app.reexecutar(runs["relatorio_equipe"], self.otavio)   # entrada vazia -> como sistema
        self.assertNotEqual(r["run_id"], runs["relatorio_equipe"])
        self.assertEqual(self.app.audit.ler()[-1]["gatilho"], f"comando:reexecucao:{runs['relatorio_equipe']}")
        with self.assertRaisesRegex(ValueError, "entrada não guardada"):
            self.app.reexecutar(runs["assistente_rh"], self.otavio)
        with self.assertRaisesRegex(ValueError, "entrada não guardada"):
            self.app.reexecutar(runs["convite_1a1"], self.otavio)        # tem liderado_id
        rex = self.app.executivo(self.dora)                               # entrada vazia, mas sistema não executa
        with self.assertRaisesRegex(ValueError, "só quem tem o papel"):
            self.app.reexecutar(rex["run_id"], self.otavio)
        r2 = self.app.reexecutar(runs["proximos_passos"], self.otavio)  # agendado: entrada do gatilho
        self.assertEqual(r2["workflow"], "proximos_passos")

    def test_falha_vira_vermelho_e_reexecucao_corrige(self):
        boa = self.app.registro.funcoes["agregar_equipe"]
        self.app.registro.funcoes["agregar_equipe"] = lambda equipe: 1 / 0
        with self.assertRaises(ErroWorkflow):
            self.app.motor.executar("relatorio_equipe", {}, self.ana)
        d = self.cmd()
        w = self.wf(d, "relatorio_equipe")
        self.assertEqual(w["semaforo"], "vermelho")
        self.assertEqual(d["saude"], "vermelho")
        self.assertEqual(d["alertas"][0]["nivel"], "critico")
        self.assertIn("relatorio_equipe", d["alertas"][0]["texto"])
        prob = d["agentes"]["problemas"][0]
        self.assertEqual((prob["tipo"], prob["reexecutar"]["pode"]), ("erro", True))
        self.app.registro.funcoes["agregar_equipe"] = boa
        self.app.reexecutar(prob["run_id"], self.otavio)
        self.assertEqual(self.wf(self.cmd(), "relatorio_equipe")["semaforo"], "amarelo")  # voltou, com histórico de erro

    # ---------------------------------------------------------------- fila e escalada
    def test_sla_da_fila_depende_de_agora(self):
        self.assertTrue(all(x["vencida"] for x in self.cmd(agora=DEPOIS)["agentes"]["fila"]))
        self.assertFalse(any(x["vencida"] for x in self.cmd(agora=MESMO_DIA)["agentes"]["fila"]))
        fila = self.cmd()["agentes"]["fila"]
        self.assertEqual(len(fila), len(self.app.fila.pendentes()))
        self.assertEqual([x["idade_h"] for x in fila], sorted((x["idade_h"] for x in fila), reverse=True))

    def test_escalar_marca_mas_nao_da_poder_de_aprovar(self):
        alvo = self.app.fila.pendentes()[0]["id"]
        self.app.escalar(alvo, self.otavio, "parado há mais de um dia")
        with self.assertRaises(PermissaoNegada):
            self.app.fila.aprovar(alvo, self.otavio)
        self.assertEqual(self.app.fila.obter(alvo)["status"], "aguardando_aprovacao")
        x = next(i for i in self.cmd()["agentes"]["fila"] if i["id"] == alvo)
        self.assertTrue(x["escalada"])
        self.app.fila.aprovar(alvo, self.ana)
        with self.assertRaises(ValueError):
            self.app.escalar(alvo, self.otavio)

    # ---------------------------------------------------------------- negócio
    def test_mission_control_bate_com_o_executivo(self):
        n = self.cmd(self.dora)["negocio"]
        ex = self.app.executivo(self.dora)["saida"]["negocio"]["metricas"]
        self.assertEqual([(m["id"], m["valor"], m["atingiu"]) for m in n["metricas"]],
                         [(m["id"], m["valor"], m["atingiu"]) for m in ex])
        self.assertEqual(n["faltam"], 4)   # 90% de 7 vencidas = 7 (arredonda para cima) - 3 cobertas
        ordem = [x["situacao"] for x in n["decisoes"]]
        pesos = {"sem_acao": 0, "rejeitado": 1, "rascunho_pendente": 2, "enviado": 3}
        self.assertEqual(ordem, sorted(ordem, key=pesos.get))
        enviados = {e["para"] for e in self.app.caixa.enviados()}
        for x in n["decisoes"]:
            email = next(p["email"] for p in self.app.equipe["liderados"] if p["id"] == x["id"])
            if x["situacao"] == "enviado":
                self.assertIn(email, enviados)

    def test_acionar_pela_tela_muda_a_situacao_da_pessoa(self):
        n = self.cmd(self.ana)["negocio"]
        alvo = next(x for x in n["decisoes"] if x["proxima"]["tipo"] == "acionar")
        st, _, corpo = tratar("POST", f"/api/workflow/{alvo['proxima']['workflow']}",
                              json.dumps({"entrada": alvo["proxima"]["entrada"]}).encode(), "ana", a=self.app)
        self.assertEqual(st, 200, corpo)
        depois = next(x for x in self.cmd(self.ana)["negocio"]["decisoes"] if x["id"] == alvo["id"])
        self.assertEqual(depois["situacao"], "rascunho_pendente")
        self.assertEqual(depois["proxima"]["tipo"], "aprovar")

    # ---------------------------------------------------------------- rotas, esquema, audit
    def test_rotas_get_e_post(self):
        st, _, corpo = tratar("GET", f"/comando?usuario=otavio&agora={DEPOIS}", uid="bruno", a=self.app)
        self.assertEqual(st, 200)
        for trecho in ("Control Tower", "Mission Control", "Execuções por dia", 'data-acao="pausar"', "<svg"):
            self.assertIn(trecho.encode(), corpo)
        st, _, corpo = tratar("GET", f"/comando/negocio?usuario=ana&agora={DEPOIS}", uid="bruno", a=self.app)
        self.assertEqual(st, 200)
        self.assertIn("Fila de decisão".encode(), corpo)
        st, _, corpo = tratar("GET", "/comando", uid="bruno", a=self.app)
        self.assertEqual(st, 403)
        self.assertIn(b"Acesso negado", corpo)
        st, _, _ = tratar("POST", "/api/comando/pausar/followup_metas", b'{"motivo":"x"}', "ana", a=self.app)
        self.assertEqual(st, 403)
        st, _, _ = tratar("POST", "/api/comando/pausar/followup_metas", b'{"motivo":"x"}', "otavio", a=self.app)
        self.assertEqual(st, 200)
        st, _, _ = tratar("POST", "/api/workflow/followup_metas", b"{}", "ana", a=self.app)
        self.assertEqual(st, 409)
        st, _, _ = tratar("POST", "/api/comando/pausar/nao_existe", b"{}", "otavio", a=self.app)
        self.assertEqual(st, 404)
        st, _, corpo = tratar("GET", f"/api/comando?agora={DEPOIS}", uid="otavio", a=self.app)
        self.assertTrue(validar(json.loads(corpo), comando.ESQUEMA))

    def test_corrente_quebrada_e_critica_e_deterministico(self):
        a, b = self.cmd(), self.cmd()
        self.assertEqual(a["negocio"], b["negocio"])
        self.assertEqual(a["alertas"], b["alertas"])
        arq = self.app.pasta / "audit.jsonl"
        linhas = arq.read_text(encoding="utf-8").splitlines()
        x = json.loads(linhas[1])
        x["usuario"] = "outra-pessoa"
        linhas[1] = json.dumps(x, ensure_ascii=False, sort_keys=True)
        arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        d = self.cmd()
        self.assertEqual((d["saude"], d["alertas"][0]["nivel"]), ("vermelho", "critico"))
        self.assertIn("linha 2", d["alertas"][0]["texto"])

    def test_consultar_o_comando_nao_infla_a_operacao_do_executivo(self):
        antes = self.app.executivo(self.dora)["saida"]["operacao"]["execucoes"]
        for _ in range(3):
            self.cmd()
        self.assertEqual(self.app.executivo(self.dora)["saida"]["operacao"]["execucoes"], antes)
        feed = self.cmd()["agentes"]["eventos"]
        self.assertFalse(any("centro_comando" in e["texto"] for e in feed))

    def test_run_id_nao_repete_depois_de_reiniciar(self):
        usados = {l["run_id"] for l in self.app.audit.ler() if "run_id" in l}
        outro = montar(self.pasta, relogio=relogio_fixo())
        r = outro.motor.executar("relatorio_equipe", {}, self.ana)
        self.assertNotIn(r["run_id"], usados)

    def test_proximo_disparo(self):
        g = {"dia_semana": "seg", "hora": "08:00"}
        self.assertEqual(comando.proximo_disparo(g, datetime(2026, 10, 15, 9, 0)), datetime(2026, 10, 19, 8, 0))
        self.assertEqual(comando.proximo_disparo(g, datetime(2026, 10, 19, 8, 0)), datetime(2026, 10, 19, 8, 0))
        self.assertEqual(comando.proximo_disparo(g, datetime(2026, 10, 19, 8, 1)), datetime(2026, 10, 26, 8, 0))
