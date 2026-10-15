"""Políticas codificadas. Cada módulo expõe FERRAMENTAS = {grupo: {nome: função}}."""
from . import ferias

POLITICAS = {"ferias": ferias}


def grupos_de_ferramentas() -> dict:
    grupos = {}
    for mod in POLITICAS.values():
        grupos.update(mod.FERRAMENTAS)
    return grupos
