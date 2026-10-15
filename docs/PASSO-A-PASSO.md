# Passo a passo: do zero à implantação numa empresa

Cada passo tem o que fazer, o arquivo que muda e como saber que deu certo.

## Passo 1 — Rodar o exemplo como está

```bash
git clone https://github.com/inematds/agentic-app && cd agentic-app
bash tests/run.sh             # última linha: OK
python3 -m agentic_app.demo   # gera saida/relatorio.html
python3 -m agentic_app.serve  # http://127.0.0.1:8765
```
**Deu certo quando:** o painel abre, você gera os rascunhos de follow-up, edita um e aprova.

## Passo 2 — Escrever o canvas de resultado (antes de qualquer agente)

Copie `templates/canvas-resultado.md` e preencha com quem vai usar, que decisão a pessoa toma, quanto isso
custa hoje e **um número** de sucesso com prazo.
**Deu certo quando:** o dono da métrica assina embaixo. Sem métrica, pare aqui.

## Passo 3 — Mapear os dados e criar os nós de contexto

Para cada dado, registre uma função de contexto com um escopo:
```python
@reg.contexto("pedidos_abertos", escopo="vendas.ler")
def pedidos_abertos(args): ...
```
Comece lendo de JSON ou CSV exportado; troque pelo banco depois, sem mudar o workflow.
**Deu certo quando:** a função devolve sempre o mesmo formato para a mesma entrada.

## Passo 4 — Codificar as políticas (com testes)

Para cada documento com número (férias, reembolso, alçada de desconto), copie `templates/politica_modelo.py`
e `templates/test_politica_modelo.py`. Uma constante por número, um teste por limite (o valor exato e o vizinho).
**Deu certo quando:** `bash tests/prova_mutacao.sh` (adapte as trocas para a sua política) diz que toda troca
quebrou algum teste.

## Passo 5 — Desenhar o workflow em JSON

Copie `templates/workflow-modelo.json`. Sequência típica: contexto → código → condição → LLM → formatação.
O LLM só entra onde há linguagem (classificar, redigir, escolher ferramenta). Número e regra ficam no código.
Defina o esquema da saída no nó de formatação.
**Deu certo quando:** `python3 -c "from agentic_app.workflow import carregar_spec; carregar_spec('meu.json')"` não reclama.

## Passo 6 — Ligar ações externas à fila de aprovação

Toda ação que sai da empresa (e-mail, cadastro, pagamento) vira `propor_acao` no nó de formatação, com a lista de
campos `editaveis`. Registre o executor real (SMTP, API interna) no lugar de `CaixaSaida`.
**Deu certo quando:** um teste prova que nada é executado antes do `aprovar`.

## Passo 7 — Permissões, identidades e audit

Preencha `templates/permissoes.json`: quem executa cada workflow, com qual identidade ele age e quem aprova.
Dê a cada identidade só os escopos de que ela precisa. Troque o cabeçalho `X-Usuario` da demo pelo login
corporativo (SSO) no `serve.py`.
**Deu certo quando:** o teste de papel sem permissão gera uma linha `workflow.negado` no `audit.jsonl` e
`AuditLog.verificar_corrente()` devolve `True`.

## Passo 8 — Gatilhos

Declare no próprio workflow: `manual` (componente da tela), `agendado` (dia + hora) e `evento` (nome + mapa do
evento para a entrada). Em produção, chame `Gatilhos.tick(agora)` a cada minuto (cron/systemd) e
`Gatilhos.emitir(...)` a partir da fila de e-mails ou do webhook do sistema de origem.
**Deu certo quando:** o teste com relógio fixo roda o agendado uma única vez por janela.

## Passo 9 — Tela e saída visual

Cada componente da tela chama um workflow com o input da tela e mostra o resultado ali mesmo. Para relatórios,
use um nó de formatação com `artefato` (HTML/PDF) em vez de devolver texto corrido.
**Deu certo quando:** a pessoa usuária faz a tarefa inteira sem sair do painel.

## Passo 10 — Piloto, medição e implantação

1. Piloto com 1 equipe por 2 a 4 semanas, `FakeLLM` ou modelo local, dados reais anonimizados.
2. Meça a métrica do canvas contra a linha de base. Leia o `audit.jsonl`: quantas propostas foram aprovadas,
   editadas e rejeitadas. Muita edição = rascunho ruim; muita rejeição = gatilho errado.
3. Só então troque o LLM (subclasse de `LLM`), conecte o executor real e abra para mais equipes.
4. Cada mudança de política = nova versão (`VERSAO_POLITICA`) + teste novo + registro no CHANGELOG.

## Passo 11 — Medir o resultado com o painel executivo

Quem patrocina o app (diretoria) não quer a tela operacional; quer saber se a métrica do canvas está andando,
com controle e a que custo.

1. Copie `templates/indicadores.json` para a pasta `data/` do seu app. Em `metricas`, ponha as métricas do canvas
   com `meta`, `linha_base` e `sentido` (`maior` ou `menor`); em `metrica_principal`, a métrica de sucesso; em
   `regra_principal`, como ela é contada, em uma frase.
2. Escreva no app uma função que devolva `{id: {"valor": x, "serie": [...]}}` para cada métrica (no exemplo,
   `metricas_negocio` em `apps/coaching/app.py`). Número vem dos dados e da fila, nunca do LLM.
3. Preencha `custo_por_modelo` com o preço por chamada e por 1.000 tokens de cada modelo (0 = modelo local).
4. Dê o papel `diretoria` (ou `admin`) a quem patrocina e mantenha o workflow `painel_executivo` com identidade
   só de leitura (`equipe.ler`, `audit.ler`, `aprovacoes.ler`).
5. Abra `/executivo` (ou rode a demo: `saida/executivo.html` e `.pdf`). Leia os alertas primeiro: corrente de hash
   quebrada ou ação externa sem aprovação são incidentes, não números ruins.

**Deu certo quando:** a diretoria responde "está entregando?" olhando só essa página, e quem tem papel de
colaborador ou gestor recebe 403 com uma linha `workflow.negado` no audit.

## Passo 12 — Medir a tendência e revisar todo trimestre

O painel executivo é a foto da semana. O de tendências é o filme: para onde cada número está indo e se a meta
chega no prazo.

1. Copie `templates/tendencias.json` para a pasta `data/` do seu app. Liste as métricas que vale acompanhar (campos do
   snapshot semanal), o `horizonte_fim` (fim do trimestre), `min_pontos` e `quedas_seguidas_alerta`.
2. Deixe o workflow `snapshot_indicadores` agendado (segunda 07:00). Em 4 semanas o painel começa a projetar; antes
   disso ele diz "histórico insuficiente", de propósito.
3. Dê o papel `estrategia` a quem planeja (diretoria e admin também veem).
4. Abra `/tendencias`. Leia primeiro os sinais antecipados (ex.: engajamento caindo 3 semanas seguidas): eles
   aparecem antes de a meta ser perdida.
5. Na revisão trimestral: compare a projeção com o que aconteceu, ajuste metas no `indicadores.json` e no
   `tendencias.json` (um teste confere que batem), use os cenários "e se" para decidir a alavanca (ex.: mais 1:1 por
   semana) e registre a decisão.

**Deu certo quando:** a reunião trimestral decide pela projeção e pelos sinais, não por impressão, e cada número da
narrativa tem origem no código (o LLM só costura as frases).

## Checklist de implantação

- [ ] Canvas preenchido, com métrica, linha de base e dono
- [ ] Toda regra com número está em `policies/` com teste de limite
- [ ] `prova_mutacao.sh` adaptado e passando
- [ ] Nenhum workflow chama LLM para calcular número ou decidir regra
- [ ] Toda ação externa passa por `propor_acao` + aprovação
- [ ] Campos editáveis definidos (e campos sensíveis, como destinatário, travados)
- [ ] Cada workflow tem papéis de execução e identidade com escopo mínimo
- [ ] Login corporativo no lugar de `X-Usuario`
- [ ] Audit log guardado fora da máquina do app e `verificar_corrente()` rodando todo dia
- [ ] Gatilhos agendados e por evento com relógio/fila de produção
- [ ] Perguntas abertas marcadas como não críticas (FAQ/busca), separadas das políticas
- [ ] `bash tests/run.sh` verde no CI antes de cada deploy
- [ ] Piloto medido contra a linha de base antes de ampliar
- [ ] `indicadores.json` com metas do canvas e preços por modelo; painel executivo só para diretoria/admin
- [ ] Snapshot semanal agendado, histórico de exemplo removido, revisão trimestral com o painel de tendências
