"""Os modelos em templates/ precisam continuar válidos — a empresa começa por eles."""
import json
import pathlib
import unittest

from agentic_app import config
from agentic_app.workflow import carregar_spec

T = pathlib.Path(__file__).resolve().parent.parent / "templates"


class TestTemplates(unittest.TestCase):
    def test_workflow_modelo_e_uma_spec_valida(self):
        spec = carregar_spec(T / "workflow-modelo.json")
        self.assertEqual([n["tipo"] for n in spec["nos"]],
                         ["contexto", "codigo", "condicao", "llm", "formatacao", "formatacao"])

    def test_matriz_de_permissoes_bate_com_os_workflows_do_app(self):
        m = json.loads((T / "permissoes.json").read_text(encoding="utf-8"))
        wdir = pathlib.Path(__file__).resolve().parent.parent / "agentic_app/apps/coaching/workflows"
        for linha in m["workflows"]:
            spec = json.loads((wdir / f"{linha['workflow']}.json").read_text(encoding="utf-8"))
            self.assertEqual(spec["seguranca"]["executar"], linha["executar"], linha["workflow"])
            self.assertEqual(spec["seguranca"]["identidade"], linha["identidade"], linha["workflow"])

    def test_indicadores_modelo_tem_o_mesmo_formato_do_app(self):
        t = json.loads((T / "indicadores.json").read_text(encoding="utf-8"))
        app = json.loads((T.parent / "agentic_app/apps/coaching/data/indicadores.json").read_text(encoding="utf-8"))
        chaves = {"acesso", "metrica_principal", "metricas", "limiares", "custo_por_modelo"}
        self.assertLessEqual(chaves, set(t))
        self.assertLessEqual(chaves, set(app))
        self.assertIn(t["metrica_principal"], [m["id"] for m in t["metricas"]])
        for m in t["metricas"] + app["metricas"]:
            self.assertLessEqual({"id", "nome", "unidade", "meta", "sentido"}, set(m))
            self.assertIn(m["sentido"], ("maior", "menor"))
        self.assertEqual(set(t["custo_por_modelo"]["modelos"]), set(config.MODELOS_PADRAO.values()))

    def test_politica_modelo_passa_nos_proprios_testes(self):
        suite = unittest.defaultTestLoader.discover(str(T), pattern="test_politica_modelo.py", top_level_dir=str(T))
        r = unittest.TextTestRunner(stream=open("/dev/null", "w")).run(suite)
        self.assertTrue(r.wasSuccessful())
        self.assertEqual(r.testsRun, 3)


if __name__ == "__main__":
    unittest.main()
