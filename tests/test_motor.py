"""Pilares 2, 4 e 7: motor determinístico, humano no comando, segurança por workflow."""
import json
import os
import unittest

from agentic_app import config
from agentic_app.esquema import ErroValidacao, validar
from agentic_app.llm import FakeLLM, OllamaLLM, get_llm
from agentic_app.seguranca import PermissaoNegada
from agentic_app.workflow import ErroWorkflow, carregar_spec
from tests.base import BaseApp


class TestSpec(unittest.TestCase):
    def test_rejeita_tipo_de_no_invalido(self):
        with self.assertRaises(ErroWorkflow):
            carregar_spec({"id": "x", "versao": 1, "seguranca": {}, "nos": [{"id": "a", "tipo": "magia"}]})

    def test_rejeita_desvio_para_no_inexistente(self):
        spec = {"id": "x", "versao": 1, "seguranca": {}, "nos": [
            {"id": "c", "tipo": "condicao", "se": {}, "entao": "nao_existe", "senao": "$fim"}]}
        with self.assertRaises(ErroWorkflow):
            carregar_spec(spec)

    def test_validador_de_esquema(self):
        esq = {"type": "object", "required": ["n"], "properties": {"n": {"type": "integer", "maximum": 3}}}
        self.assertTrue(validar({"n": 2}, esq))
        for ruim in ({}, {"n": 4}, {"n": True}, {"n": "2"}):
            with self.assertRaises(ErroValidacao):
                validar(ruim, esq)


class TestLLM(unittest.TestCase):
    def test_fake_e_o_padrao_e_ollama_so_com_variavel(self):
        antigo = os.environ.pop("AGENTIC_LLM", None)
        try:
            self.assertIsInstance(get_llm(), FakeLLM)
            os.environ["AGENTIC_LLM"] = "ollama"
            self.assertIsInstance(get_llm(), OllamaLLM)  # só seleciona; nenhuma chamada feita
        finally:
            os.environ.pop("AGENTIC_LLM", None)
            if antigo:
                os.environ["AGENTIC_LLM"] = antigo

    def test_modelo_escolhido_pela_tarefa(self):
        self.assertEqual(config.modelo_para("classificacao"), "pequeno")
        self.assertEqual(config.modelo_para("redacao"), "medio")
        with self.assertRaises(KeyError):
            config.modelo_para("tarefa_sem_modelo")


class TestMotor(BaseApp):
    def test_determinismo_mesma_entrada_mesma_saida(self):
        a = self.app.motor.executar("followup_metas", {}, self.ana)["saida"]
        b = self.app.motor.executar("followup_metas", {}, self.ana)["saida"]
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_trilha_tem_os_cinco_tipos_de_no(self):
        r = self.rh("carla", "Quantos dias de férias eu tenho?")
        tipos = {p["tipo"] for p in r["trilha"]}
        self.assertEqual(tipos, {"contexto", "codigo", "condicao", "llm", "formatacao"})

    def test_llm_recebe_modelo_por_tarefa(self):
        r = self.rh("carla", "Quantos dias de férias eu tenho?")
        modelos = {p["no"]: p["modelo"] for p in r["trilha"] if "modelo" in p}
        self.assertEqual(modelos, {"categoria": "pequeno", "agente": "medio"})

    def test_condicao_desvia_quando_nao_ha_pendencia(self):
        r = self.app.motor.executar("followup_metas", {"liderado_ids": ["felipe"]}, self.ana)
        self.assertEqual(r["saida"]["qtd"], 0)
        self.assertEqual([p["no"] for p in r["trilha"]], ["ctx", "pendentes", "tem_pendente", "vazio"])
        self.assertEqual(r["propostas"], [])

    def test_entrada_invalida_e_barrada(self):
        with self.assertRaises(ErroWorkflow):
            self.app.motor.executar("followup_metas", {"campo_estranho": 1}, self.ana)

    def test_formatacao_rejeita_saida_fora_do_esquema(self):
        class LLMRuim(FakeLLM):
            def redigir(self, *a, **k):
                return "curto"  # corpo de e-mail com menos de 40 caracteres
        self.app.motor.llm = LLMRuim()
        with self.assertRaises(ErroWorkflow) as ctx:
            self.app.motor.executar("followup_metas", {}, self.ana)
        self.assertIn("ErroValidacao", str(ctx.exception))
        self.assertEqual(self.app.fila.pendentes(), [])  # nada proposto com saída inválida


class TestHumanoNoComando(BaseApp):
    def test_proposta_nao_envia_ate_aprovar(self):
        r = self.app.motor.executar("followup_metas", {}, self.ana)
        self.assertEqual(len(r["propostas"]), 6)
        self.assertEqual(self.app.caixa.enviados(), [])

    def test_aprovar_com_edicao_envia_o_texto_editado(self):
        r = self.app.motor.executar("followup_metas", {}, self.ana)
        aid = r["propostas"][0]["id"]
        self.app.fila.aprovar(aid, self.ana, {"corpo": "Texto revisado pela Ana, com calma e contexto."})
        enviados = self.app.caixa.enviados()
        self.assertEqual(len(enviados), 1)
        self.assertEqual(enviados[0]["corpo"], "Texto revisado pela Ana, com calma e contexto.")

    def test_campo_nao_editavel_e_recusado(self):
        r = self.app.motor.executar("followup_metas", {}, self.ana)
        with self.assertRaises(ValueError):
            self.app.fila.aprovar(r["propostas"][0]["id"], self.ana, {"para": "outra@pessoa.com"})

    def test_colaborador_nao_aprova_envio(self):
        r = self.app.motor.executar("followup_metas", {}, self.ana)
        with self.assertRaises(PermissaoNegada):
            self.app.fila.aprovar(r["propostas"][0]["id"], self.bruno)
        self.assertEqual(self.app.caixa.enviados(), [])

    def test_rejeitar_nao_envia(self):
        r = self.app.motor.executar("followup_metas", {}, self.ana)
        self.app.fila.rejeitar(r["propostas"][0]["id"], self.ana, "não é o momento")
        self.assertEqual(self.app.caixa.enviados(), [])
        self.assertEqual(len(self.app.fila.pendentes()), 5)


class TestSeguranca(BaseApp):
    def test_papel_sem_permissao_e_negado_e_auditado(self):
        with self.assertRaises(PermissaoNegada):
            self.app.motor.executar("followup_metas", {}, self.bruno)
        ultima = self.app.audit.ler()[-1]
        self.assertEqual(ultima["evento"], "workflow.negado")
        self.assertEqual(ultima["usuario"], "bruno")

    def test_identidade_sem_escopo_e_barrada(self):
        spec = json.loads(json.dumps(self.app.motor.workflows["followup_metas"]))
        spec["id"], spec["seguranca"]["identidade"] = "followup_errado", "svc-rh"  # svc-rh não lê equipe
        self.app.motor.adicionar(spec)
        with self.assertRaises(PermissaoNegada):
            self.app.motor.executar("followup_errado", {}, self.ana)

    def test_uma_linha_de_audit_por_execucao(self):
        antes = len(self.app.audit.ler())
        self.app.motor.executar("relatorio_equipe", {}, self.ana)
        linhas = self.app.audit.ler()
        self.assertEqual(len(linhas), antes + 1)
        self.assertEqual(linhas[-1]["identidade"], "svc-coaching")
        self.assertEqual(linhas[-1]["usuario"], "ana")

    def test_corrente_de_hash_detecta_adulteracao(self):
        self.app.motor.executar("relatorio_equipe", {}, self.ana)
        self.app.motor.executar("relatorio_equipe", {}, self.ana)
        self.assertTrue(self.app.audit.verificar_corrente())
        arq = self.app.audit.arquivo
        arq.write_text(arq.read_text().replace('"usuario": "ana"', '"usuario": "outra"', 1))
        self.assertFalse(self.app.audit.verificar_corrente())


if __name__ == "__main__":
    unittest.main()
