"""Pilar 6: a política É o código. Mudou um número do manual, algum teste aqui quebra."""
import unittest

from agentic_app.policies import ferias as F


class TestDiasDeFerias(unittest.TestCase):
    def test_f1_proporcional_abaixo_de_12_meses(self):
        self.assertEqual(F.dias_de_ferias(0)["dias"], 0)
        self.assertEqual(F.dias_de_ferias(4)["dias"], 10)
        self.assertEqual(F.dias_de_ferias(11)["dias"], 27)   # 27,5 arredonda para baixo
        self.assertEqual(F.dias_de_ferias(11)["regra"], "F1")

    def test_f2_de_12_a_59_meses(self):
        self.assertEqual(F.dias_de_ferias(12), {"dias": 30, "regra": "F2", "politica": "manual-pessoas-v3"})
        self.assertEqual(F.dias_de_ferias(59)["dias"], 30)

    def test_f3_bonus_de_5_anos(self):
        self.assertEqual(F.dias_de_ferias(60)["dias"], 32)
        self.assertEqual(F.dias_de_ferias(119)["dias"], 32)
        self.assertEqual(F.dias_de_ferias(119)["regra"], "F3")

    def test_f4_bonus_de_10_anos(self):
        self.assertEqual(F.dias_de_ferias(120)["dias"], 35)
        self.assertEqual(F.dias_de_ferias(300)["regra"], "F4")

    def test_entradas_estritas(self):
        for ruim in (True, 12.0, "12", None):
            with self.assertRaises(TypeError):
                F.dias_de_ferias(ruim)
        with self.assertRaises(ValueError):
            F.dias_de_ferias(-1)
        with self.assertRaises(ValueError):
            F.dias_de_ferias(601)


class TestPedidoDeFerias(unittest.TestCase):
    def test_pedido_valido(self):
        r = F.validar_pedido_ferias([14, 10, 6], 30)
        self.assertTrue(r["aprovado"])
        self.assertEqual(r["motivos"], [])

    def test_f5_antecedencia_de_30_dias(self):
        self.assertFalse(F.validar_pedido_ferias([30], 29)["aprovado"])
        self.assertTrue(F.validar_pedido_ferias([30], 30)["aprovado"])

    def test_f6_limites_de_fracionamento(self):
        self.assertFalse(F.validar_pedido_ferias([10, 10, 5, 5], 40)["aprovado"])  # 4 períodos
        self.assertFalse(F.validar_pedido_ferias([13, 13, 4], 40)["aprovado"])     # nenhum >= 14
        r = F.validar_pedido_ferias([20, 4], 40)                                    # um < 5
        self.assertIn("F6: nenhum período pode ter menos de 5 dias", r["motivos"])

    def test_pedido_entradas_estritas(self):
        with self.assertRaises(TypeError):
            F.validar_pedido_ferias([], 30)
        with self.assertRaises(TypeError):
            F.validar_pedido_ferias([10, "5"], 30)


class TestLicencaParental(unittest.TestCase):
    def test_valores_por_papel(self):
        esperado = {"gestante": 180, "parceiro_gestante": 20, "adotante_principal": 180, "adotante_secundario": 20}
        for papel, dias in esperado.items():
            self.assertEqual(F.licenca_parental(papel)["dias"], dias, papel)

    def test_p4_remunerada_e_nao_desconta_ferias(self):
        r = F.licenca_parental("gestante")
        self.assertTrue(r["remunerada"])
        self.assertFalse(r["desconta_ferias"])

    def test_papel_invalido(self):
        with self.assertRaises(ValueError):
            F.licenca_parental("pai")
        with self.assertRaises(TypeError):
            F.licenca_parental(1)


if __name__ == "__main__":
    unittest.main()
