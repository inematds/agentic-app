"""Painel de tendências (1.2.0): matemática, projeção, sinais, snapshot semanal e RBAC."""
import json
import pathlib
from datetime import date, datetime

from agentic_app import tendencias as T
from agentic_app.llm import FakeLLM
from agentic_app.seguranca import PermissaoNegada
from agentic_app.serve import tratar
from tests.base import BaseApp

RAIZ = pathlib.Path(__file__).resolve().parent.parent
HIST = json.loads((RAIZ / "agentic_app/apps/coaching/data/historico.json").read_text(encoding="utf-8"))["semanas"]


def cfg_min(**extra):
    c = {"horizonte_fim": "2026-12-31", "rotulo_horizonte": "fim do trimestre", "min_pontos": 4,
         "janela_media_movel": 4, "quedas_seguidas_alerta": 3,
         "metricas": [{"id": "x", "nome": "Indicador X", "grupo": "resultado", "unidade": "%", "meta": 20,
                       "sentido": "maior"}]}
    c.update(extra)
    return c


def hist(valores, inicio=date(2026, 1, 5)):
    return [{"semana": date.fromordinal(inicio.toordinal() + 7 * i).isoformat(), "x": v} for i, v in enumerate(valores)]


class TestMatematica(BaseApp):
    def test_regressao_e_projecao_batem_com_conta_manual(self):
        b, a = T.regressao([0, 1, 2, 3], [10, 12, 14, 16])
        self.assertEqual((b, a), (2.0, 10.0))
        d = T.analisar(hist([10, 12, 14, 16]), cfg_min())
        x = d["metricas"][0]
        self.assertEqual(x["ritmo_semana"], 2.0)
        # último ponto 26/01/2026, faltam (20 - 16) / 2 = 2 semanas -> 09/02/2026
        self.assertEqual((x["projecao"]["status"], x["projecao"]["data"]), ("atinge", "09/02/2026"))
        self.assertEqual(x["media_movel"], [10.0, 11.0, 12.0, 13.0])
        self.assertEqual((x["var_semana"], x["var_periodo"]), (2.0, 6.0))

    def test_projecao_do_app_bate_com_a_formula_nos_dados_de_exemplo(self):
        ys = [l["conversa_7d"] for l in HIST]
        xs = list(range(len(ys)))
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        d = self.app.tendencias(self.app.usuario("estela"))["saida"]
        m = next(x for x in d["metricas"] if x["id"] == "conversa_7d")
        self.assertEqual(m["ritmo_semana"], round(b, 3))
        semanas = (90 - ys[-1]) / round(b, 3)
        self.assertGreater(semanas * 7, (date(2026, 12, 31) - date(2026, 10, 12)).days)
        self.assertEqual(m["projecao"]["status"], "nao_atinge")
        self.assertIn("não é atingida até o fim do trimestre", m["projecao"]["texto"])

    def test_tres_quedas_seguidas_viram_sinal_duas_nao(self):
        tres = T.analisar(hist([15, 14, 13, 12]), cfg_min())
        self.assertEqual(tres["metricas"][0]["quedas_seguidas"], 3)
        self.assertTrue(any("caindo há 3 semanas seguidas" in s["texto"] for s in tres["sinais"]))
        duas = T.analisar(hist([12, 15, 14, 13]), cfg_min())
        self.assertEqual(duas["metricas"][0]["quedas_seguidas"], 2)
        self.assertFalse(any("semanas seguidas" in s["texto"] for s in duas["sinais"]))

    def test_historico_insuficiente_nao_projeta(self):
        d = T.analisar(hist([10, 12, 14]), cfg_min(cenarios=[]))
        p = d["metricas"][0]["projecao"]
        self.assertEqual(p["status"], "insuficiente")
        self.assertIn("Histórico insuficiente", p["texto"])
        self.assertNotIn("data", p)
        self.assertEqual(d["metricas"][0]["ritmo_semana"], 0.0)

    def test_meta_menor_e_ruptura_futura(self):
        c = cfg_min(metricas=[{"id": "x", "nome": "Risco", "grupo": "resultado", "unidade": "pessoas", "meta": 10,
                               "sentido": "menor"}])
        d = T.analisar(hist([4, 5, 6, 7]), c)
        p = d["metricas"][0]["projecao"]
        self.assertEqual(p["status"], "rompe")  # ainda na meta (7 <= 10), sobe 1/semana -> rompe em 3 semanas
        self.assertEqual(p["data"], "16/02/2026")

    def test_cenario_e_se_segue_a_regra_explicita(self):
        self.assertEqual(T.cenario_mais_1a1(42.9, 1.3, 3, 5, 6), 76.2)   # +2 conversas x 100/6
        self.assertEqual(T.cenario_mais_1a1(42.9, 1.3, 3, 9, 6), 100.0)  # teto
        d = self.app.tendencias(self.app.usuario("estela"))["saida"]
        c5 = next(c for c in d["cenarios"] if c["id"] == "1a1_5")
        self.assertEqual((c5["valor_hoje"], c5["valor_cenario"]), (42.9, 76.2))
        self.assertEqual(c5["projecao"]["status"], "atinge")


class TestPainelTendencias(BaseApp):
    def setUp(self):
        super().setUp()
        self.estela = self.app.usuario("estela")

    def test_barrado_por_papel_e_auditado(self):
        for u in (self.bruno, self.ana):
            with self.assertRaises(PermissaoNegada):
                self.app.tendencias(u)
            ult = self.app.audit.ler()[-1]
            self.assertEqual((ult["evento"], ult["workflow"], ult["usuario"]), ("workflow.negado", "painel_tendencias", u.id))
        self.assertEqual(self.app.tendencias(self.app.usuario("dora"))["status"], "ok")   # diretoria também vê
        with self.assertRaises(PermissaoNegada):
            self.app.executivo(self.estela)   # estratégia não vê o executivo

    def test_snapshot_semanal_forma_o_historico_sozinho(self):
        [r] = self.app.gatilhos.tick(datetime(2026, 10, 19, 7, 0))
        self.assertEqual(r["workflow"], "snapshot_indicadores")
        self.assertEqual(r["saida"]["semana"], "2026-10-12")   # segunda-feira da semana de 15/10
        vivo = T.ler_vivo(self.app.pasta / "historico.jsonl")
        self.assertEqual(len(vivo), 1)
        self.assertEqual(vivo[0]["conversa_7d"], 14.3)          # sem e-mail aprovado: só Gabriela (1:1 há 6 dias)
        self.app.gravar_snapshot()                              # mesma semana: substitui, não duplica
        self.assertEqual(len(T.ler_vivo(self.app.pasta / "historico.jsonl")), 1)
        d = self.app.tendencias(self.estela)["saida"]
        m = next(x for x in d["metricas"] if x["id"] == "conversa_7d")
        self.assertEqual(d["pontos"], 12)                       # vivo substitui a semana do exemplo
        self.assertEqual(m["ultimo"], 14.3)

    def test_sem_exemplo_so_o_vivo_e_insuficiente(self):
        self.app.cfg_tendencias["historico_exemplo"] = None
        self.app.gravar_snapshot()
        d = self.app.tendencias(self.estela)["saida"]
        self.assertFalse(d["exemplo"])
        self.assertEqual(d["pontos"], 1)
        self.assertTrue(all(m["projecao"]["status"] == "insuficiente" for m in d["metricas"]))
        self.assertTrue(all("insuficiente" in c["texto"] for c in d["cenarios"]))

    def test_comparacao_entre_pessoas_acha_quedas(self):
        d = self.app.tendencias(self.estela)["saida"]
        em_queda = sorted(p["id"] for p in d["pessoas"] if p["quedas_seguidas"] >= 3)
        self.assertEqual(em_queda, ["carla", "elisa", "henrique", "lucas"])
        self.assertEqual(d["pessoas"][0]["id"], "carla")        # pior ritmo primeiro (85 -> 64)

    def test_llm_so_costura_nunca_muda_numero(self):
        base = self.app.tendencias(self.estela)["saida"]

        class LLMInventa(FakeLLM):
            def redigir(self, modelo_texto, dados, instrucao, modelo):
                return "Tudo vai bater 99% amanhã."
        self.app.motor.llm = LLMInventa()
        outro = self.app.tendencias(self.estela)["saida"]
        self.assertEqual(outro["narrativa"], "Tudo vai bater 99% amanhã.")
        self.assertEqual(outro["metricas"], base["metricas"])
        self.assertEqual(outro["sinais"], base["sinais"])
        principal = next(m for m in base["metricas"] if m["id"] == "conversa_7d")
        self.assertIn(principal["projecao"]["texto"], base["narrativa"])

    def test_rota_html_e_pdf(self):
        st, _, corpo = tratar("GET", "/tendencias", uid="bruno", a=self.app)
        self.assertEqual(st, 403)
        st, _, corpo = tratar("GET", "/tendencias?usuario=estela", uid="bruno", a=self.app)
        self.assertEqual(st, 200)
        self.assertIn(b"<polyline", corpo)
        self.assertIn("Para onde os números estão indo".encode(), corpo)
        st, _, corpo = tratar("GET", "/api/tendencias", uid="estela", a=self.app)
        self.assertEqual(json.loads(corpo)["pontos"], 12)
        self.assertTrue((self.app.pasta / "tendencias.pdf").read_bytes().startswith(b"%PDF-1.4"))

    def test_template_e_config_coerentes(self):
        t = json.loads((RAIZ / "templates/tendencias.json").read_text(encoding="utf-8"))
        ind = {m["id"]: m for m in self.app.indicadores["metricas"]}
        for c in (t, self.app.cfg_tendencias):
            self.assertLessEqual({"acesso", "horizonte_fim", "min_pontos", "quedas_seguidas_alerta", "metricas"}, set(c))
            for m in c["metricas"]:
                self.assertIn(m["id"], T.CAMPOS_SNAPSHOT)
                self.assertIn(m["grupo"], ("resultado", "adocao", "custo", "risco"))
        for m in self.app.cfg_tendencias["metricas"]:
            if m["id"] in ind:
                self.assertEqual(m["meta"], ind[m["id"]]["meta"], m["id"])
        spec = self.app.motor.workflows["painel_tendencias"]
        self.assertEqual(spec["seguranca"]["executar"], self.app.cfg_tendencias["acesso"])
        self.assertTrue(json.loads((RAIZ / "agentic_app/apps/coaching/data/historico.json")
                                   .read_text(encoding="utf-8"))["exemplo"])
