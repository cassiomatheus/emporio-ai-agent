# Comparação local — Gemma 4 12B e Qwen 3.5 9B

Data de referência: **02/11/2026**, America/Belem. Avaliação real solicitada pelo usuário, com dados sintéticos.

**Recomendação atual: manter `qwen3.5:9b` nesta máquina e configuração.** O Qwen concluiu os dois conjuntos sem erro de SDK. O Gemma funcionou com tool calling, mas sofreu **duas quedas do Ollama por falta de RAM (`oom-kill`)**. Assim, ele não superou o Qwen operacionalmente. **Não é possível concluir que sua capacidade de raciocínio seja inferior a partir das notas completas contaminadas pelas quedas.**

## Condições verificadas

Comparação com o mesmo agente, prompts, serviços, regras, gabaritos, seis CSVs sintéticos e PDF sintético compartilhado byte a byte. Foram usados os 40 cenários originais/46 turnos e os 18 adicionais/20 turnos da Fase 12C. Estes últimos já foram vistos em avaliação anterior; não são um novo holdout cego. Nenhum ajuste de prompt, código, dado ou gabarito foi feito para favorecer um modelo.

| Condição | Valor |
|---|---|
| Servidor | Ollama 0.35.0, somente loopback |
| Qwen | `qwen3.5:9b`, 9.0B, Q4_K_M, ID `56671c2ab938` |
| Gemma | `gemma4:12b`, 11.9B, Q4_K_M, ID `6114515d63c1` |
| Contexto | 4096 solicitado e observado para ambos |
| Geração | temperatura 0; reasoning effort none; thinking desligado solicitado |
| Finalização estruturada | ativa para ambos, no adaptador existente |
| Limites | 4 rodadas; 1200 tokens/saída; 60 s/requisição; 120 s/turno |
| Hardware | RTX 3060, 12.288 MiB VRAM; aproximadamente 14,9 GiB RAM física |

Fonte congelada: `38e06ad26f8fee3deed98a30256b7dd0e3d780cc785bb93c16327e82ca641c25`. [Manifesto](model_comparison_gemma4/manifest.json), [modelos/digests instalados](model_comparison_gemma4/installed_models.json) e [integridade final](model_comparison_gemma4/verification.json). As fontes originais do desafio não foram enviadas ao modelo. Sem credenciais ou tokens de sessão nos registros.

O prompt deste projeto foi anteriormente ajustado usando Qwen. Esta é uma comparação de substituição no agente atual, não um ranking geral dos modelos. O backend calcula preços e monta a resposta factual; a avaliação mede principalmente seleção/argumentos de tools, plano e execução segura.

## Resultado operacional completo

| Execução | Casos aprovados | Turnos aprovados | Estado |
|---|---|---|---|
| Qwen · 40 casos | 38/40 | 44/46 | Sem erro de SDK |
| Gemma · 40 casos (OOM) | 15/40 | 18/46 | Afetada por OOM e perda de conexão |
| Qwen · 18 adicionais | 15/18 | 17/20 | Sem erro de SDK |
| Gemma · 18 adicionais (OOM) | 12/18 | 13/20 | Afetada por OOM e perda de conexão |

**As notas de 15/40 e 12/18 do Gemma não são uma estimativa justa de sua qualidade linguística.** O harness continuou após a indisponibilidade do serviço e registrou falhas de provedor nos cenários restantes. Elas são falhas reais da execução ponta a ponta, mas não erros comprovados de entendimento. Os JSONs originais foram preservados sem substituir ou melhorar notas.

Na primeira rodada, o erro ocorreu em PRE03 durante a finalização estruturada: um `InternalServerError`, seguido de **24 APIConnectionError**. Na segunda rodada, após reinício automático, houve **5 APIConnectionError** nos casos HLD15–18. O journal confirmou duas ocorrências de `Failed with result oom-kill` e dois reinícios automáticos. [Eventos filtrados](model_comparison_gemma4/oom_events.json). Não foram expostos logs completos, ambiente ou prompts.

O smoke anterior foi aprovado: Gemma escolheu `search_products`, executou a consulta real e concluiu o plano. Seu preload levou 50,734 s e o primeiro turno 26,372 s. Isso demonstra compatibilidade funcional básica; as quedas seguintes não são evidência de ausência de suporte a ferramentas. A segunda rodada em outro conjunto reproduziu o problema de memória; não foi feita uma terceira tentativa contínua idêntica dos 40 casos sem corrigir essa condição.

## Qualidade nos trechos que funcionaram

Foram comparados somente turnos nos quais **ambos** tiveram inferência real e nenhuma requisição HTTP/SDK falhou. Guards e injeções de provedor ficam fora desta tabela. A seleção é pós-hoc, determinada pela queda; não é uma amostra independente nem substitui o conjunto completo. [Subconjuntos pareados](model_comparison_gemma4/paired_valid_subsets.json).

| Trecho pareado | Qwen: tarefas | Gemma: tarefas | Mediana Qwen / Gemma (s) |
|---|---|---|---|
| Catálogo/preços antes da primeira queda | 10/10 | 10/10 | 3.75 / 5.80 |
| 13 turnos adicionais antes da segunda queda | 10/13 | 11/13 | 4.46 / 5.32 |

Gemma acertou o filtro de cor natural de HLD02, omitido pelo Qwen. Porém, em HLD03 usou `term=ukulele`, que não encontra o instrumento pelos nomes sintéticos, em vez do filtro da categoria; terminou pedindo orçamento. Ambos falharam em HLD14/frete por ausência de evidência lexical. Portanto, a troca não resolveu integralmente as falhas residuais.

O Qwen falhou em POL08, recusando a pergunta sobre senha do Wi-Fi sem executar a busca exigida pelo gabarito, e em MUL04, tentando chamar a função inexistente `answer_order` após consultar oferta/horário. O backend recusou a função e respondeu com encaminhamento, sem divulgar os fatos parciais. As duas falhas permanecem nas notas. A rodada atual deu 38/40; as duas rodadas históricas da Fase 12C deram 39/40. Temperatura 0 não torna todo o diálogo idêntico: IDs de chamada, cache e condições de execução variam.

## Métricas e limites de interpretação

| Execução | Seleção de tools | Argumentos | Grounding aplicável | Compliance |
|---|---|---|---|---|
| Qwen · 40 casos | 44/46 | 43/46 | 27/27 | 46/46 |
| Gemma · 40 casos (OOM) | 18/46 | 18/46 | 8/8 | 46/46 |
| Qwen · 18 adicionais | 20/20 | 18/20 | 14/14 | 20/20 |
| Gemma · 18 adicionais (OOM) | 15/20 | 14/20 | 10/10 | 20/20 |

As métricas do sistema completo incluem guards. As quedas do Gemma geraram respostas seguras sem fatos; isso ajuda a manter compliance automático alto, mas não comprova capacidade do modelo nos casos não processados. Em cada suíte de 40, ROB05/06/07 contêm injeções determinísticas de timeout/chamada inválida, sem inferência real nesses turnos. Os grupos estão separados no [JSON de comparação](model_comparison_gemma4/comparison.json). Grounding não mede adequação de todos os filtros; os checks de compliance têm cobertura limitada. Não houve LLM-juiz.

| Execução | Requisições / com usage | Finalizações | Tokens conhecidos | Erros de requisição |
|---|---|---|---|---|
| Qwen · 40 casos | 94 / 94 | 27 | 166244 | 0 |
| Gemma · 40 casos (OOM) | 56 / 31 | 10 | 46227 | 25 |
| Qwen · 18 adicionais | 46 / 46 | 14 | 81835 | 0 |
| Gemma · 18 adicionais (OOM) | 37 / 32 | 8 | 49085 | 5 |

Os tokens do Gemma são **parciais**, pois várias requisições falharam. Quantidades de tokens também dependem do tokenizer. Não se conclui que ele seja mais barato/eficiente por reportar menos tokens. Não há custo financeiro ou energético medido. Preload e consultas de recursos não entram na contagem Responses.

A mediana global de 13,9 ms do primeiro relatório Gemma está dominada pelas falhas imediatas de conexão: **não é tempo de geração do modelo**. Os tempos dos subconjuntos válidos acima incluem pipeline de ferramentas/finalização e, possivelmente, inicialização residual. A carga do desktop não foi isolada; p95 usa nearest-rank. Não é comparação de throughput concorrente.

## Memória e estabilidade

| Execução | VRAM total máxima observada (MiB) | RAM disponível mínima observada (KiB) | Contexto |
|---|---|---|---|
| Qwen · 40 casos | 6664 | 8658784 | [4096] |
| Gemma · 40 casos (OOM) | 9084 | 1328136 | [4096] |
| Qwen · 18 adicionais | 6663 | 8758528 | [4096] |
| Gemma · 18 adicionais (OOM) | 9009 | 305376 | [4096] |

O Gemma chegou a até **9.084 MiB de VRAM total** (incluindo desktop) e a apenas **298 MiB de RAM disponível** na segunda rodada. O evento confirmado foi do OOM killer do sistema, portanto envolve RAM do host, não uma demonstração de estouro exclusivo da VRAM. O Qwen manteve mais de 8 GiB de RAM disponível nas amostras da suíte principal e não provocou novos reinícios.

A amostragem ocorre a cada três segundos e pode perder picos. Nesses registros aparecia somente o modelo avaliado, sem executar os dois em paralelo. O campo `size_vram` informado por `/api/ps` foi 1.085.926.276 bytes para Gemma e 5.589.560.196 para Qwen; não foi interpretado como a mesma medida do consumo global obtido com `nvidia-smi`. Os valores brutos foram preservados, sem inventar explicação para a diferença.

Não se identificou a alocação interna específica responsável pelo consumo do Gemma, nem se comprovou vazamento no backend. Não houve alteração de swap, configuração do serviço, quantização, contexto, bibliotecas ou sistema operacional. Não foram fechados programas do usuário. A menor condição necessária para uma comparação limpa é repetir sem pressão de RAM/OOM, com uma configuração de memória estável e os mesmos parâmetros para ambos. Mais memória livre ou um perfil de consumo menor precisam ser validados, não presumidos como solução.

## Reprodução e arquivos

Os quatro relatórios completos: [Qwen 40](model_comparison_gemma4/qwen_40_run1.json), [Qwen 18](model_comparison_gemma4/qwen_18_run1.json), [Gemma 40 com queda](model_comparison_gemma4/gemma_40_run1.json), [Gemma 18 com queda](model_comparison_gemma4/gemma_18_run1.json). [Smoke Gemma](model_comparison_gemma4/gemma_smoke.json). Traces incluem ferramentas/argumentos, resultados, plano candidato, resposta entregue, latência e uso disponível, apenas de fontes sintéticas.

Comandos usados, com tags/caminhos exclusivos para não sobrescrever evidências:

```bash
python -m scripts.benchmark_agent --tag gemma4_40_r1 --model gemma4:12b --context 4096 --thinking none --finalization on --rich-trace --work-dir data/derived/model_comparison_gemma4_20261102 --output docs/model_comparison_gemma4/gemma_40_run1.json
python -m scripts.benchmark_agent --tag gemma4_18_r1 --model gemma4:12b --cases-file tests/evaluations/holdout_12c.json --context 4096 --thinking none --finalization on --rich-trace --work-dir data/derived/model_comparison_gemma4_20261102 --output docs/model_comparison_gemma4/gemma_18_run1.json
python -m scripts.benchmark_agent --tag qwen35_40_r1 --model qwen3.5:9b --context 4096 --thinking none --finalization on --rich-trace --work-dir data/derived/model_comparison_gemma4_20261102 --output docs/model_comparison_gemma4/qwen_40_run1.json
python -m scripts.benchmark_agent --tag qwen35_18_r1 --model qwen3.5:9b --cases-file tests/evaluations/holdout_12c.json --context 4096 --thinking none --finalization on --rich-trace --work-dir data/derived/model_comparison_gemma4_20261102 --output docs/model_comparison_gemma4/qwen_18_run1.json
```

Os quatro comandos retornaram 1 por falhas medidas e geraram relatórios íntegros; isso não significa aprovação de todos os casos. Não repetir o perfil Gemma continuamente sem resolver a pressão de memória. O serviço reiniciou automaticamente após as duas quedas; nenhuma mudança de segurança ou função fictícia foi introduzida.

Código, dados e gabaritos permaneceram iguais aos hashes iniciais; Ruff check aprovado. Não houve modificação funcional e não se apresenta uma nova execução pytest nesta comparação. O ambiente `.env`/modelo da interface permaneceu Qwen; ao terminar, o Ollama estava ativo com Qwen carregado em 4096. Nenhum modelo foi baixado/removido, nem houve commit, push ou publicação.

**Decisão:** Qwen é a opção operacional recomendada neste ambiente hoje. A capacidade global de qualidade do Gemma permanece inconclusiva por falta de uma execução completa estável. Para substituir o modelo, é necessário resolver essa condição e repetir os conjuntos, sem mudar gabaritos. As limitações comerciais anteriores do agente permanecem.

