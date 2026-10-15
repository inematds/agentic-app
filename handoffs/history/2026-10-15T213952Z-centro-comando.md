# Handoff — 2026-10-15 — agentic-app 1.3.0: Centro de Comando (Agent Control Tower + Mission Control)

## Projeto e escopo
agentic-app, raiz `~/projetos/agentic-app` (repo inematds/agentic-app). O usuário pediu um "centro de comando" com ações, com duas visões: operação dos agentes (Agent Control Tower) e negócio (Mission Control). Restrições do AGENTS.md: só stdlib, sem rede nos testes, workflow nunca executa ação externa, docs em PT/EN/ES.

## Objetivo atual
Entregue: versão 1.3.0 publicada (commit 2892072, push feito). Critério de pronto: `bash tests/run.sh` com OK na última linha e `prova_mutacao.sh` OK.

## Estado aceito
- [confirmed] `agentic_app/comando.py` — Controle (pausas e escaladas em saida/comando.json, tudo auditado) + calcular/ESQUEMA (torre, missao, alertas por regra)
- [confirmed] `agentic_app/comando_html.py` — página /comando com duas abas e botões POST (X-Usuario do ?usuario=)
- [confirmed] workflow `centro_comando` (papéis operacao, admin, gestor, diretoria; identidade svc-comando, escopo comando.ler); usuário fictício otavio (operacao)
- [confirmed] Motor: pausa checada após RBAC (WorkflowPausado, 409, status "pausado" no audit); tick/emitir pulam o pausado; run_id continua a numeração do audit após reinício
- [confirmed] Rotas: GET /comando, /api/comando (?agora=), POST /api/comando/{pausar|retomar|rodar|reexecutar|escalar}/<alvo>
- [confirmed] Docs: READMEs, ARQUITETURA, PASSO-A-PASSO (passo 13), guia PT/EN/ES com prints guia/assets/comando-*.jpg, CHANGELOG, VERSION 1.3.0

## Proposto / tentado, não confirmado
- [?] GitHub Pages do guia com a seção nova no ar — não conferido

## Decisões e restrições
- Operação nunca aprova nem envia; escalar só marca o item.
- Reexecutar só execução agendada ou com entrada vazia (o audit guarda só o hash da entrada; perguntas de RH não são salvas).
- Leituras do painel (centro_comando, executivo, tendências) ficam fora da contagem de operação e do feed.
- "Ao vivo" é opcional (30 s, desligado por padrão), porque cada consulta grava uma linha no audit.

## Arquivos alterados
- `agentic_app/{comando.py,comando_html.py,workflow.py,gatilhos.py,executivo.py,serve.py,demo.py,painel.html}`
- `agentic_app/apps/coaching/{app.py,data/acesso.json,data/indicadores.json,data/comando.json,workflows/centro_comando.json}`
- `templates/{comando.json,permissoes.json,indicadores.json}`, `tests/test_comando.py`
- `README*.md`, `AGENTS.md`, `CHANGELOG.md`, `VERSION`, `docs/*.md`, `guia/**`
- Fora do projeto: `~/projetos/wifi/LESSONS.md` (lição nova no topo)

## Memória e regras duráveis tocadas
- `~/projetos/wifi/LESSONS.md` — conferir VERSION antes de anunciar o número da versão; matar o servidor com `kill $SP` em vez de `pkill -f`

## Verificação
- Rodado: `bash tests/run.sh` → "93 checks, 0 falhas" e OK
- Rodado: `bash tests/prova_mutacao.sh` → OK
- Rodado: `python3 -m agentic_app.demo` → seção 12 impressa sem erro
- Rodado: screenshots headless de /comando (claro, escuro, 390 px) e da seção do guia → layout conferido visualmente
- Não rodado: verificação do GitHub Pages — fora do escopo

## Estado em execução
- Processos em segundo plano: nenhum (servidor 8799 dos prints foi encerrado)
- Servidores / portas: nenhum
- Worktrees / branches abertos: nenhum

## Perguntas abertas e adiados
- Aberta: publicar a novidade 1.3.0 no portal (inema.club)? — o usuário ainda não pediu

## Próxima ação exata
Nada pendente. Se o usuário pedir: atualizar o portal com a 1.3.0 (skill atualiza-portal; precisa da confirmação dele).

## Mapa de retomada
- `CHANGELOG.md` — resumo da 1.3.0
- `agentic_app/comando.py` — regras da torre e da missão
- `docs/ARQUITETURA.md` — seção "Centro de Comando (1.3.0)"
- `tests/test_comando.py` — comportamento esperado

## Checagem de compartilhamento
- Sem segredos, tokens, cookies, dados pessoais ou endpoints privados: sim (usuários e e-mails são fictícios do exemplo)
