# Changelog

## 1.2.0 — 2026-10-15

Painel de tendências: "para onde está indo?" (o executivo responde "está entregando agora?").

- `agentic_app/tendencias.py` (só stdlib, determinístico): variação semana a semana e no período, média móvel,
  regressão linear simples, projeção até a meta ("atingida em DD/MM" ou "não é atingida até o fim do trimestre"),
  ruptura futura de meta já atingida, sinais antecipados (N semanas seguidas no sentido ruim), comparação entre
  pessoas e cenários "e se" com regra explícita. Com menos de `min_pontos` semanas: "histórico insuficiente".
- Histórico: `apps/coaching/data/historico.json` (12 semanas, DADO DE EXEMPLO rotulado) + snapshot semanal real em
  `saida/historico.jsonl` pelo workflow `snapshot_indicadores` (agendado segunda 07:00); o real substitui o exemplo
  da mesma semana.
- Workflow `painel_tendencias` (papéis `estrategia`, `diretoria`, `admin`; identidade só leitura `svc-estrategia`);
  usuária fictícia Estela (estratégia). O nó LLM só costura a narrativa com frases já calculadas (FakeLLM padrão).
- `serve.py`: `/tendencias` (gráficos de linha SVG com média móvel, meta e projeção) e `/api/tendencias`.
- `relatorio.py`: página de tendências em HTML e PDF. `demo.py`: seção 11.
- `templates/tendencias.json` (métricas acompanhadas, horizonte, limiares, cenários).
- Testes: 75 checks (13 novos). Docs PT/EN/ES, ARQUITETURA, PASSO-A-PASSO (passo 12), guia com a seção "Tendências".

## 1.1.0 — 2026-10-15

Painel executivo: a visão de quem patrocina o app.

- `agentic_app/executivo.py`: indicadores de resultado de negócio (métricas do canvas com meta, linha de base e
  status), operação dos agentes (execuções por workflow e por gatilho, aprovação × edição × rejeição, tempo até
  aprovar, sugestões aceitas), controle e risco (negados por papel, ferramentas barradas, corrente de hash,
  % de ações externas com aprovação) e custo de LLM (chamadas por workflow e modelo, tokens estimados, tabela de
  preço). Alertas executivos de 3 a 5 frases montadas por regra. Saída validada por `executivo.ESQUEMA`.
- Workflow `painel_executivo` (identidade só leitura `svc-diretoria`), papel `diretoria` (usuária fictícia Dora) e
  `admin`; colaborador e gestor são negados e auditados.
- `serve.py`: rota `/executivo` (HTML com gráficos SVG inline) e `/api/executivo` (JSON); link no painel.
- `relatorio.py`: página executiva em HTML e PDF (`saida/executivo.html`, `saida/executivo.pdf`).
- `demo.py`: seção 10 imprime o resumo executivo.
- Audit: cada execução grava `llm = {chamadas por modelo, tokens_estimados}`; `AuditLog.primeira_quebra()` diz
  em que linha a corrente quebrou. LLMs registram estimativa de tokens (caracteres ÷ 4).
- `templates/indicadores.json` (métricas, metas, acesso, limiares, custo por modelo); `permissoes.json` com o papel
  e a identidade novos.
- Testes: 62 checks (14 novos); `prova_mutacao.sh` continua com 9 trocas.
- Docs: README PT/EN/ES, ARQUITETURA, PASSO-A-PASSO (passo 11), guia PT/EN/ES com a seção "Painel executivo".

## 1.0.0 — 2026-10-15

Primeira versão.

- Motor de workflow em JSON com 5 tipos de nó: `contexto`, `codigo`, `condicao`, `llm`, `formatacao`
  (+ `proximo`/`$fim`, `para_cada`, validação de esquema na entrada e na saída).
- Adaptador de LLM: `FakeLLM` determinístico (padrão) e `OllamaLLM` local opcional (`AGENTIC_LLM=ollama`);
  modelo escolhido pela tarefa (`classificacao`, `redacao`, `resumo`, `agente`).
- Humano no comando: `FilaAprovacao` com edição de campos permitidos, aprovar/rejeitar por papel, caixa de saída simulada.
- Segurança: papéis por workflow, identidades com escopo, audit log JSONL com hash encadeado.
- Gatilhos: manual (componente da tela), agendado (dia + hora, relógio injetável), evento.
- Política codificada: `policies/ferias.py` (manual fictício de RH, regras F1–F6 e P1–P4, 3 funções com entrada estrita).
- App de referência Coaching de gestor: 12 liderados fictícios, 5 workflows, painel web (`python3 -m agentic_app.serve`),
  demo no terminal (`python3 -m agentic_app.demo`), relatório HTML + PDF sem dependência.
- `templates/`: canvas de resultado, modelo de workflow, modelo de política + teste, matriz de permissões.
- Testes: `tests/run.sh` com 48 checks sem rede; `tests/prova_mutacao.sh` prova que mudar 9 números da política quebra testes.
- Docs: README PT/EN/ES, `docs/PASSO-A-PASSO.md` (10 passos + checklist), `docs/ARQUITETURA.md`, guia PT/EN/ES.
