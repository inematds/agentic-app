"""Modelo de teste de política. Teste os LIMITES (o valor exato e o vizinho), não só "devolve dict".

Rode a partir da raiz do repo:  python3 -m unittest templates/test_politica_modelo.py
"""
import importlib.util
import pathlib
import unittest

_spec = importlib.util.spec_from_file_location("politica_modelo", pathlib.Path(__file__).with_name("politica_modelo.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


class TestPoliticaModelo(unittest.TestCase):
    def test_r1_no_limite_aprova(self):
        self.assertTrue(P.reembolso_aprovado(500)["aprovado"])

    def test_r1_um_acima_do_limite_reprova(self):
        self.assertFalse(P.reembolso_aprovado(501)["aprovado"])

    def test_entrada_estrita(self):
        for ruim in (True, "500", 500.0):
            with self.assertRaises(TypeError):
                P.reembolso_aprovado(ruim)
        with self.assertRaises(ValueError):
            P.reembolso_aprovado(0)


if __name__ == "__main__":
    unittest.main()
