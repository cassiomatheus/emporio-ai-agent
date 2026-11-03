# Decisões — Fases 01–06

## DEC-01 — Snapshot, não dados em tempo real

Os seis CSVs formam uma única entrada. O relatório contém SHA-256 dos bytes lidos
e estatísticas por tabela. Não se presume que estoque, promoções ou pedidos
representem o estado atual externo. As contagens de aceite são verificadas no
snapshot original; o carregador também aceita snapshots sintéticos menores.

## DEC-02 — Não há recebimento real

`order_date` e `estimated_delivery` são preservados como datas ISO. Nenhum
`delivered_at` é criado ou inferido. Campos opcionais vazios viram `NULL`.

## DEC-05 — Promoções sem datas

Preservar `is_active` como inteiro 0/1. Percentuais são inteiros entre 0 e 100,
conforme o schema observado; percentuais fracionários são recusados até uma
revisão explícita do contrato. Não criar início ou fim de promoção, nem aplicar
desconto ou inferir elegibilidade comercial durante a ingestão.

## DEC-06 — Dados de clientes não autenticam

IDs, nomes e contatos são armazenados apenas no banco local ignorado pelo Git.
Importar um cliente não cria autenticação. A autorização de consultas pertence
às fases de serviços/sessões; nenhuma consulta pública de pedidos foi criada.

## DEC-07 — Preservar totais históricos

`orders.total_brl` é convertido exatamente em `orders.total_cents`, sem cálculo
a partir dos itens. Comparações com o catálogo são apenas diagnósticos derivados,
separados em `observations.historical_total_differences` no relatório. Diferenças
de R$ 48 e R$ 88 dos pedidos 3 e 20 não são erros bloqueantes nem são corrigidas.
Não é criado `unit_price_at_purchase`, pois esse dado não existe na fonte.

## DEC-09 — Originais locais e relatório sanitizado

Os originais externos e as cópias em `data/raw/` são preservados byte a byte.
CSV/PDF bruto e SQLite não são versionados. A permissão de redistribuir os anexos
continua pendente. O manual interno não é publicado. Na Fase 03, os trechos de
pagamento foram consultados localmente para fundamentar os serviços, sem criar
índice ou mecanismo de recuperação documental.
O relatório público contém schema, contagens, hashes e diferenças monetárias
diagnósticas; não contém nomes, telefones, e-mails, notas ou linhas de clientes.
Erros de validação incluem apenas tabela, campo raiz, posição lógica do registro
CSV (incluindo o cabeçalho como 1) e código, sem valores inválidos ou traceback.

## DEC-10 — Normalização conservadora e mapeamento de arquivos

Para cada uma das seis tabelas, aceitar o nome canônico ou o prefixo fornecido
`desafio_tecnico_ai_eng - `. Recusar ausência, ambiguidade, colunas extras/ausentes,
cabeçalho duplicado e registros com largura incompatível. A ordem das colunas
pode variar. UTF-8 e UTF-8 com BOM são aceitos. Outros CSVs são ignorados.

Campos vazios ou somente com espaços viram `None`; apenas os três campos
opcionais de pedidos aceitam esse valor. Campos obrigatórios ausentes bloqueiam
o snapshot. Textos preenchidos, inclusive telefone com zeros à esquerda, são
preservados; não se inventam valores. Datas são validadas e serializadas em ISO.
`specs` deve ser um objeto JSON; recusar JSON inválido, não finito ou com chaves
repetidas e serializar com chaves ordenadas, preservando acentos e tipos JSON.

## DEC-11 — Dinheiro exato e schema relacional

`products.price_brl` → `products.price_cents` e
`orders.total_brl` → `orders.total_cents`. O contrato usa `Decimal`, até duas
casas significativas e limite compatível com INTEGER de 64 bits do SQLite.
Rejeitar valores negativos, não finitos ou frações de centavo; não arredondar
silenciosamente. No banco não há `REAL` para dinheiro. Os nomes deixam explícita
a mudança de unidade; dividir por 100 com `Decimal` recupera o valor monetário.

| Tabela | Chave | Restrições principais |
| --- | --- | --- |
| categories | category_id | ID positivo e textos obrigatórios |
| products | product_id | FK categories; centavos/estoque ≥ 0; status enumerado; specs objeto JSON |
| customers | customer_id | Textos obrigatórios; contatos preservados como texto |
| orders | order_id | FK customers; total em centavos ≥ 0; status enumerado; datas ISO |
| order_items | (order_id, product_id) | FKs orders/products; quantidade > 0 |
| promotions | promotion_id | FK products; percentual 0–100 inteiro; flag 0/1 |

As seis tabelas são `STRICT`. A chave composta de itens é aplicada após validar
unicidade no snapshot. Há índices nas FKs não cobertas pela chave composta.
São cinco relacionamentos e nenhum possui exclusão em cascata. A conexão habilita
`PRAGMA foreign_keys=ON`. Status e estoque são preservados separadamente; não há
coluna calculada de disponibilidade nem filtro comercial nesta fase.

## DEC-12 — Atomicidade e idempotência por substituição integral

Validar todo o snapshot em memória antes de abrir o banco para escrita. Executar
`BEGIN IMMEDIATE`, DDL, exclusão em ordem inversa de dependência, inserção em
ordem de dependência e verificações dentro da mesma transação. Usar parâmetros
para valores; identificadores SQL vêm apenas dos contratos estáticos do código.
Não usar `executescript`, que poderia quebrar a transação por commit implícito.

Antes de confirmar, verificar contagens, `foreign_key_check` e `integrity_check`.
Qualquer exceção provoca rollback, inclusive após exclusões e inserções parciais.
Não há tabelas de auditoria com timestamps variáveis: a mesma entrada produz o
mesmo conteúdo lógico; entradas removidas também desaparecem do snapshot derivado.
Essa estratégia é adequada para 191 registros, sem histórico incremental.

O banco recebe `application_id=0x454D504F` e `user_version=1`. Bancos existentes
de outros aplicativos ou versões desconhecidas são recusados. O destino precisa
ter extensão `.sqlite3`, `.sqlite` ou `.db` e não pode estar em `data/raw/`.
Relatórios escritos pelos scripts usam `.json` e também não podem estar na fonte.
Uma falha na primeira importação pode deixar um arquivo SQLite vazio, sem dados
ou schema parcialmente confirmados; um snapshot anterior permanece intacto.

As decisões de contatos, frete e troca/garantia foram documentadas na Fase 04,
abaixo. A recuperação não implementa decisão de elegibilidade ou cálculo de frete.

## DEC-13 — Serviços separados e leitura consistente

Contratos `Protocol` desacoplam serviços das implementações SQLite. Repositórios
retornam registros sem cálculos de preço, disponibilidade ou autenticação.
Os serviços recebem Pydantic nas fronteiras e retornam resultados tipados.
Os repositórios abrem conexões `mode=ro`, `query_only=ON`, com transação de
leitura, de modo que preço/promoção e pedido/itens venham do mesmo snapshot.
Banco ausente não é criado por uma consulta. Falhas técnicas viram
`ServiceUnavailable`, sem preço de fallback ou mensagem contendo SQL/PII.

Para 65 produtos, os filtros são determinísticos em Python sobre uma leitura
limitada ao catálogo; não há ORM nem geração livre de SQL. Nome aceita substring,
categoria aceita nome exato ou ID, texto ignora caixa/acentos e especificações
textuais são comparadas por igualdade normalizada. Não há busca semântica,
sinônimos ou inferência de característica ausente. A faixa usa preço de tabela,
é inclusiva e a ordem é preço/ID. Paginação tem limite máximo 100.

## DEC-14 — Parcelas e ambiguidade do manual

Fonte consultada localmente: manual v2.1, junho/2025, seções 3 e 3.1, página 3.
A tabela geral cita parcela mínima de R$ 100; a seção específica 3.1 detalha
faixas distintas. Aplicar o detalhamento: R$ 80 em 4–6x e R$ 100 em 7–12x.

A exceção de 1–3x abaixo de R$ 50 é ambígua. Interpretação conservadora deste
protótipo: exigir R$ 50 por parcela em 2–3x; tratar 1x como pagamento à vista,
sem limite mínimo de parcela. Essa é uma decisão de implementação, não uma
afirmação de que o texto elimina a ambiguidade. Precisa ser confirmada com a loja
antes de uso real. Não se simula combinação de modalidades de pagamento.

Os pisos são verificados sobre o preço final após um único desconto e sobre a
menor parcela efetiva. Distribuir os centavos excedentes nas primeiras parcelas,
com diferença de no máximo R$ 0,01 entre elas; a soma sempre é o total e os juros
são zero. Não arredondar uma parcela para cima para torná-la artificialmente
elegível. Não oferecer acima de 12x ou uma contagem não elegível.

## DEC-15 — Descontos e disponibilidade

Disponível somente se `active` e estoque > 0. Detalhes de produto indisponível
podem ser consultados, mas seu preço não gera oferta vendável. Na busca, a
inclusão de indisponíveis precisa ser explícita. Os dados continuam snapshots.

Considerar apenas promoções com `is_active=1` para o mesmo produto. Se houver
várias, a decisão deste protótipo é escolher uma única promoção com maior
percentual; em empate, menor ID. Para PIX, comparar essa promoção ao desconto
isolado de 5% sobre a tabela e escolher o maior, sem somar nem aplicar descontos
sucessivos; em empate, manter a promoção. Demais modalidades usam a promoção
isolada, quando houver. Não inferir validade temporal.

Preços são `Decimal` com arredondamento `ROUND_HALF_UP` para centavos após o
desconto. Cálculos monetários usam contexto decimal local de precisão 40.
Os resultados incluem preço original, percentual, preço final, origem do desconto
e ID da promoção quando aplicada. As regras são verificáveis sem LLM.

## DEC-16 — Consulta protegida de pedidos

`OrderAccessContext` só pode ser injetado por um backend que já autorizou o
cliente. O construtor é um mecanismo interno de confiança, não um autenticador;
não aceitar esse contexto do usuário/LLM. A Fase 07 deverá ligá-lo às sessões de
demonstração autorizadas no servidor. Nesta fase, os testes fornecem contextos
controlados, sem alegar login real.

Sem contexto autorizado, recusar antes de chamar o repositório. Com contexto,
buscar por `order_id` **e** `customer_id` no SQL, e conferir o dono novamente no
serviço. Pedido alheio e inexistente têm a mesma resposta de domínio `forbidden`;
não consultar globalmente a existência de um pedido para diferenciar os casos.
A saída omite dados de clientes e notas internas, preserva o total histórico e
mantém rastreio/previsão ausentes como `None`, com `tracking_status=not_provided`.
Não inferir entrega real, preço unitário da compra, nem prazo de devolução.

## DEC-03 — Contatos divergentes no manual

A capa, a tabela de dados da empresa (1.2, página 2) e o canal de atendimento
(7, página 6) não são plenamente consistentes em telefone/e-mail. Preservar a
fonte; não escolher um contato como correto sem confirmação externa da loja.
A capa é preservada no texto por página, mas não entra no ranking de seções.
Consultas de contatos ainda exigem cuidado com essa diferença entre fontes.

## DEC-04 — Frete em exatamente R$ 500

Seção 5.1, página 4: a fonte diferencia valores acima e abaixo do limite, sem
regra literal para a igualdade. A busca pode recuperar a seção relacionada,
mas isso não é evidência de uma tarifa para exatamente R$ 500. O gabarito exige
explicitar a lacuna, sem inferir gratuidade ou taxa. Não há cálculo de frete.

## DEC-08 — Troca por defeito não é garantia legal

Seção 4.2, página 4: procedimento de troca por defeito em 30 dias da compra.
Seção 8.1, página 7: garantia legal em 90 dias do recebimento. Seção 4.1,
página 4: arrependimento online em 7 dias do recebimento. São fragmentos e
gabaritos distintos, com marcos temporais diferentes. Recuperar um procedimento
não autoriza negar outro direito nem aprovar uma devolução sem os dados necessários.
Garantia do fabricante (8.2) é outra fonte, com condições próprias do certificado.

## DEC-17 — Extração por geometria, estilo e seção

Usar PyMuPDF localmente, com texto por página e detecção geométrica de tabelas.
Manter cabeçalhos e células como estruturas; a representação pesquisável repete
os rótulos em cada linha, evitando separar valor de condição. Títulos numéricos
com fonte em negrito e tamanho compatível definem as seções; itens de listas
numeradas não viram novos títulos. Remover cabeçalhos/rodapés apenas do índice,
mantendo o texto original extraído por página em memória.

Seções continuam entre páginas. Cada fragmento contém ID estável, hash SHA-256,
versão detectada (ou None, sem inventar), fonte, caminho da seção, páginas do
fragmento e páginas da seção. Parágrafos são agrupados até cerca de 1.000
caracteres; unidades atômicas e tabelas não são cortadas. O manual observado
tem 8 páginas, 28 seções, 30 fragmentos e 4 tabelas. Não há OCR nem publicação
da extração integral. Mudanças de layout exigem nova verificação.

## DEC-18 — Recuperação lexical e ausência de evidência

Normalizar caixa, acentos, números e um conjunto pequeno de flexões portuguesas.
Usar sobreposição ponderada por frequência inversa; títulos têm peso 2.
Exigir cobertura lexical de 60% ou duas âncoras textuais do título, para não
descartar seções explicitamente nomeadas por causa de verbos ausentes no texto.
Não usar embeddings, LLM, modelo de reranking ou base vetorial externa.

Retornar até top_k (máximo 5), com diversidade por seção, score não probabilístico
e excerto de até 420 caracteres, preservando linhas de tabela/bullets relevantes.
Fragmentos de seções diferentes não são fundidos. Marcar encurtamento quando
o excerto não contém toda a unidade. Sem correspondência suficiente, retornar
`no_evidence` e lista vazia; falha de abertura/extração é erro tipado separado.
O serviço recupera fontes, sem inferir uma resposta ou avaliar direitos.

## DEC-19 — Avaliação observada de recuperação

Gabaritos definidos por leitura do manual: 20 perguntas positivas sobre PIX,
parcelas, devoluções, frete e garantia; 6 negativas sem suporte. Recall@3 é a
média de |seções relevantes recuperadas nos 3 primeiros| / |seções relevantes|.
Perguntas negativas ficam fora desse denominador e têm abstenção medida à parte.
Perguntas com dois alvos exigem ambos, não apenas algum acerto.

A primeira execução obteve 95%: uma pergunta de garantia legal perdeu a seção
correta por cobertura lexical insuficiente. A regra geral de âncoras do título
elevou a medição para 100% nesse mesmo conjunto. Essa foi uma iteração de
desenvolvimento, sem alegar avaliação cega ou generalização. Gabaritos de resposta
são resumos para revisão humana; a métrica automática mede seções, não qualidade
de resposta, acerto jurídico ou cobertura completa de cada condição no excerto.

Texto bruto, linhas de tabela e coleções de páginas/fragmentos internos também
são excluídos da serialização Pydantic padrão, reduzindo exportação acidental.
Somente excertos selecionados são serializados no contrato público da busca.

## DEC-20 — Fronteira de tools independente do provedor

Expor somente seis operações por lista fechada, com contratos Pydantic de entrada
e saída e JSON Schema exportável. Entrada deve ser objeto JSON nativo; recusar
campos extras, coerções de IDs/bools, não finitos e argumentos acima de 8 KiB.
Preços aceitam inteiro ou texto decimal (até duas casas), nunca float de JSON.
Resultados são revalidados e limitados a 64 KiB, sem cortar dados silenciosamente.
Dinheiro sai como string decimal. Não há SQL, caminho, código, eval ou comando
arbitrário em nenhum contrato. Texto que parece SQL continua sendo apenas texto.

Envelope comum: sucesso contém dados e nenhum erro; falha contém erro tipado e
nenhum dado. Mensagens são fixas e os campos inválidos só mostram nomes conhecidos
do schema ou `$`, nunca valores, chaves privadas desconhecidas, exceção ou PII.
Falhas inesperadas e saídas inválidas viram `service_unavailable`; não há preço
de fallback. Busca de catálogo vazia é sucesso com lista vazia; detalhes ausentes
são `not_found`; políticas/dados da loja sem fonte são `no_evidence`.

O registro só despacha chamadas; não contém loop, prompt, SDK, autenticação ou
sessões. Limites de rodadas e timeout de orquestração pertencem à Fase 06.

## DEC-21 — Autorização externa aos argumentos

`get_order_status` recebe somente `order_id`. O contexto de acesso é um argumento
Python separado, injetado por backend de confiança. Não é campo JSON Schema e
não fica armazenado no registro entre chamadas. A tool recusa antes de invocar
o serviço quando falta autorização; o serviço mantém sua própria guarda e a
consulta SQL por dono. Nenhum ID declarado pelo solicitante autentica o cliente.
Contextos usados nos testes são controlados; autenticação real não foi adicionada.

Pedido alheio e inexistente continuam indistinguíveis (`forbidden`). O retorno
omite PII de clientes e notas internas e preserva rastreio/previsão ausentes.

## DEC-22 — Dados públicos da loja com fonte e ambiguidades

Adicionar ao PolicyService seleção explícita das fontes existentes para endereço,
horário e contatos. A tool não lê o PDF por conta própria nem expõe o texto
integral. Dados da tabela 1.2, horários da seção 2, contato da seção 7 e contatos
da capa são retornados com página, seção (None para capa), versão e hash.
Selecionar apenas os campos públicos pedidos, sem CNPJ ou outros campos internos.

Preservar as variantes de telefone/e-mail e alertar sobre divergências, sem eleger
uma como correta. Horários incluem alertas de variação e de que não se está
checando "aberta agora". O mapeamento é específico deste manual; mudança de
estrutura exige revisão. Sem fonte válida, não usar constantes de fallback.

## DEC-23 — Identificação de produto e limites de resposta

Detalhes aceitam exatamente um entre ID e nome completo. A normalização textual
é a mesma do serviço de catálogo; não usar substring para escolher um produto
nessa operação. Mais de um nome normalizado igual retorna `ambiguous`, sem
escolher por preço, ordem ou disponibilidade. O método fica no ProductService.

As tools delegam filtros e cálculos. O catálogo é limitado a 20 itens por página,
características são até 10 escalares com chaves/strings limitadas; políticas são
até 5 excertos de 420 caracteres. Dados da loja são até 8 entradas de 300 caracteres.
Identificadores e paginação dos resultados precisam corresponder à solicitação.
Nada disso representa execução de ação comercial ou integração com LLM.

## DEC-24 — SDK e modelo configuráveis, sem escolha paga implícita

Usar SDK oficial OpenAI, com adaptador Responses API atrás do protocolo
LLMProvider. Tools/serviços não importam o SDK. Modelo, credencial e provedor
são obrigatoriamente explícitos; configuração parcial não constrói cliente nem
chama API. O endpoint compatível precisa implementar Responses API. Não prometer
suporte a servidores que só ofereçam Chat Completions. Sem credenciais neste
workspace, a chamada real foi marcada como não executada.

O cliente usa store=False, retries automáticos desativados e timeout explícito.
Itens de saída, incluindo reasoning criptografado quando retornado, são mantidos
somente durante o loop e reenviados ao continuar, com call_id correspondente.
Não há estado remoto referenciado por previous_response_id. Isso não equivale
a garantir uma política de retenção externa do provedor.

As tools têm mapas dinâmicos de specs; usar strict=False no schema enviado ao
provedor e manter validação estrita autoritativa da Fase 05. JSON inválido,
chaves duplicadas, números não finitos, nome desconhecido ou campos extras
resultam em falha tipada, sem executar SQL ou liberar pedido.

## DEC-25 — LLM planeja; fatos são renderizados da evidência

O modelo escolhe tools e, ao terminar, devolve AnswerPlan em JSON, referenciando
IDs de chamadas bem-sucedidas desta execução. Não há campo de texto livre para
preço, estoque ou decisão de política. O backend valida e renderiza os fatos
diretamente dos dados tipados das tools. Referência inexistente ou falha não
gera resposta factual. Texto livre, JSON com fatos extras ou plano inválido
produz abstenção. Não confiar só em instruções de prompt para impedir alucinação.

Essa escolha restringe a flexibilidade da conversa: saudação, esclarecimento,
fora de escopo e encaminhamento também usam textos controlados. A persona é
acolhedora e profissional, sem prometer ações externas. Políticas são excertos
com fonte e não decisões de elegibilidade. Esta é uma limitação deliberada do
MVP auditável, não prova de compreensão semântica geral.

## DEC-26 — Loop pequeno, limites e falhas

Execução de uma mensagem: no máximo 4 requisições de LLM por padrão, 12 chamadas
de tools no total e 4 no mesmo retorno. Tools da mesma resposta são executadas
sequencialmente e cada saída é correlacionada ao call_id. IDs repetidos são
recusados. Erros de tool podem ser informados ao modelo para corrigir argumentos
na próxima rodada, dentro do limite. Modelos não escolhem autorização.

Timeouts padrão: total 30 s, requisição 20 s e tool 5 s; entrada de usuário até
2.000 caracteres e histórico transitório até 128 KiB serializados. SDK limita
saída a 1.200 tokens por padrão. Os valores configuráveis são validados. Ao
esgotar tempo/rodadas/chamadas, retornar falha segura, sem preços de fallback.

As tools síncronas rodam em threads para não bloquear o loop. Timeout cancela a
espera e descarta o resultado tardio; não mata uma thread Python já executando.
As operações são somente leitura e SQLite já tem timeout de conexão. O fechamento
do executor pode esperar essa thread terminar; não se alega deadline rígido de
processo nem cancelamento físico de qualquer dependência arbitrária.

Não adicionar LangGraph ou multiagentes: o fluxo tem seis tools e poucas rodadas,
com contrato e estado local suficientes. Não há memória persistente ou sessão;
a Fase 07 continua pendente. Rastros contêm IDs, nomes e status, sem prompts,
argumentos, respostas brutas ou credenciais.

## DEC-27 — Demonstração e testes honestamente rotulados

O diagnóstico fixo usa LLM roteirizado por padrão e tools/serviços reais. Esse
resultado não comprova seleção autônoma de ferramenta por um modelo real.
Testes do SDK usam transporte HTTP local simulado; não são chamadas a provedor.
O modo --real só executa quando provedor, modelo, credencial e URL quando
necessária estão configurados. Não incluir chave ou endpoint nos relatórios.

Tokens são somados somente quando o provedor informa uso; na simulação, uso é
None, não uma estimativa de tokens/custo real. Custo e qualidade de modelo real
permanecem não medidos. Não há escolha definitiva de modelo ou benchmark real.

## DEC-28 — Sessões efêmeras e capacidades do backend

ConversationService guarda sessões em memória, com handle de cliente conferido
pela identidade do objeto registrado, ID de sessão aleatório e concessão imutável.
O modelo/usuário não fornece identidade autorizante. Não é autenticação real;
somente demonstra a separação entre cliente, sessão e autorização no backend.
Nenhuma rota HTTP foi adicionada. Uma instância pertence a um event loop/processo.

Há limites de pares/caracteres, TTL monotônico, cotas de clientes/sessões, lock por
sessão e espera limitada. Fechar/revogar/expirar limpa o estado; verificar novamente
após await impede entregar/guardar resposta de uma sessão que perdeu acesso.
A limpeza por TTL ocorre nas operações, sem tarefa de background ou persistência.
Clientes precisam ser revogados para liberar sua quota. Ver docs/sessions.md.

## DEC-29 — Pedidos exclusivamente sintéticos na demonstração

A fábrica for_demo mantém catálogo/preços no snapshot escolhido e monta OrderService
com outra base, validada contra todas as fixtures redistribuíveis de data/samples.
O registro administrativo só concede IDs presentes nessa base (1/2), após conferir
seus dados, não simplesmente por aceitar um ID declarado. A verificação é repetida
antes/depois de cada chat e recusa base divergente sem mostrar linhas pessoais.
Não converter automaticamente o banco original nem sobrescrevê-lo com exemplos.

Essa validação evita uso acidental do snapshot original com concessão demonstrativa;
não protege contra backend/administrador malicioso ou troca/restauração concorrente
do arquivo local. Os snapshots e o método administrativo pertencem ao backend
confiável. Futura API precisará de uma fronteira de identidade própria.

## DEC-30 — Referência não é cache de preço

Guardar no máximo 20 IDs obtidos das tools de produto bem-sucedidas escolhidas na
resposta final. Um único ID permite referência; vários ou nenhum exigem esclarecer.
Busca vazia limpa a referência anterior. Seleção explícita nova tem precedência.
Padrões conservadores reconhecem seguimentos em português; não são um resolvedor
semântico geral. A resolução fornece apenas ID numérico em contexto confiável e
recusa chamadas de produto que tentem consultar outro ID naquele seguimento.

Histórico é contexto não confiável. O ledger de evidências continua local a cada
execução: preço, estoque e parcelas precisam de consulta nova, inclusive depois
de falha. IDs de pedidos e mensagens declarativas não criam referência de produto.
O plano receipt_date oferece pergunta controlada sobre recebimento real, sem
inferir essa data ou decidir elegibilidade de devolução.

## DEC-31 — Logs por lista permitida e injection como defesa em camadas

AuditEvent admite somente eventos, status, tools e erros conhecidos. ID de sessão
vira HMAC com sal efêmero; não registrar prompts, argumentos, resultados, call_ids
controlados pelo modelo, cliente/pedido, contato, segredo ou exceção. Logger não
instala handlers globais; a aplicação habilita INFO. Falhas de handler são descartadas.
E-mails/números/credenciais óbvios são redigidos antes do LLM/histórico; nomes e
outros dados livres podem escapar, portanto não alegar anonimização completa.

Padrões auxiliares bloqueiam instruções reconhecidas no usuário e resultados de
tools antes do próximo envio ao LLM. Prompts bloqueados não entram no histórico.
SQL arbitrário e autorização por LLM continuam impossíveis pelas fronteiras dos
contratos existentes, independentemente desses padrões. Respostas factuais exigem
evidências tipadas da execução atual. Falsos positivos/negativos e relevância das
consultas continuam riscos; não afirmar resistência geral a injection com mocks.

Todos os testes da Fase 07 são offline, com provedor roteirizado e serviços reais
sintéticos. Não houve medição de qualidade, custo ou ataque com modelo real.

## DEC-32 — CLI e HTTP usam o mesmo runtime

build_runtime monta adaptador, serviços e ConversationService já implementados;
interfaces não replicam filtros/cálculos/autorização. CLI local e FastAPI usam
esse runtime, com limites de Settings. Lifespan fecha o SDK e revoga os visitantes.
A entrada mínima da Fase 01 continua preservada. FastAPI/Uvicorn são dependências
de execução; HTTPX é de desenvolvimento para TestClient. O lock foi atualizado.

## DEC-33 — HTTP sem identidade real só cria visitante

POST /sessions recebe objeto vazio. ID de cliente, demo_order e contexto livre
são rejeitados. Todas as sessões HTTP são visitantes sem concessão de pedido;
as tools/OrderService continuam recusando leituras. Não expor pedidos originais
enquanto autenticação real estiver fora de escopo. Só CLI offline permite uma
concessão administrativa fixa para cliente sintético 1, rotulada demonstração.

O token de 32 bytes aleatórios protege a posse da conversa, não prova identidade
de cliente. Seu hash fica no servidor; ID isolado/token cruzado não libera sessão.
Recebê-lo uma vez no corpo 201 e enviá-lo no cabeçalho Bearer; evitar query string,
logs e cache. Expiração revoga handles; falha de criação desfaz cliente temporário.
Um worker/event loop e escopo local são limites explícitos, sem infraestrutura
de autenticação/distribuição adicionada nesta fase.

## DEC-34 — Falhas HTTP tipadas e exemplos observados

Schemas Pydantic proíbem campos extras; limite de 2.000 caracteres e 16 KiB no
corpo, inclusive streaming sem Content-Length. Erros retornam vocabulário fixo,
sem input/traceback/caminho. Ausência de Bearer é 401, sessão/pedido negado é 403,
validação 422, quota 429, falha de provedor 502, indisponibilidade/limite 503 e
timeout 504. Abstenções controladas podem retornar 200 com status explícito.
GET /health não chama provedor nem mostra configuração; distingue processo ativo
de montagem disponível por chat_ready. No-store em todas as respostas.

OfflineDemoProvider é um roteiro restrito, sem LLM/rede e só com base sintética.
Ativação explícita, sem fallback silencioso quando o provedor real falha. Exemplos
TestClient em docs/http_examples.json têm execution=offline_scripted e tokens
substituídos. Não são conversas autônomas reais nem avaliação da Fase 09.

## DEC-35 — Avaliar o roteiro existente sem entregar o gabarito ao agente

40 cenários/46 turnos em tests/evaluations/agent_cases.json, com parâmetros,
IDs, valores, seções, códigos e proibições explícitos. Distribuição 8/6/8/6/5/7
validada; nenhum LLM-juiz. O sujeito offline é OfflineDemoProvider da Fase 08,
sem alterações para melhorar sua pontuação. O modo real só constrói cliente com
configuração explícita; aqui registrou not_run, sem API real.

As calls de referência são um controle independente executado após a conversa,
sem alimentar seu contexto/ledger. 39/39 controles não se confundem com 25/40
tarefas concluídas nem com seleção autônoma de um LLM. Relatar também falhas de
argumentos que coincidem com resultado correto na fixture, como filtro de preço
omitido. Os JSONs têm hashes, versão e denominadores, sem respostas/documento
interno ou dados de sessão. Fonte real só no perfil opcional de retrieval.

## DEC-36 — Métricas com cobertura e limites explícitos

Seleção por nomes, argumentos essenciais, sucesso por turno/cenário, grounding
automático de dinheiro/estoque/seções e compliance por regras são dimensões
separadas. Abstenção sem afirmação verificável tem grounding N/A. Erro esperado
tratado corretamente, como forbidden, não é falha por si só. Classificação por
componente é diagnóstico por regra, com possíveis sobreposições e revisão futura.

Recall@3 distingue ponta a ponta (roteiro não chamou busca) de controle direto
das seções. P95 usa nearest-rank sobre tempos medidos por perf_counter; setup,
extração inicial, controles e HTTP ficam fora do tempo por turno. Valores locais
do roteiro não são latência de API/LLM real. Tokens faltantes e custo ficam null,
sem estimar faturamento ou preencher zero artificialmente.

Fixtures temporárias separam catálogo de pedidos sintéticos; manual local não é
exportado. Testes de mutação verificam que o avaliador rejeita preço, estoque,
fonte e acesso adulterados. Pytest aprovado verifica detecção/implementação;
não converte as falhas observadas do sujeito em sucesso de tarefa. Nesta fase,
não corrigir o provedor ou alterar regras para elevar a nota do próprio conjunto.

## DEC-37 — Exemplos finais executados com simulação explícita

Cinco Markdown gerados por scripts/generate_examples.py a partir de respostas
capturadas do backend, SQLite e PDF sintéticos. ExampleProvider predetermina as
chamadas e os planos finais; não é LLM nem o provedor da CLI/API. O exemplo de
promoção combina tools, referência, desconto não cumulativo e parcelas; devolução
recupera fontes e pergunta recebimento real. Manifesto inclui hashes e contagens.
Não usar essas demonstrações curadas para alterar a nota 25/40 do roteiro existente.

## DEC-38 — Preparação pública sem conceder permissão de publicação

Auditar candidatos Git e exclusões, padrões de segredos/tokens e correspondências
com identificadores de clientes originais sem exportar os valores. Só fixtures
sintéticas e resultados sanitizados são candidatos; manual/CSVs originais, bancos,
credenciais e logs ficam locais. Ausência de achado heurístico não é garantia
absoluta nem autorização do usuário/titular. Redistribuição dos anexos não foi
documentada; não criar licença permissiva ou publicar os materiais por suposição.

## DEC-39 — Modelo e estado externo sem afirmações não verificadas

Documentar adaptador OpenAI Responses/SDK e configuração, mas manter modelo
real não escolhido/não validado enquanto disponibilidade/orçamento/credencial
não forem fornecidos. Mock não substitui o entregável de LLM real. Conferir
reprodução numa cópia limpa dos candidatos públicos, com novo venv e sem anexos
ou ambiente secreto. Não criar histórico retroativo: Git ainda não tem commits,
remoto ou link público; prazo do e-mail não foi informado. Auditoria técnica
local é distinta de aprovação de entrega. Commit/push/publicação/envio continuam
dependendo de autorização explícita, sem ação automática nesta fase.

## DEC-40 — Integridade das evidências e do estado Git na revisão da Fase 10

As falhas reproduzidas nos utilitários de entrega foram corrigidas sem alterar
o agente: validar todos os cenários antes de escrever, usar checagens explícitas
que funcionam em -O, recusar symlinks e substituir cada arquivo sem truncar um
inode compartilhado por hard link. O conjunto de arquivos não é uma transação
de diretório contra falha de disco; preferir saída nova e conferir o manifesto.

Auditar conteúdo do índice além do worktree: um arquivo local limpo pode ter
segredo staged. Ler blobs por OID sem filtros, sinalizar tipos/conflitos de índice
e interromper em falha de Git. A exclusão do próprio relatório não exclui aliases
restritos. SSH não implica segredo; senha é sinalizada e userinfo HTTP requer
revisão. Snapshots iniciais e verificações após correções são separados para não
apresentar evidência antiga como validação do código novo.

## DEC-41 — Pedido semântico de catálogo antes dos filtros técnicos

O LLM seleciona a ferramenta existente e extrai categoria, subtipo, marca/modelo,
características e orçamento em `CatalogSearchRequest`. `CatalogQueryMapper` valida
as entidades contra o vocabulário observado e produz `SearchProductsInput`.
Cálculo, disponibilidade, consultas e autorização permanecem nos serviços Python.
Não há nova tool fictícia nem etapa adicional obrigatória de inferência.

Os contratos do agente e os contratos técnicos são documentados separadamente.
Aliases e recuperação de slots usam evidência da fonte, sem IDs de casos ou
respostas codificadas. Critérios desconhecidos ou contraditórios exigem
esclarecimento, sem consulta ampla. A paginação usa os filtros já normalizados.
Metadados de interpretação são privados, fora do HTTP e dos logs.

Alternativa adiada: outro LLM ou etapa geral de classificação para todas as
mensagens. A implementação começa pelo catálogo e reaproveita o loop existente.
Validação real, comparação com a linha de base e limites:
[Interpretação do catálogo](catalog_interpretation.md).
