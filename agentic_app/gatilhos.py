"""Pilar 8 — gatilhos além do clique.

- manual    : componente da UI chama motor.executar(...)
- agendado  : Agendador.tick(agora) roda o que venceu (relógio injetado = testável)
- evento    : Barramento.emitir("email.recebido", {...}) roda quem assina o evento

Os gatilhos vêm do próprio JSON do workflow (campo "gatilhos"). Nada escondido no código.
"""
from .workflow import WorkflowPausado, resolver

DIAS = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6}


class Gatilhos:
    def __init__(self, motor, usuarios: dict):
        self.motor = motor
        self.usuarios = usuarios
        self.agendados = []   # (workflow_id, gatilho)
        self.eventos = {}     # nome -> [(workflow_id, gatilho)]
        self.componentes = {}  # componente da UI -> workflow_id
        self._ja_rodou = set()
        for wid, spec in motor.workflows.items():
            for g in spec.get("gatilhos", []):
                if g["tipo"] == "agendado":
                    self.agendados.append((wid, g))
                elif g["tipo"] == "evento":
                    self.eventos.setdefault(g["nome"], []).append((wid, g))
                elif g["tipo"] == "manual" and "componente" in g:
                    self.componentes.setdefault(g["componente"], wid)
                elif g["tipo"] != "manual":
                    raise ValueError(f"{wid}: gatilho desconhecido {g['tipo']}")

    def manual(self, workflow_id, entrada, usuario):
        return self.motor.executar(workflow_id, entrada, usuario, gatilho="manual")

    def tick(self, agora) -> list:
        """Roda cada agendamento cujo dia/hora bate com `agora` (uma vez por janela)."""
        resultados = []
        for wid, g in self.agendados:
            if agora.weekday() != DIAS[g["dia_semana"]] or agora.strftime("%H:%M") != g["hora"]:
                continue
            chave = (wid, agora.strftime("%Y-%m-%d %H:%M"))
            if chave in self._ja_rodou:
                continue
            self._ja_rodou.add(chave)
            try:
                resultados.append(self.motor.executar(wid, dict(g.get("entrada", {})),
                                                      self.usuarios[g["usuario"]],
                                                      gatilho=f"agendado:{g['dia_semana']} {g['hora']}"))
            except WorkflowPausado:
                continue  # pausado no Centro de Comando: o disparo ficou no audit; os outros seguem
        return resultados

    def agendado_de(self, workflow_id):
        """Primeiro gatilho agendado do workflow (para o 'rodar agora' do Centro de Comando)."""
        for wid, g in self.agendados:
            if wid == workflow_id:
                return g
        raise ValueError(f"{workflow_id} não tem gatilho agendado")

    def emitir(self, nome, evento: dict) -> list:
        resultados = []
        for wid, g in self.eventos.get(nome, []):
            entrada = resolver(g["mapa"], {"evento": evento})
            try:
                resultados.append(self.motor.executar(wid, entrada, self.usuarios[g["usuario"]],
                                                      gatilho=f"evento:{nome}"))
            except WorkflowPausado:
                continue  # evento recebido com o workflow pausado: fica no audit (hash), não é processado
        return resultados
