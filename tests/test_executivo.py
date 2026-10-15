"""Painel executivo (1.1.0): números batem com a demo, controle e RBAC."""
import json
from datetime import datetime

from agentic_app import executivo
from agentic_app.esquema import ErroValidacao, validar
from agentic_app.llm import FakeLLM
from agentic_app.seguranca import PermissaoNegada
from agentic_app.serve import tratar
from tests.base import BaseApp


def cenario_demo(app):
    """Os mesmos passos de agentic_app/demo.py (seções 3 a 9)."""
    ana, bruno, rosa = app.usuario("ana"), app.usuario("bruno"), app.usuario("rosa")
    try:
        app.motor.executar("followup_metas", {}, bruno)
    except PermissaoNegada:
        pass
    r = app.motor.executar("followup_metas", {}, ana)
    p = r["propostas"]
    app.fila.aprovar(p[0]["id"], ana, {"corpo": p[0]["payload"]["corpo"] + " Podemos tomar um café?"})
    app.fila.rejeitar(p[1]["id"], ana, "já conversamos ontem")
    for pessoa, q in [("carla", "Quantos dias de férias eu tenho?"),
                      ("bruno", "Posso dividir minhas férias em 10 e 10 dias, pedindo com 15 dias de antecedência?"),
                      ("elisa", "Vou adotar uma criança, quantos dias de licença tenho?"),
                      ("bruno", "Onde vejo meu holerite?")]:
        app.motor.executar("assistente_rh", {"colaborador_id": pessoa, "pergunta": q}, bruno if pessoa == "bruno" else rosa)
    [rag] = app.gatilhos.tick(datetime(2026, 10, 19, 8, 0))
    sug = app.guardar_sugestoes(rag)
    app.executar_sugestao(sug[0]["id"], ana)
    app.gatilhos.emitir("email.recebido", {"de": "lucas.martins@exemplo.com", "remetente_id": "lucas",
                                           "corpo": "Oi RH, quantos dias de férias eu tenho direito?"})
    app.motor.executar("relatorio_equipe", {}, ana)


class TestPainelExecutivo(BaseApp):
    def setUp(self):
        super().setUp()
        self.dora = self.app.usuario("dora")
        cenario_demo(self.app)

    def ex(self):
        return self.app.executivo(self.dora)["saida"]

    def test_resultado_de_negocio_bate_com_os_dados(self):
        d = self.ex()
        m = {x["id"]: x for x in d["negocio"]["metricas"]}
        # 7 metas vencidas: Carla (2, recebeu o e-mail aprovado) + Gabriela (1, 1:1 há 6 dias) = 3 cobertas
        self.assertEqual(m["conversa_7d"]["valor"], 42.9)
        self.assertEqual(m["conversa_7d"]["detalhe"], "3 de 7 metas vencidas")
        self.assertFalse(m["conversa_7d"]["atingiu"])
        self.assertEqual(m["metas_concluidas"]["valor"], 31.2)          # 5 de 16
        self.assertEqual(m["pessoas_em_risco"]["valor"], 6)
        self.assertEqual(len(m["engajamento_medio"]["serie"]), 4)
        self.assertEqual(m["engajamento_medio"]["valor"], m["engajamento_medio"]["serie"][-1])
        self.assertTrue(m["engajamento_medio"]["atingiu"])

    def test_operacao_bate_com_o_audit_da_demo(self):
        op = self.ex()["operacao"]
        self.assertEqual(op["execucoes"], 9)
        self.assertEqual(op["por_workflow"], {"assistente_rh": 5, "convite_1a1": 1, "followup_metas": 1,
                                              "proximos_passos": 1, "relatorio_equipe": 1})
        self.assertEqual(op["por_gatilho"], {"clique": 7, "horario": 1, "evento": 1})
        r = op["rascunhos"]
        self.assertEqual((r["propostos"], r["aprovados_sem_edicao"], r["aprovados_com_edicao"], r["rejeitados"],
                          r["pendentes"]), (8, 0, 1, 1, 6))
        self.assertEqual((r["taxa_aprovacao"], r["taxa_edicao"], r["taxa_rejeicao"]), (50.0, 100.0, 50.0))
        self.assertEqual(op["sugestoes"], {"geradas": 10, "executadas": 1, "taxa": 10.0})
        self.assertEqual(op["tempo_ate_aprovacao"]["amostras"], 1)

    def test_custo_conta_cada_chamada_do_llm_e_usa_a_tabela(self):
        chamadas_reais = len(self.app.motor.llm.chamadas)
        c = self.ex()["custo"]
        self.assertEqual(c["chamadas"], chamadas_reais)          # o FakeLLM conta igual a um modelo real
        self.assertEqual(sum(v["chamadas"] for v in c["por_modelo"].values()), chamadas_reais)
        self.assertEqual(c["custo_total"], 0)
        self.app.indicadores["custo_por_modelo"]["modelos"]["medio"]["por_chamada"] = 0.01
        c2 = self.ex()["custo"]
        self.assertAlmostEqual(c2["custo_total"], c2["por_modelo"]["medio"]["chamadas"] * 0.01, places=4)

    def test_todas_as_acoes_externas_com_aprovacao(self):
        ctl = self.ex()["controle"]
        self.assertEqual((ctl["acoes_externas"], ctl["acoes_com_aprovacao"], ctl["pct_com_aprovacao"]), (1, 1, 100.0))
        self.assertTrue(ctl["corrente_integra"])
        self.assertEqual(ctl["negados_por_papel"], {"colaborador": 1})

    def test_envio_sem_aprovacao_derruba_os_100_e_vira_alerta_critico(self):
        self.app.caixa.enviar_email({"para": "x@exemplo.com", "assunto": "atalho", "corpo": "saiu sem fila"})
        d = self.ex()
        self.assertEqual(d["controle"]["pct_com_aprovacao"], 50.0)
        self.assertEqual(d["alertas"][0]["nivel"], "critico")
        self.assertIn("sem aprovação", d["alertas"][0]["texto"])

    def test_corrente_de_hash_quebrada_aparece_como_alerta(self):
        arq = self.app.pasta / "audit.jsonl"
        linhas = arq.read_text(encoding="utf-8").splitlines()
        adulterada = json.loads(linhas[2])
        adulterada["aprovado_por"] = "outra-pessoa"
        linhas[2] = json.dumps(adulterada, ensure_ascii=False, sort_keys=True)
        arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        d = self.ex()
        self.assertFalse(d["controle"]["corrente_integra"])
        self.assertEqual(d["controle"]["quebra_na_linha"], 3)
        self.assertEqual(d["alertas"][0]["nivel"], "critico")
        self.assertIn("linha 3", d["alertas"][0]["texto"])

    def test_colaborador_e_gestor_barrados_e_auditados(self):
        for u in (self.bruno, self.ana):
            with self.assertRaises(PermissaoNegada):
                self.app.executivo(u)
            ult = self.app.audit.ler()[-1]
            self.assertEqual((ult["evento"], ult["workflow"], ult["usuario"]), ("workflow.negado", "painel_executivo", u.id))
        self.assertEqual(self.ex()["controle"]["negados_por_papel"], {"colaborador": 2, "gestor": 1})

    def test_rota_executivo_respeita_o_papel(self):
        st, tipo, corpo = tratar("GET", "/executivo", uid="bruno", a=self.app)
        self.assertEqual(st, 403)
        self.assertIn(b"Acesso negado", corpo)
        st, tipo, corpo = tratar("GET", "/executivo?usuario=dora", uid="bruno", a=self.app)
        self.assertEqual(st, 200)
        self.assertIn("Metas vencidas com conversa".encode(), corpo)
        self.assertIn(b"<svg", corpo)
        st, _, _ = tratar("GET", "/saida/executivo.html", uid="ana", a=self.app)
        self.assertEqual(st, 404)  # arquivo do executivo não vaza pela rota de arquivos
        st, _, corpo = tratar("GET", "/api/executivo", uid="dora", a=self.app)
        self.assertEqual(json.loads(corpo)["controle"]["acoes_externas"], 1)

    def test_saida_valida_no_esquema_e_alertas_deterministicos(self):
        a, b = self.ex(), self.ex()
        self.assertEqual(a.pop("artefatos"), ["executivo.html", "executivo.pdf"])  # o motor acrescenta depois
        self.assertTrue(validar(a, executivo.ESQUEMA))
        self.assertTrue(3 <= len(a["alertas"]) <= executivo.MAX_ALERTAS)
        self.assertEqual([x["texto"] for x in a["alertas"][:3]], [x["texto"] for x in b["alertas"][:3]])
        quebrado = json.loads(json.dumps(a))
        quebrado["controle"]["pct_com_aprovacao"] = 120
        with self.assertRaises(ErroValidacao):
            validar(quebrado, executivo.ESQUEMA)

    def test_meta_atingida_muda_status_e_frase(self):
        cfg = next(m for m in self.app.indicadores["metricas"] if m["id"] == "conversa_7d")
        cfg["meta"] = 40
        d = self.ex()
        prin = next(m for m in d["negocio"]["metricas"] if m["id"] == "conversa_7d")
        self.assertTrue(prin["atingiu"])
        self.assertTrue(any(x["texto"].startswith("Resultado de negócio na meta") for x in d["alertas"]))

    def test_ferramenta_fora_do_escopo_conta_como_barrada(self):
        class LLMIntrometido(FakeLLM):
            def escolher_ferramenta(self, pergunta, ferramentas, modelo):
                return "licenca_parental"
        llm_ok = self.app.motor.llm
        self.app.motor.llm = LLMIntrometido()
        with self.assertRaises(PermissaoNegada):
            self.rh("bruno", "Quantos dias de férias eu tenho?")
        self.app.motor.llm = llm_ok
        d = self.ex()
        self.assertEqual(d["controle"]["ferramentas_barradas"], 1)
        self.assertTrue(any("escopo mínimo barrou 1" in x["texto"] for x in d["alertas"]))

    def test_painel_gera_html_e_pdf(self):
        r = self.app.executivo(self.dora)
        self.assertEqual(r["saida"]["artefatos"], ["executivo.html", "executivo.pdf"])
        self.assertTrue((self.app.pasta / "executivo.pdf").read_bytes().startswith(b"%PDF-1.4"))
        html = (self.app.pasta / "executivo.html").read_text(encoding="utf-8")
        for trecho in ("Resultado de negócio", "Operação dos agentes", "Controle e risco", "Custo e uso de LLM"):
            self.assertIn(trecho, html)

    def test_acesso_do_config_bate_com_o_workflow(self):
        spec = self.app.motor.workflows["painel_executivo"]
        self.assertEqual(spec["seguranca"]["executar"], self.app.indicadores["acesso"])
