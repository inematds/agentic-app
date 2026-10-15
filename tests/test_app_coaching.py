"""App de referência: assistente de RH, agente de fundo, gatilhos, relatório e painel."""
from datetime import datetime

from agentic_app.llm import FakeLLM
from agentic_app.seguranca import PermissaoNegada
from agentic_app.serve import tratar
from tests.base import BaseApp


class TestAssistenteRH(BaseApp):
    def test_ferias_por_tempo_de_casa_vem_da_politica(self):
        casos = {"carla": 35, "elisa": 32, "lucas": 30, "diego": 20, "henrique": 10}
        for pessoa, dias in casos.items():
            r = self.rh(pessoa, "Quantos dias de férias eu tenho?")
            self.assertEqual(r["saida"]["resultado"]["dias"], dias, pessoa)

    def test_escopo_minimo_so_ferramentas_da_categoria(self):
        r = self.rh("bruno", "Quantos dias de férias eu tenho?")
        self.assertEqual(r["saida"]["ferramentas_ofertadas"], ["dias_de_ferias", "validar_pedido_ferias"])
        r = self.rh("elisa", "Vou adotar uma criança, quantos dias de licença tenho?")
        self.assertEqual(r["saida"]["ferramentas_ofertadas"], ["licenca_parental"])
        self.assertEqual(r["saida"]["resultado"]["dias"], 180)

    def test_agente_que_pede_ferramenta_fora_do_escopo_e_barrado(self):
        class LLMIntrometido(FakeLLM):
            def escolher_ferramenta(self, pergunta, ferramentas, modelo):
                return "licenca_parental"  # não foi ofertada numa pergunta de férias
        self.app.motor.llm = LLMIntrometido()
        with self.assertRaises(PermissaoNegada):
            self.rh("bruno", "Quantos dias de férias eu tenho?")

    def test_pedido_fracionado_reprovado_explica_a_regra(self):
        r = self.rh("bruno", "Posso dividir minhas férias em 10 e 10 dias, pedindo com 15 dias de antecedência?")
        self.assertEqual(r["saida"]["ferramenta"], "validar_pedido_ferias")
        self.assertFalse(r["saida"]["resultado"]["aprovado"])
        self.assertIn("F5", r["saida"]["resposta"])

    def test_pergunta_aberta_vai_para_faq_nao_critica(self):
        r = self.rh("bruno", "Onde vejo meu holerite?")
        self.assertEqual(r["saida"]["fonte"], "busca_faq")
        self.assertFalse(r["saida"]["critica"])

    def test_colaborador_so_pergunta_do_proprio_perfil(self):
        self.assertEqual(self.rh("bruno", "Quantos dias de férias eu tenho?", self.bruno)["status"], "ok")
        with self.assertRaises(PermissaoNegada):
            self.rh("carla", "Quantos dias de férias eu tenho?", self.bruno)


class TestAgenteDeFundoEGatilhos(BaseApp):
    def test_agente_sugere_e_executar_ainda_exige_aprovacao(self):
        r = self.app.motor.executar("proximos_passos", {}, self.sistema)
        sug = self.app.guardar_sugestoes(r)
        self.assertEqual(len(sug), 10)
        self.assertEqual(sug[0]["id"], "s-carla-1a1")  # dois sinais = prioridade 1
        r2 = self.app.executar_sugestao("s-lucas-1a1", self.ana)
        self.assertEqual(r2["propostas"][0]["status"], "aguardando_aprovacao")
        self.assertEqual(self.app.caixa.enviados(), [])

    def test_agendado_roda_segunda_8h_uma_vez(self):
        segunda = datetime(2026, 10, 19, 8, 0)
        self.assertEqual([r["workflow"] for r in self.app.gatilhos.tick(segunda)], ["proximos_passos"])
        self.assertEqual(self.app.gatilhos.tick(segunda), [])                      # mesma janela
        self.assertEqual(self.app.gatilhos.tick(datetime(2026, 10, 20, 8, 0)), [])  # terça
        sexta = self.app.gatilhos.tick(datetime(2026, 10, 23, 17, 0))
        self.assertEqual([r["workflow"] for r in sexta], ["relatorio_equipe"])
        self.assertTrue(self.app.audit.ler()[-1]["gatilho"].startswith("agendado:"))

    def test_evento_email_recebido_responde_via_fila(self):
        [r] = self.app.gatilhos.emitir("email.recebido", {"de": "lucas.martins@exemplo.com", "remetente_id": "lucas",
                                                          "corpo": "Quantos dias de férias eu tenho?"})
        self.assertEqual(r["saida"]["resultado"]["dias"], 30)
        self.assertEqual(len(r["propostas"]), 1)
        self.assertEqual(r["propostas"][0]["payload"]["para"], "lucas.martins@exemplo.com")
        self.assertEqual(self.app.audit.ler()[-1]["gatilho"], "evento:email.recebido")


class TestRelatorioEPainel(BaseApp):
    def test_relatorio_gera_html_e_pdf(self):
        r = self.app.motor.executar("relatorio_equipe", {}, self.ana)
        self.assertEqual(r["saida"]["artefatos"], ["relatorio.html", "relatorio.pdf"])
        html = (self.app.pasta / "relatorio.html").read_text(encoding="utf-8")
        self.assertIn("Carla Mendes", html)
        self.assertIn("<svg", html)
        self.assertTrue((self.app.pasta / "relatorio.pdf").read_bytes().startswith(b"%PDF-1.4"))

    def test_painel_numeros(self):
        p = self.app.painel()
        self.assertEqual((p["total"], p["metas_total"], p["metas_atrasadas"], p["pessoas_atrasadas"]), (12, 16, 7, 6))

    def test_servidor_sem_socket(self):
        st, tipo, corpo = tratar("GET", "/", a=self.app)
        self.assertEqual(st, 200)
        self.assertIn(b"Coaching de gestor", corpo)
        st, _, _ = tratar("POST", "/api/workflow/followup_metas", b'{"entrada":{}}', "bruno", a=self.app)
        self.assertEqual(st, 403)
        st, _, _ = tratar("POST", "/api/workflow/followup_metas", b'{"entrada":{}}', "ana", a=self.app)
        self.assertEqual(st, 200)
        st, _, corpo = tratar("POST", "/api/acoes/acao-0001/aprovar", b'{"edicoes":{}}', "ana", a=self.app)
        self.assertEqual(st, 200)
        self.assertEqual(len(self.app.caixa.enviados()), 1)
