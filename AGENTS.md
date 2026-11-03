# AGENTS.md — Plano de implementação orientado ao Codex

**Projeto:** Empório da Música — Agente de Atendimento com IA  
**Contexto:** desafio técnico de AI Engineer da Artefact  
**Linguagem principal:** Python  
**Estado:** especificação aprovada; implementação ainda deve ser realizada  
**Última revisão da especificação:** 31/10/2026  
**Uso:** coloque **este arquivo na raiz do repositório** aberto no VS Code. Ele é o guia permanente do Codex; execute cada fase com os prompts da seção 15.

> **REGRA DE EXECUÇÃO PARA O CODEX:** este documento define o projeto inteiro, mas **não autoriza implementar tudo de uma vez**. Em cada solicitação, implemente **somente a fase indicada pelo usuário**, preservando as anteriores. Antes de editar, examine o estado real do repositório; depois, execute verificações e apresente um relatório conciso com arquivos alterados, testes, decisões e pendências. Se uma fase ainda não foi pedida, não a antecipe. Não declare testes ou resultados que não foram executados.

## 0. Uso no VS Code

1. Abra/crie `emporio-ai-agent/` no VS Code e inicialize o Git. Salve **este arquivo na raiz** como `AGENTS.md`, reconhecido pelo Codex como instrução persistente.
2. Coloque os 6 CSVs e o PDF em `data/raw/` **localmente**. Os arquivos fornecidos têm nomes como `desafio_tecnico_ai_eng - products.csv`; implemente mapeamento para nomes canônicos sem modificar originais. Consulte os cuidados de publicação da seção 11.
3. No Codex, envie primeiro o **Prompt 00** (seção 15). Depois solicite **uma fase por vez** e confira diffs, testes e decisões antes de avançar.
4. Faça commits progressivos; jamais inclua segredos. No final, verifique a reprodução por README e prepare 5 exemplos reais.

Referência oficial do `AGENTS.md`: https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex

## 1. Objetivo, entregáveis e limites

Criar agente conversacional **de texto**, em português, para a loja fictícia Empório da Música, usando **CSV estruturado**, **PDF de políticas** e **LLM com tool calling**. O desafio mede raciocínio, clareza, iniciativa e justificativa técnica mais do que complexidade.

**Exigido:** persona profissional e acolhedora; busca de produtos, preços, estoque, promoções e status de pedidos; respostas sobre políticas; tratamento de fora do escopo; Python; GitHub **público com histórico real de commits**, README explicando execução, modelo, framework, retrieval, limitações e uso honesto de Codex; 3–5 conversas (planejar 5), sendo uma não trivial. Link enviado por e-mail no prazo externo ao PDF. Não alterar repo após a data de entrega.

**MVP P0:** (a) catálogo/estoque; (b) ofertas, PIX, parcelas; (c) consulta de políticas com fonte; (d) pedidos somente com autorização no backend; (e) LLM integrando ferramentas com falhas seguras; (f) testes e reprodução.

**Fora do escopo:** ações de compra/cancelamento/reembolso/estoque, pagamento real, WhatsApp real, autenticação real, API de transportadora, dados em tempo real, multiagentes, fine-tuning e infraestrutura distribuída. Não aprovar/recusar devoluções sem informações necessárias.

## 2. Princípios de engenharia — instruções ao Codex

1. **Fontes:** SQLite derivado dos CSVs para dados; PDF para políticas. Nenhum valor/preço/estoque/pedido inventado. Os arquivos são snapshots, não dados ao vivo.
2. **Determinismo:** cálculos, filtros, autorização e aplicação de regras **em Python**, nunca delegados à geração livre do LLM.
3. **Tools restritas:** nenhuma execução de SQL arbitrário pelo LLM. Contratos de entrada e saída validados e erros tipados.
4. **Camadas:** interface → agente → tools → serviços → repositórios/retrieval; separar responsabilidades.
5. **Falha segura:** sem evidência, esclarecer, abster-se ou direcionar para humano; não prometer ações externas.
6. **Privacidade:** isolamento de sessão; não registrar senhas, PII integral, prompts sensíveis ou documento interno em logs. ID declarado pelo usuário não autentica.
7. **Qualidade:** Python tipado, Pydantic em fronteiras, testes pytest, Ruff, código sem complexidade gratuita.
8. **Originais imutáveis:** nunca editar CSV/PDF brutos; transformações documentadas na ingestão.
9. **Reprodutibilidade:** configurações por ambiente, testes offline com mocks, README executável.
10. **Implementação incremental:** **somente fase solicitada**; inspecionar repositório, registrar diff, testes reais, decisões e pendências. Não declarar conclusões não verificadas.

## 3. Dados disponíveis — inventário verificado

Resultados obtidos dos **anexos CSV fornecidos**, não de uma fonte em tempo real:

| Arquivo canônico | Registros | Colunas originais |
|---|---:|---|
| `categories.csv` | 9 | `category_id`, `name`, `description` |
| `products.csv` | 65 | `product_id`, `price_brl`, `name`, `category_id`, `description`, `stock_quantity`, `status`, `specs`, `created_at` |
| `customers.csv` | 50 | `customer_id`, `name`, `phone`, `email`, `city` |
| `orders.csv` | 20 | `order_id`, `customer_id`, `order_date`, `status`, `total_brl`, `payment_method`, `tracking_code`, `estimated_delivery`, `notes` |
| `order_items.csv` | 22 | `order_id`, `quantity`, `product_id` |
| `promotions.csv` | 25 | `promotion_id`, `product_id`, `discount_percent`, `description`, `is_active` |

**Observações comprovadas nos dados:**
- `products.status`: `active` (62), `discontinued` (2), `coming_soon` (1).
- `promotions.is_active`: 4 ativas e 21 inativas; **não existem colunas de validade temporal**.
- `orders.status`: 7 `delivered`, 4 `confirmed`, 4 `pending`, 4 `cancelled`, 1 `shipped`.
- `orders` têm datas entre 15/10/2025 e 22/03/2026; o dataset é um **snapshot**.
- Há 12 pedidos sem `tracking_code`, 12 sem `estimated_delivery` e 16 sem `notes`.
- Relacionamentos existentes não apresentam IDs órfãos nas tabelas fornecidas; não há duplicidade da chave composta `(order_id, product_id)` em `order_items`.
- O campo `products.specs` contém JSON serializado em texto.
- Os totais históricos dos pedidos 3 e 20 diferem da soma calculada usando **preços atuais dos produtos** (diferenças de R$ 48 e R$ 88, respectivamente); não corrigir nem recalcular pedido histórico usando preço atual.
- Produto 130, `coming_soon`, tem estoque 2; produto 136, `discontinued`, tem estoque 13. Estoque positivo **não basta** para afirmar disponibilidade.
- Promoção ativa: produto 127, **Kalani KAL-700T Tenor Natural**, preço de tabela **R$ 359,00**, desconto **10%**, valor resultante **R$ 323,10**, sem acumular 5% PIX.

**Relacionamentos previstos:** `products.category_id → categories.category_id`; `orders.customer_id → customers.customer_id`; `order_items.order_id → orders.order_id`; `order_items.product_id → products.product_id`; `promotions.product_id → products.product_id`. Em `order_items` usar chave composta apenas após validar unicidade. Não criar campos fictícios como `delivered_at`, `unit_price_at_purchase` ou `promotion_start_date` no banco de origem; uma camada derivada deve distinguir explicitamente dados calculados de dados observados.

## 4. Regras de negócio

Fonte: `políticas_da_loja.pdf`, v2.1, junho/2025, e CSVs. Não substituir texto-fonte por interpretação inventada.

| ID | Regra e implementação |
|---|---|
| RN-01 | Disponível apenas se `status='active'` **e** `stock_quantity>0`; `discontinued`/`coming_soon` não vendáveis. |
| RN-02 | Preço consultado no catálogo; usar `Decimal`/centavos e arredondamento monetário explícito. |
| RN-03 | Oferta elegível só com `is_active=1` no snapshot; não afirmar vigência futura/atual externa. |
| RN-04 | Promoções **não acumulam** com desconto PIX de 5% sobre preço de tabela. |
| RN-05 | Até 12 parcelas sem juros: 4–6x com parcela mínima R$ 80; 7–12x mínima R$ 100. Regra 1–3x menciona exceção abaixo de R$ 50: documentar interpretação conservadora. |
| RN-06 | Direito de arrependimento online: até 7 dias corridos **do recebimento**; não usar `order_date` nem `estimated_delivery` como data real. |
| RN-07 | Troca por defeito (30 dias), troca por preferência e garantia legal (90 dias) são procedimentos distintos; não negar direitos automaticamente. |
| RN-08 | Frete metropolitano grátis **acima** de R$ 500 e R$ 35 **abaixo** de R$ 500; valor exato R$ 500 não definido literalmente. |
| RN-09 | Consulta de pedido exige autorização conferida pelo backend; conhecer ID de pedido não comprova identidade. |
| RN-10 | Produto descontinuado/indisponível: não ofertar; alternativas apenas após consulta de estoque. |
| RN-11 | Exibir oferta com preço original, preço promocional e percentual. |
| RN-12 | Loja vende instrumentos, **não** acessórios; redirecionar educadamente. |
| RN-13 | Persona informal e profissional; reclamação/dúvida incerta pode ser encaminhada a humano. |
| RN-14 | Sem código de rastreamento: informar ausência, não fabricar código, data ou entrega. |

**Informações adicionais:** funcionamento segunda–sexta 09h–18h, sábado 09h–13h, domingos/feriados fechado; horários especiais variáveis. Não afirmar “aberta agora” sem fuso de Campo Grande e feriados. Manual cita contatos divergentes entre seções 1.2 e 7, e variação de e-mail: manter fidelidade à fonte e explicitar ambiguidade. Para devolução considerar também condições de embalagem, custos e reembolso do manual.

**Decisões a documentar (`docs/decisions.md`):** DEC-01 snapshot ≠ real time; DEC-02 não há `delivered_at`; DEC-03 contatos/e-mail divergentes; DEC-04 valor de frete exatamente R$ 500; DEC-05 promoções sem datas; DEC-06 clientes sem autenticação real; DEC-07 totais históricos ≠ preço atual; DEC-08 30 dias de troca vs 90 de garantia; DEC-09 PDF classificado como interno — não divulgar integralmente nem publicar sem permissão.

## 5. Matriz de requisitos

### Requisitos funcionais (RF)

| ID | Requisito | Prio. |
|---|---|---|
| RF-01 | Receber e responder mensagens em português | P0 |
| RF-02 | Manter persona coerente com a loja | P0 |
| RF-03 | Filtrar catálogo por nome, categoria, faixa de preço e características | P0 |
| RF-04 | Verificar estoque e disponibilidade comercial | P0 |
| RF-05 | Consultar preços e aplicar descontos/parcelas válidos | P0 |
| RF-06 | Consultar pedidos com autorização prévia | P0 |
| RF-07 | Recuperar políticas por tema/pergunta, citando seção | P0 |
| RF-08 | Combinar resultados de duas ou mais ferramentas | P0 |
| RF-09 | Pedir dados adicionais quando indispensáveis | P0 |
| RF-10 | Recusar/redirecionar demandas fora do escopo | P0 |
| RF-11 | Manter contexto de referências como “esse violão” por sessão | P1 |
| RF-12 | Recomendar alternativas realmente disponíveis | P1 |
| RF-13 | Explicar limitações e encaminhar casos incertos | P1 |
| RF-14 | Emitir logs técnicos rastreáveis, sem dados sensíveis | P1 |

### Requisitos não funcionais (RNF)

| ID | Requisito | Prio. | Verificação |
|---|---|---|---|
| RNF-01 | Respostas verificáveis e fundamentadas | P0 | Comparar fontes e resposta esperada |
| RNF-02 | Proteção de PII e isolamento de sessão | P0 | Testes de acesso indevido |
| RNF-03 | Regras executadas de forma determinística | P0 | Testes unitários |
| RNF-04 | Falhas seguras, sem inventar dados | P0 | Simulação de erro/ausência |
| RNF-05 | Ambiente reproduzível | P0 | Setup limpo via README |
| RNF-06 | Componentes desacoplados | P1 | Testes isolados |
| RNF-07 | Rastreabilidade de consultas e fontes | P1 | Logs com IDs e seções, sem PII |
| RNF-08 | Latência adequada, com mediana/p95 mensuradas | P1 | Benchmark observado; sem meta artificial |
| RNF-09 | Custo e consumo de tokens observáveis | P1 | Métricas quando API informar uso |
| RNF-10 | Troca de provedor sem reescrita dos serviços | P2 | Teste de adaptador |

### Critérios de aceitação e rastreabilidade (CA)

| ID | Requisitos relacionados | Cenário | Resultado esperado |
|---|---|---|---|
| CA-01 | RF-03/04, RN-01 | Violões até R$ 800 disponíveis | Apenas itens que atendam categoria, faixa e disponibilidade |
| CA-02 | RF-04, RN-01 | Estoque zero | Não anunciar disponibilidade |
| CA-03 | RF-04, RN-10 | Produto `discontinued` com estoque | Não anunciar disponível |
| CA-04 | RF-05, RN-03/04 | Kalani 127 em promoção e PIX | R$ 359,00 → 10% → R$ 323,10; **não** 15% acumulados |
| CA-05 | RF-05, RN-05 | Parcelamento com parcela mínima inválida | Não ofertar condição impossível |
| CA-06 | RF-07, RN-06/07 | Devolução sem data de recebimento | Solicitar dados e não decidir elegibilidade definitiva |
| CA-07 | RF-06, RN-09 | Consulta a pedido de outro cliente | Negar acesso sem expor dados |
| CA-08 | RF-06, RN-14 | Pedido sem rastreio | Informar ausência, não inventar código |
| CA-09 | RF-08, RN-04/05 | Promoção + parcelas na mesma mensagem | Consultar fontes necessárias e aplicar regras |
| CA-10 | RF-11 | “Quanto custa esse violão?” seguido de “E em 6x?” | Manter produto de referência da sessão |
| CA-11 | RF-10, RN-12 | Pedido de palhetas ou cabos | Explicar escopo e redirecionar |
| CA-12 | RNF-04 | Falha do serviço de catálogo | Não fornecer preço sem verificação |
| CA-13 | RNF-01/07 | Política de garantia | Resposta condizente, seção rastreável |
| CA-14 | RF-09 | Busca ambígua com requisito essencial ausente | Perguntar somente o necessário |

**Definição de pronto:** um P0 só está concluído quando existe implementação, teste verificável, documentação mínima e evidência da execução. Não usar “passou” para teste não executado.

## 6. Arquitetura técnica acordada

```text
Mensagem do usuário (CLI / FastAPI / UI opcional)
    |
    v
Sessão + contexto autorizado + limites
    |
    v
Orquestrador LLM (persona + decisão de tool calling)
    |
    +--> Tools de catálogo ------> ProductService ------> SQLite
    |
    +--> Tools de preços --------> PricingService ------> SQLite + regras
    |
    +--> Tools de pedidos -------> OrderService --------> SQLite + autorização
    |
    +--> Tools de políticas -----> PolicyService -------> Retriever PDF
    |
    v
Validação de resultados / políticas / segurança / limites
    |
    v
Resposta clara e fundamentada + logs técnicos controlados
```

**Tecnologias inicialmente preferidas:** Python 3.11+; `uv` (ou venv/pip se mais simples); FastAPI, Pydantic, SQLite, PyMuPDF, pytest, Ruff; SDK oficial de um LLM com tool calling confiável. **Não fixar provedor/modelo pago sem testar disponibilidade e orçamento.** Usar variáveis de ambiente para configurar modelo/credenciais; ter testes offline por mocks. Para o PDF pequeno, começar com recuperação **por seção + busca lexical** (eventualmente SQLite FTS5); introduzir embeddings só se testes mostrarem necessidade. Não adotar LangGraph, ReAct genérico, multiagentes ou banco vetorial externo sem justificativa mensurável.

### Diretórios propostos (adaptar se o repositório já tiver convenções)

```text
emporio-ai-agent/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── app/
│   ├── main.py
│   ├── config.py
│   ├── agent/{orchestrator.py,prompts.py,memory.py}
│   ├── tools/{product_tools.py,pricing_tools.py,order_tools.py,policy_tools.py}
│   ├── services/{product_service.py,pricing_service.py,order_service.py,policy_service.py}
│   ├── retrieval/{document_loader.py,retriever.py}
│   ├── database/{connection.py,models.py,repository.py}
│   └── schemas/{requests.py,responses.py}
├── data/
│   ├── raw/            # originais locais, acesso restrito, revisar publicação
│   └── samples/        # fixtures sintéticos redistribuíveis
├── scripts/{inspect_data.py,ingest_data.py}
├── tests/{unit,integration,evaluations}/
├── docs/{requirements.md,decisions.md,architecture.md,evaluation.md}
└── examples/           # 5 conversas validadas
```

Não criar dezenas de arquivos vazios. Criar apenas os arquivos necessários ao trabalho da fase, com responsabilidades claras.

## 7. Contratos preliminares das ferramentas

| Tool | Parâmetros conceituais | Retorno e segurança |
|---|---|---|
| `search_products` | termo, categoria, preço mín./máx., especificações, limite | IDs, nome, preço, status, estoque, disponibilidade verificada; paginação/limite |
| `get_product_details` | `product_id` ou busca exata por nome | Produto existente ou `not_found`, sem inventar atributos |
| `get_product_offers` | `product_id`, contexto da modalidade de pagamento | Preço original, desconto permitido, valor final, condições elegíveis, regra aplicada |
| `get_order_status` | `order_id` e **identidade autorizada injetada pelo backend** | Status e campos permitidos; `forbidden` e `not_found` sem vazamento |
| `search_store_policies` | tema/pergunta, `top_k` | Excerto breve, seção, página, versão e grau de correspondência |
| `get_store_info` | assunto (endereço, horário, contatos) | Informação pública com referência e alertas sobre ambiguidades |

**Requisitos de contrato:** entradas validadas por Pydantic; limites de texto/itens; mensagens de erro tipadas; resultados estáveis; sem expor rastros de exceção ao cliente; nunca confiar em argumentos fornecidos pelo LLM para liberar acesso. O agente pode chamar várias ferramentas em sequência, com limite configurável de rodadas e timeout.

## 8. Fases incrementais — apenas uma por solicitação

### Fase 00 — Descoberta (sem editar)
Inspecionar Git, Python, estrutura, dados presentes, configuração e riscos. Apresentar plano concreto da Fase 01 e lacunas. **Não programar.**

### Fase 01 — Fundação
Criar projeto Python, `pyproject.toml`, ambiente, `.env.example`, `.gitignore`, README inicial, pytest/Ruff, execução mínima e diretórios necessários. Evitar arquivos vazios. **Aceite:** smoke test, importação, lint/comandos funcionando. **Commit:** `chore: initialize project structure and development environment`.

### Fase 02 — Banco e ingestão
Criar `scripts/inspect_data.py`, diagnóstico de schemas/nulos/FKs; modelar SQLite; `scripts/ingest_data.py` transacional e **idempotente**, normalização documentada e originais imutáveis. Converter `specs` JSON; preservar valores monetários e `orders.total_brl`. **Aceite:** contagens 9/65/50/20/22/25, sem FKs inválidas, executar duas vezes sem duplicar; testes offline. **Commit:** `feat: implement relational data ingestion and validation`.

### Fase 03 — Serviços e regras
Criar `ProductService` (filtro, status, estoque), `PricingService` (ofertas, PIX, parcelamento) e `OrderService` (consulta protegida/histórico), independentes de LLM. Separar serviço de repositório. **Aceite:** CA-01 a CA-05, CA-07/08 em testes; oferta do Kalani 127 = R$ 323,10. **Commit:** `feat: implement business services and deterministic rules`.

### Fase 04 — Políticas/PDF
Extrair PDF por página e seção, incluindo condições/tabelas. Indexar por seção + busca lexical, devolver trecho breve e metadados página/seção/versão. Testar questões de PIX, parcelas, frete, garantia, devolução; medir **Recall@3 observado**. Sem evidência, retornar ausência. **Commit:** `feat: implement document retrieval with source metadata`.

### Fase 05 — Ferramentas
Expor tools da seção 7 com Pydantic, limites, erros padronizados e autorização fora do LLM. Não permitir SQL livre. **Aceite:** testes de contratos, inválidos, falhas, `forbidden` e vazio; serviços funcionam isolados. **Commit:** `feat: expose validated tools for agent orchestration`.

### Fase 06 — LLM/orquestração
Integrar SDK de modelo configurável, persona, loop de tool calling, múltiplas tools, limites de rodadas e timeout, resultados verificados, mocks offline. Primeiro diálogo: violões de nylon até R$ 1.000. **Aceite:** tool correta e resposta conferida; falha de tool não produz preço inventado. **Commit:** `feat: integrate LLM and tool-calling agent loop`.

### Fase 07 — Sessões/segurança
Implementar histórico separado por sessão, referências conversacionais, acesso aos pedidos restrito a sessão de demonstração previamente autorizada **no servidor**, sem alegar autenticação real; logs sanitizados, abstenção, tratamento de falhas. **Aceite:** CA-06, 07, 08, 10, 11, 12, 14; teste de duas sessões e tentativa de ler pedido alheio. **Commit:** `feat: add session management and secure tool access`.

### Fase 08 — API/CLI
CLI simples para depuração; FastAPI com `POST /sessions`, `POST /chat`, `GET /health`, reutilizando mesmo orquestrador. UI web é opcional. **Aceite:** testes TestClient, schemas, sessões, HTTP errors, documentação de execução. **Commit:** `feat: expose conversational agent through FastAPI`.

### Fase 09 — Avaliação integrada
Conjunto de ~40 cenários (catálogo 8; preço/promoções 6; políticas 8; pedidos 6; múltiplas etapas 5; robustez 7). Gabaritos determinísticos; medir seleção de tools, sucesso, fundamentação, compliance, latência mediana/p95 e tokens/custo quando possível. Distinguir execução offline vs API real e documentar falhas. **Commit:** `test: add agent evaluation suite and robustness tests`.

### Fase 10 — Documentação e entrega
README completo (configuração, modelo, escolhas, arquitetura, retrieval, testes, limites, uso de Codex), 5 conversas demonstrativas reais/simuladas rotuladas, revisão de segredos e publicação dos anexos, execução limpa e Git progressivo. Não publicar sem autorização nem mudar após deadline. **Commit:** `docs: finalize reproducible submission and example conversations`.

## 9. Testes e demonstrações

**Casos obrigatórios:** filtro de violões por preço/corda/estoque; produto zerado, `discontinued` e `coming_soon`; Kalani 127 com 10% sem PIX adicional; oferta inativa; limites das parcelas; pedido histórico sem recálculo; pedido sem rastreamento; acesso indevido; devolução sem recebimento real; garantia 90 dias vs troca 30 dias; referência “esse violão ... e em 6x”; acessório fora de escopo; ausência de produto, falha de tool e prompt injection.

**Cinco arquivos em `examples/`:** `01_catalogo.md`, `02_promocao_pagamento.md`, `03_pedido_protegido.md`, `04_devolucao.md`, `05_fora_escopo.md`. Para cada: contexto, mensagens, tools e respostas **sanitizadas**, regras/fontes e interpretação. Exemplos devem ser provenientes de execução real ou **rotulados claramente como simulação**, nunca alegar resultado não medido.

**Relatório `docs/evaluation.md`:** versão, modelo, dataset de avaliação, gabaritos, número de casos, métricas observadas, exemplos de erros, latência/custo se medidos, limitações e melhorias. Preferir gabaritos determinísticos e pequena revisão humana para ambiguidade a depender só de LLM-juiz.

## 10. Decisões que precisam ser justificadas no README

| Escolha | Justificativa defendível | Alternativa não escolhida |
|---|---|---|
| SQLite | Relações claras e dados pequenos, consultas determinísticas e configuração local | Agente SQL livre, DB remoto sem necessidade |
| Tool calling | Permite ao LLM coordenar consultas controladas | RAG puro sobre tabelas |
| Recuperação por seção | Manual curto com tópicos/tabelas semânticas | Banco vetorial externo no primeiro momento |
| Serviços para regras | Cálculos e autorizações testáveis | Regras apenas no prompt |
| FastAPI + CLI | API integrável com depuração simples | Interface elaborada antes do núcleo |
| Sessões isoladas | Continuidade sem mistura de clientes | Memória global ou permanente sem justificativa |
| Avaliação automatizada | Evidência mensurável e repetível | Apenas 3–5 demonstrações escolhidas |

Adiar decisões definitivas sobre modelo/provedor até um teste pequeno com qualidade de tool calling, português, custo e latência. Se escolher modelo local, documentar memória/hardware; se API paga, configurar credencial por ambiente e custo.

## 11. Segurança da publicação e políticas de dados

O README exige repositório **público**, mas o PDF fornecido se identifica como **manual interno de uso restrito** e há informações pessoais fictícias nos CSVs. Antes de publicar, confirmar se a redistribuição dos anexos é permitida. **Não presumir automaticamente que autorização de uso no desafio implica autorização de publicação integral.**

- `.gitignore`: incluir `.env`, tokens, bases locais, logs, caches, arquivos `data/raw/` e arquivos internos não autorizados.
- Manter os originais locais em `data/raw/` para reprodução durante o desenvolvimento.
- Disponibilizar **fixtures sintéticas pequenas** em `data/samples/` e um caminho de execução sem os originais, caso não haja autorização para republicar.
- Não imprimir clientes/contatos em logs públicos, exemplos, traces ou testes.
- Se o projeto usar o PDF local, documentar onde o avaliador deve colocá-lo e como executar um modo demonstrativo sem o documento original.
- Documentar abertamente as limitações do modo demonstrativo e o que precisa ser fornecido pelo avaliador para executar a versão integral.
- Não implementar rota HTTP pública para consultar PII sem autenticação real; pedidos no protótipo devem usar contexto de sessão de demonstração com dados sanitizados e autorização gerenciada pelo backend.

## 12. Definição de concluído e relatório do Codex

Uma fase termina apenas quando: código delimitado, testes relevantes executados (ou bloqueio explicado), lint quando disponível, sem credenciais expostas, documentação atualizada, diff revisável. Responder sempre com **Implementado; Arquivos; Testes e saídas reais; Decisões/limitações; Próxima fase**. Não fazer commit automaticamente sem autorização; não reescrever histórico.

## 13. Armadilhas a evitar

Não afirmar tempo real com CSV; não acumular PIX e promo; não confundir estoque com disponibilidade; não inferir data de recebimento; não liberar pedido por ID declarado; não recalcular total histórico; não delegar cálculos e autorização ao LLM; não inventar política; não misturar sessões; não fabricar resultados; não publicar material interno/PII/segredos; não acrescentar infraestrutura sem necessidade.

## 14. Primeiro marco funcional

Pergunta “Quais violões de nylon disponíveis custam até R$ 1.000?” → LLM seleciona tool → serviço consulta CSV/SQLite → aplica status/estoque/preço → resposta verificada → teste valida resultado. Esse corte vertical reúne partes das Fases 01–03 e 05–06; não exige API ou toda a recuperação documental.

## 15. Prompts prontos para Codex — **um por vez**

**Primeiro prompt obrigatório:**

> **Prompt 00.** Leia `AGENTS.md` e faça descoberta **somente leitura** do repositório. Informe estado real (Git, Python, arquivos e dados), ausências, riscos e proposta exata da Fase 01. Não programe, não invente resultados e não antecipe outras fases.

**Prompts seguintes, enviar separadamente após revisar cada entrega:**

- **01:** “Execute **somente a Fase 01** do `AGENTS.md`. Crie fundação mínima, testes e README inicial; rode verificações e reporte o diff. Não implemente serviços ou agente.”
- **02:** “Execute **somente a Fase 02**. Inspecione os seis CSVs em `data/raw/`, modele SQLite e implemente ingestão transacional idempotente, sem alterar originais. Teste contagens, FKs e segunda importação.”
- **03:** “Execute **somente a Fase 03**. Crie serviços de catálogo, preços e pedidos com regras determinísticas e testes; não use LLM nem desenvolva UI.”
- **04:** “Execute **somente a Fase 04**. Extraia PDF por seções com metadados; crie recuperação leve e teste Recall@3 com perguntas reais; não publique o documento interno.”
- **05:** “Execute **somente a Fase 05**. Crie ferramentas com schemas, validação e erros; autorização antes de ler pedidos; sem SQL livre.”
- **06:** “Execute **somente a Fase 06**. Integre modelo configurável e tool calling com persona, limites e testes offline; demonstre busca de violões até R$ 1.000.”
- **07:** “Execute **somente a Fase 07**. Implemente sessões isoladas, contexto e acesso autorizado de demonstração; teste vazamento e falhas.”
- **08:** “Execute **somente a Fase 08**. Acrescente CLI e endpoints FastAPI reaproveitando o núcleo; teste HTTP, sessão e inputs.”
- **09:** “Execute **somente a Fase 09**. Monte ~40 casos com gabaritos, execute avaliação disponível, reporte métricas observadas e falhas.”
- **10:** “Execute **somente a Fase 10**. Finalize README, 5 conversas e checklist de segurança; **não publique nem faça push sem meu aval**.”

**Prompts de revisão após cada fase:**

> Revise como engenheiro sênior as alterações **desta fase**, comparando com `AGENTS.md` e critérios de aceitação. Examine diff, testes, segurança, regras de negócio e complexidade. Corrija somente falhas comprovadas do escopo e reporte evidências, limites e próximo passo. **Não faça commit sem autorização.**

## 16. Checklist final

- [ ] Repositório público com commits progressivos e sem segredos.
- [ ] README reproduzível e uso de Codex declarado.
- [ ] Dados importados sem mutações nos originais; publicação permitida/fixtures sintéticas.
- [ ] Catálogo, disponibilidade, PIX, promoção e parcelas corretos.
- [ ] Políticas com fontes; pedidos protegidos sem fingir autenticação real.
- [ ] Tools validadas, falhas seguras e sessões isoladas.
- [ ] Testes executados, métricas observadas e limitações honestas.
- [ ] 5 conversas verificadas (1+ caso não trivial).
- [ ] Prazo confirmado no e-mail; não alterar repositório depois da entrega.

**Mensagem ao Codex:** implemente um agente pequeno, auditável, funcional e defendível. Cada decisão deve ter justificativa e evidência de teste.
