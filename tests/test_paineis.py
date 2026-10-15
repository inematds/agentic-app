"""Painéis no layout de BI (1.4.0): simulação, filtros, gráficos, rotas e o snapshot de 7 dias."""
import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime
from urllib.parse import quote

from agentic_app import graficos as G
from agentic_app import visao as V
from agentic_app.serve import tratar
from agentic_app.simular import simular
from agentic_app.tendencias import ler_vivo

FIM = datetime(2026, 10, 15, 17, 30).astimezone()
AGORA = FIM.isoformat(timespec="minutes")
QA = "agora=" + quote(AGORA)


class TestPaineisBI(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="agentic-bi-")
        self._antiga = os.environ.get("AGENTIC_SAIDA")
        os.environ["AGENTIC_SAIDA"] = self.pasta
        self.app, _, self.cont = simular(self.pasta, semanas=8, fim=FIM)

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)
        if self._antiga is None:
            os.environ.pop("AGENTIC_SAIDA", None)
        else:
            os.environ["AGENTIC_SAIDA"] = self._antiga

    def op(self, ignorar=("centro_comando", "painel_executivo", "painel_tendencias"), **f):
        audit = self.app.audit.ler()
        wfs = {l.get("workflow") for l in audit}
        return V.operacao(audit, self.app.fila.itens, V.normalizar(f, wfs), FIM, ignorar=ignorar)

    def get(self, rota, uid):
        st, _, corpo = tratar("GET", rota, uid=uid, a=self.app)
        return st, corpo.decode()

    # ---------------------------------------------------------------- simulação
    def test_simulacao_usa_o_motor_de_verdade_e_e_deterministica(self):
        audit = self.app.audit.ler()
        self.assertTrue(self.app.audit.verificar_corrente())
        status = {l.get("status") for l in audit if l.get("evento") == "workflow.executado"}
        self.assertLessEqual({"ok", "erro", "pausado"}, status)
        self.assertTrue(any(l["evento"] == "workflow.negado" for l in audit))
        self.assertTrue(any(l["evento"] == "comando.escalar" for l in audit))
        dias = {l["ts"][:10] for l in audit}
        self.assertGreater(len(dias), 40)                         # espalhado em semanas, não num dia só
        outra = tempfile.mkdtemp(prefix="agentic-bi2-")
        try:
            app2, _, cont2 = simular(outra, semanas=8, fim=FIM)
            self.assertEqual(cont2, self.cont)
            self.assertEqual(app2.audit.ler()[-1]["hash"], audit[-1]["hash"])
        finally:
            shutil.rmtree(outra, ignore_errors=True)

    # ---------------------------------------------------------------- filtros e agregação
    def test_totais_batem_entre_cartoes_e_graficos(self):
        v = self.op()
        k = v["kpis"]
        self.assertEqual(k["execucoes"], sum(v["por_situacao"].values()))
        self.assertEqual(k["execucoes"], sum(sum(x[s] for s in V.SITUACOES_EXEC) for x in v["por_dia"]))
        self.assertEqual(k["execucoes"], sum(v["por_gatilho"].values()))
        self.assertEqual(k["falhas"], v["por_situacao"]["falha"])
        self.assertEqual(k["fila"], sum(v["fila_idade"].values()))
        self.assertEqual(len(v["por_dia"]), 56)

    def test_filtros_restringem_o_detalhe_mas_o_grafico_do_filtro_mostra_todas_as_opcoes(self):
        v = self.op(workflow="assistente_rh")
        self.assertTrue(v["detalhe"])
        self.assertTrue(all(x["workflow"] == "assistente_rh" for x in v["detalhe"]))
        self.assertGreater(len(v["por_workflow"]), 1)            # o gráfico de workflow ignora o próprio filtro
        f = self.op(situacao="falha")
        self.assertEqual(f["kpis"]["execucoes"], f["kpis"]["falhas"])
        self.assertTrue(all(x["situacao"] == "falha" for x in f["detalhe"]))
        dia = next(x["dia"] for x in self.op()["por_dia"] if x["ok"])
        d = self.op(dia=dia)
        self.assertTrue(all(x["ts"][:10] == dia for x in d["detalhe"]))

    def test_periodo_e_variacao(self):
        self.assertLess(self.op(periodo="7d")["kpis"]["execucoes"], self.op(periodo="8s")["kpis"]["execucoes"])
        self.assertIsNotNone(self.op(periodo="7d")["kpis"]["variacao"])
        self.assertIsNone(self.op(periodo="tudo")["kpis"]["variacao"])

    def test_valor_desconhecido_vira_padrao_nunca_erro(self):
        f = V.normalizar({"periodo": "xyz", "workflow": "nao_existe", "situacao": "<script>"}, {"assistente_rh"})
        self.assertEqual(f, {"periodo": "8s", "workflow": "", "gatilho": "", "situacao": "", "dia": ""})
        st, corpo = self.get(f"/comando?usuario=otavio&{QA}&periodo=xyz&situacao=%3Cscript%3E", "otavio")
        self.assertEqual(st, 200)
        self.assertNotIn("<script>alert", corpo)

    # ---------------------------------------------------------------- páginas
    def test_quatro_paineis_no_mesmo_layout(self):
        rotas = [(f"/comando?usuario=otavio&{QA}", "otavio"), (f"/comando/negocio?usuario=ana&{QA}", "ana"),
                 (f"/executivo?usuario=dora&{QA}", "dora"), ("/tendencias?usuario=estela", "estela")]
        for rota, uid in rotas:
            st, corpo = self.get(rota, uid)
            self.assertEqual(st, 200, rota)
            for trecho in ('class="paineis"', "Filtros", 'class="kpis"', "<svg", "aria-current=page"):
                self.assertIn(trecho, corpo, rota)
            for base in ("/comando?", "/comando/negocio?", "/executivo?", "/tendencias?"):
                self.assertIn(f'href="{base}', corpo, rota)
        self.assertEqual(self.get("/executivo?usuario=bruno", "bruno")[0], 403)
        self.assertEqual(self.get("/tendencias?usuario=ana", "ana")[0], 403)

    def test_clique_no_grafico_e_link_de_filtro_e_o_chip_tira_o_filtro(self):
        st, corpo = self.get(f"/comando?usuario=otavio&{QA}", "otavio")
        self.assertIn("workflow=assistente_rh", corpo)
        self.assertIn("situacao=falha", corpo)
        st, corpo = self.get(f"/comando?usuario=otavio&{QA}&situacao=falha", "otavio")
        self.assertIn("situação: falha", corpo)
        self.assertEqual(len(re.findall(r'class="tag" style="border-color:var\(--bad\);color:var\(--bad\)">falha<', corpo)),
                         self.op(situacao="falha")["kpis"]["execucoes"])

    def test_negocio_filtra_a_fila_de_decisao(self):
        d = self.app.comando(self.app.usuario("ana"), agora=AGORA)["saida"]["negocio"]["decisoes"]
        f = V.normalizar_negocio({"situacao": "enviado"})
        so = V.filtrar_decisoes(d, f)
        self.assertTrue(all(x["situacao"] == "enviado" for x in so))
        st, corpo = self.get(f"/comando/negocio?usuario=ana&{QA}&situacao=enviado", "ana")
        self.assertIn(f"{len(so)} de {len(d)} pessoa(s)", corpo)

    def test_executivo_e_tendencias_com_filtro(self):
        d7 = self.app.executivo(self.app.usuario("dora"), filtros={"periodo": "7d"}, agora=AGORA)["saida"]["visao"]
        d8 = self.app.executivo(self.app.usuario("dora"), agora=AGORA)["saida"]["visao"]
        self.assertLess(d7["kpis"]["execucoes"], d8["kpis"]["execucoes"])
        st, corpo = self.get("/tendencias?usuario=estela&grupo=custo", "estela")
        custo = [m for m in self.app.tendencias(self.app.usuario("estela"))["saida"]["metricas"] if m["grupo"] == "custo"]
        self.assertEqual(corpo.count('<div class="kpi">') + corpo.count('<a class="kpi link"'), len(custo))
        self.assertIn("<polyline", corpo)

    def test_snapshot_grava_a_semana_e_nao_o_acumulado(self):
        total = self.op(periodo="tudo")["kpis"]["execucoes"]
        self.app.gravar_snapshot()
        ultima = ler_vivo(self.app.pasta / "historico.jsonl")[-1]
        semana = self.op(periodo="7d", ignorar=self.app.indicadores["ignorar_workflows"])["kpis"]["execucoes"]
        self.assertEqual(ultima["execucoes"], semana)
        self.assertLess(ultima["execucoes"], total)

    # ---------------------------------------------------------------- gráficos
    def test_graficos_tem_tooltip_legenda_e_link(self):
        s = G.colunas(["a", "b"], G.STATUS_SERIES, {"a": {"ok": 3, "falha": 1}, "b": {"ok": 2}}, href=lambda c: f"?d={c}")
        self.assertIn("<title>a: 4", s)
        self.assertIn('href="?d=a"', s)
        self.assertIn('class="leg"', s)                           # 2+ séries: legenda sempre
        self.assertNotIn('class="leg"', G.barras([("x", "x", 5)]))  # uma série: sem legenda
        self.assertIn("Sem dados", G.rosca([("a", "a", 0, "red")]))
        estreita = G.linha(["1", "2", "3"], [("e", [78.0, 77.0, 76.7], "red", False)], meta=(75, "meta"))
        self.assertNotIn('class="sv mut">0<', estreita)          # faixa estreita: eixo não parte do zero


if __name__ == "__main__":
    unittest.main()
