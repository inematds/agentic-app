# Arquitetura

```
 Tela (painel.html)        Gatilhos (gatilhos.py)
  componente ─┐             agendado ─┐   evento ─┐
              ▼                       ▼           ▼
          serve.tratar ──────────► Motor.executar(workflow, entrada, usuário, gatilho)
                                      │
             1. RBAC: papel do usuário ∈ seguranca.executar?  ── não ─► audit "workflow.negado"
             2. identidade do workflow (conta de serviço com escopos)
             3. entrada validada pelo esquema do workflow
             4. nós em ordem:  contexto → código → condição → LLM → formatação
                                      │                         │
                                      │                         ├─ valida JSON da saída
                                      │                         ├─ PROPÕE ação ─► FilaAprovacao
                                      │                         └─ artefato (HTML/PDF)
             5. uma linha no audit log (hash encadeado)
                                      ▼
                         resultado volta para a tela
                                      │
           pessoa revisa/edita/aprova ─► executor (e-mail) ─► audit "acao.executada"
```

## Os cinco tipos de nó

| Tipo | Faz | Nunca faz |
|---|---|---|
| `contexto` | chama uma função registrada que carrega dados, exigindo o escopo da identidade | ler dado que a identidade não pode |
| `codigo` | regra de negócio em Python puro (filtrar, calcular, chamar política) | chamar LLM |
| `condicao` | compara um campo (`>`, `>=`, `<`, `<=`, `==`, `!=`, `em`) e desvia para `entao`/`senao` | avaliar código arbitrário |
| `llm` | `classificar`, `redigir` ou `agente` (escolher ferramenta do grupo liberado) | escolher o próprio modelo; usar ferramenta fora do grupo |
| `formatacao` | monta o JSON da UI, valida contra esquema, propõe ação, gera artefato | executar a ação |

Referências entre nós: `"$entrada.campo"`, `"$id_do_no.campo"`, `"$usuario.id"`, `"$item.x"` (dentro de `para_cada`).
Qualquer nó pode ter `"proximo": "<id>"` ou `"$fim"`.

## Modelo por tarefa

O nó LLM declara a `tarefa` (`classificacao`, `redacao`, `resumo`, `agente`). O modelo vem de `config.MODELOS_PADRAO`
ou de um `modelos.json` na pasta atual. O audit log grava qual modelo cada execução usou.

## Escopo mínimo do agente

No `assistente_rh`, o nó `categoria` classifica a pergunta (`ferias`, `licenca_parental`, `outro`). O nó `agente`
recebe **só** o grupo de ferramentas daquela categoria (`policies/ferias.py › FERRAMENTAS`). Se o LLM pedir uma
ferramenta que não foi ofertada, o motor levanta `PermissaoNegada` e o teste
`test_agente_que_pede_ferramenta_fora_do_escopo_e_barrado` prova isso. Perguntas `outro` vão para a busca no FAQ,
marcadas como `critica: false`.

## Identidades

| Identidade | Escopos | Usada por |
|---|---|---|
| `svc-coaching` | `equipe.ler` | followup_metas, convite_1a1, proximos_passos, relatorio_equipe |
| `svc-rh` | `rh.perfil.ler`, `rh.faq.ler` | assistente_rh |
| `svc-diretoria` | `equipe.ler`, `audit.ler`, `aprovacoes.ler` (só leitura) | painel_executivo, snapshot_indicadores |
| `svc-estrategia` | `equipe.ler`, `historico.ler` (só leitura) | painel_tendencias |
| `svc-comando` | `equipe.ler`, `audit.ler`, `aprovacoes.ler`, `comando.ler` (só leitura) | centro_comando |

O audit grava as duas coisas: **quem pediu** (`usuario`, `papeis`) e **como o workflow agiu** (`identidade`).

## Arquivos de saída (`saida/`, ou `AGENTIC_SAIDA`)

| Arquivo | Conteúdo |
|---|---|
| `audit.jsonl` | uma linha por execução/negação/aprovação, com `hash` e `hash_anterior` |
| `aprovacoes.json` | fila de ações propostas e seu status |
| `caixa_saida.jsonl` | e-mails "enviados" (simulado; troque pelo SMTP da empresa) |
| `sugestoes.json` | última rodada do agente de fundo |
| `relatorio.html`, `relatorio.pdf` | saída visual do `relatorio_equipe` |
| `executivo.html`, `executivo.pdf` | saída do `painel_executivo` (servida só pela rota `/executivo`, com RBAC) |
| `historico.jsonl` | um snapshot por semana (chave = segunda-feira), gravado pelo `snapshot_indicadores` |
| `tendencias.html`, `tendencias.pdf` | saída do `painel_tendencias` (servida só pela rota `/tendencias`, com RBAC) |
| `comando.json` | workflows pausados (quem, quando, motivo) e aprovações escaladas, do Centro de Comando |

## Painel executivo (1.1.0)

```
 audit.jsonl ─┐  aprovacoes.json ─┐  caixa_saida.jsonl ─┐  sugestoes.json ─┐  dados do app ─┐
              ▼                   ▼                     ▼                 ▼                ▼
   contexto registros_operacao (audit.ler)   contexto aprovacoes (aprovacoes.ler)   contexto equipe (equipe.ler)
                                   └──────────────┬──────────────┘
                     código indicadores_executivos → executivo.calcular(...)  (valida executivo.ESQUEMA)
                                                  ▼
                     formatação + artefato → executivo.html / executivo.pdf ; rota /executivo
```

- Acesso: `seguranca.executar = ["diretoria", "admin"]` no workflow e `acesso` em `indicadores.json` (um teste
  confere que batem). Qualquer outro papel → `PermissaoNegada` + linha `workflow.negado`.
- **Resultado de negócio**: o app entrega `{id: {valor, serie}}` (`metricas_negocio`); meta, linha de base e sentido
  vêm de `indicadores.json`; `atingiu` é só comparação.
- **Operação**: execuções `ok` por workflow e por gatilho (`manual`/`sugestao:` = clique, `agendado:` = horário,
  `evento:` = evento); desfecho dos rascunhos pela fila; tempo até aprovação = `ts` da execução que propôs →
  `ts` de `acao.executada`; sugestões aceitas = execuções com gatilho `sugestao:`. Leituras listadas em
  `ignorar_workflows` (o próprio painel) não contam.
- **Controle**: `workflow.negado` + `acao.negada` por papel; execuções negadas com "ferramenta fora do escopo";
  `AuditLog.primeira_quebra()` (0 = íntegra); ações externas = linhas da caixa de saída, cada uma precisa de
  `acao.executada` com aprovador no audit e item `executada` na fila.
- **Custo**: desde 1.1.0 cada linha `workflow.executado` grava `llm = {chamadas: {modelo: n}, tokens_estimados}`
  contando as chamadas reais ao adaptador (o `FakeLLM` conta igual). Tokens = caracteres ÷ 4 quando o adaptador não
  informa. Custo = chamadas × `por_chamada` + tokens/1000 × `por_1k_tokens`.
- **Alertas**: regras fixas em `executivo.alertas`, ordenadas por nível (crítico → atenção → ok), no máximo 5.

## Tendências (1.2.0)

```
 segunda 07:00 ─► snapshot_indicadores ─► executivo.calcular ─► snapshot_de ─► saida/historico.jsonl
                                                                                   │
 data/historico.json (EXEMPLO, rotulado) ───────────────► juntar (real vence na mesma semana)
                                                                                   ▼
 painel_tendencias: contexto equipe + contexto historico (historico.ler) → código analisar
                    → código fatos → LLM redigir (só costura) → código com_narrativa → formatação + artefato
```

Regras (todas em `tendencias.py`, testadas):

- **Ritmo** = inclinação da reta de mínimos quadrados, x = semanas desde o 1º ponto. **Média móvel** de
  `janela_media_movel` semanas.
- **Projeção** a partir do último valor: semanas = (meta − último) ÷ ritmo; data = última semana + semanas × 7 dias
  (para cima). Depois de `horizonte_fim` → "não é atingida até o fim do trimestre". Ritmo no sentido contrário →
  "não é atingida". Meta já atingida e ritmo piorando → data em que sai da meta ("rompe").
- **Histórico insuficiente**: menos de `min_pontos` semanas → sem ritmo nem projeção, nem cenário.
- **Sinal antecipado**: `quedas_seguidas_alerta` movimentos seguidos no sentido ruim no fim da série (queda se
  `maior` é melhor, alta se `menor`). Vale também por pessoa (engajamento das últimas semanas em `equipe.json`).
- **Cenário "e se" (coaching)**: cada conversa 1:1 a mais por semana com alguém que tem meta vencida cobre essa
  pessoa: vale 100 ÷ (pessoas com meta vencida) pontos, teto 100%; depois segue o ritmo de hoje.
- **Narrativa**: o nó LLM recebe frases prontas com os números; trocar o LLM não muda nenhum número (teste
  `test_llm_so_costura_nunca_muda_numero`).

## Centro de Comando (1.3.0)

```
 audit.jsonl ─┐  aprovacoes.json ─┐  comando.json (pausas, escaladas) ─┐  dados do app ─┐
              ▼                   ▼                                    ▼                ▼
 centro_comando: contextos registros_operacao + aprovacoes + estado_comando (comando.ler) + equipe
                 → código centro_de_comando → comando.calcular(...)  (valida comando.ESQUEMA)
                 → aba Agentes (Agent Control Tower) + aba Negócio (Mission Control) ; rota /comando
 POST /api/comando/{pausar|retomar|rodar|reexecutar|escalar}/<alvo>  → Controle (papel controlar_agentes) + audit
```

- **Pausa** entra no motor: `Motor.executar` checa `motor.pausado(workflow)` logo depois do RBAC. Pausado → linha
  `workflow.executado` com `status="pausado"` e `WorkflowPausado` (HTTP 409). `Gatilhos.tick` e `emitir` pulam o
  pausado e seguem com os outros. Não conta como erro no executivo.
- **Semáforo** por workflow: `pausado` · `vermelho` (última execução real com erro) · `amarelo` (erro no histórico
  ou aprovação dele fora do SLA) · `verde` · `sem_execucao`.
- **Idade da aprovação** = `agora` − `ts` da execução que propôs (lista `propostas` do audit). `agora` é parâmetro
  (`?agora=` na rota), então o teste é determinístico. Acima de `sla_aprovacao_horas` → alerta.
- **Reexecutar** (`comando.reexecucao`): execução `agendado:` usa a entrada e o usuário do próprio gatilho; entrada
  vazia (`hash_entrada` = hash de `{}`) roda como `executar_como` (o agendador) se o workflow aceita esse papel.
  O resto não se refaz: o audit guarda só o hash da entrada (pergunta de RH, por exemplo, não fica salva).
  Execução barrada no escopo também não: refazer repete o bloqueio.
- **Escalar** grava `comando.escalar` e marca o item; `papeis_aprovadores` não muda. Operação nunca aprova.
- **Mission Control**: métricas pelo mesmo `metricas_negocio` + `executivo.metrica` do painel executivo (um teste
  confere que batem); `faltam` = teto(meta% × vencidas) − cobertas; fila de decisão por `fila_de_decisoes` (regra:
  sinais do agente de fundo + situação na fila de aprovação), ordenada por "sem ação" primeiro.
- `run_id` continua a numeração do audit quando o app reinicia (antes recomeçava em 0001).

## Painéis visão geral → detalhe (1.4.0)

```
 URL ?periodo&workflow&gatilho&situacao&dia ──► entrada.filtros do workflow (centro_comando, painel_executivo)
                                                 └► visao.operacao(audit, fila, filtros, agora) → cartões, séries, detalhe
 painel_bi.pagina (navegação + filtros + cartões + grade de gráficos + detalhe)  ◄── graficos.py (SVG puro)
   /comando (Agentes) · /comando/negocio (Negócio) · /executivo · /tendencias
```

- Cada gráfico ignora o PRÓPRIO filtro (o de workflow continua mostrando todos os workflows, com o escolhido em
  destaque) e respeita os outros; o detalhe respeita todos. `visao.normalizar` troca valor desconhecido pelo padrão.
- Negócio e tendências filtram na página (a saída do workflow já tem tudo); agentes e executivo filtram no workflow,
  porque precisam reler o audit com a janela de tempo. `agora` vem de `?agora=` ou do relógio do audit.
- Série de status em ordem fixa ok → negado → pausado → falha: o validador de paleta reprova laranja ao lado de
  vermelho no modo claro; sempre com legenda, tooltip (`<title>`) e vão de 2 px entre segmentos.
- `simular.py`: relógio simulado injetado no `AuditLog`; roda os workflows, gatilhos, aprovações, pausa e escalada
  pelo motor real, com semente fixa. As linhas do audit são reais (corrente íntegra), os dados são fictícios.
- `snapshot_indicadores` passa `{"filtros": {"periodo": "7d"}}` ao cálculo executivo: execuções, chamadas, custo,
  confiança e negados da semana, e não mais o acumulado desde o início.

## Trocar o LLM

`FakeLLM` é determinístico e é o que os testes usam. `OllamaLLM` (`AGENTIC_LLM=ollama`) fala só com
`http://localhost:11434`; se o Ollama não responder, cai no `FakeLLM`. Para outro provedor, crie uma subclasse de
`LLM` com `classificar`, `redigir` e `escolher_ferramenta`: o resto do framework não muda.
