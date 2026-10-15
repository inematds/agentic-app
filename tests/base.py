import itertools
import os
import shutil
import tempfile
import unittest

from agentic_app.apps.coaching import montar


def relogio_fixo():
    cont = itertools.count()
    return lambda: f"2026-10-15T12:00:{next(cont) % 60:02d}+00:00"


class BaseApp(unittest.TestCase):
    """Cada teste ganha uma pasta de saída própria e um relógio fixo."""

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="agentic-teste-")
        self._antiga = os.environ.get("AGENTIC_SAIDA")
        os.environ["AGENTIC_SAIDA"] = self.pasta
        self.app = montar(self.pasta, relogio=relogio_fixo())
        self.ana = self.app.usuario("ana")
        self.rosa = self.app.usuario("rosa")
        self.bruno = self.app.usuario("bruno")
        self.sistema = self.app.usuario("sistema")

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)
        if self._antiga is None:
            os.environ.pop("AGENTIC_SAIDA", None)
        else:
            os.environ["AGENTIC_SAIDA"] = self._antiga

    def rh(self, colaborador, pergunta, usuario=None):
        return self.app.motor.executar("assistente_rh", {"colaborador_id": colaborador, "pergunta": pergunta},
                                       usuario or self.rosa)
