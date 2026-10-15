"""Roda a suíte SEM REDE: qualquer tentativa de abrir conexão quebra o teste."""
import os
import socket
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.pop("AGENTIC_LLM", None)  # força FakeLLM


def _bloqueado(*a, **k):
    raise RuntimeError("rede bloqueada nos testes")


socket.socket.connect = _bloqueado
socket.socket.connect_ex = _bloqueado
socket.create_connection = _bloqueado

suite = unittest.defaultTestLoader.discover(os.path.join(RAIZ, "tests"), pattern="test_*.py", top_level_dir=RAIZ)
resultado = unittest.TextTestRunner(verbosity=1, stream=sys.stdout).run(suite)
falhas = len(resultado.failures) + len(resultado.errors)
print(f"{resultado.testsRun} checks, {falhas} falhas")
sys.exit(1 if falhas or resultado.testsRun < 20 else 0)
