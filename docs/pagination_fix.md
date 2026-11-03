# Correção da continuação do catálogo

Validação executada em 02/11/2026. Escopo: falha relatada ao continuar uma lista
de violões. Não houve troca de modelo, alteração dos dados brutos, gabaritos,
serviços de preços/autorização, contratos HTTP ou frontend.

## Diagnóstico e correções

**Severidade média — continuação dependente de inferência.** O catálogo do desafio
contém 35 violões, dos quais 33 têm status `active` e estoque positivo. A ferramenta
retornava corretamente a primeira página de 10 itens, mas a sessão armazenava apenas
IDs de referência. Filtros e posição da busca precisavam ser reconstruídos pelo LLM
ao receber “continue”. Dez novos testes de integração falharam no código anterior.

A repetição real anterior à alteração conseguiu continuar, em 14.008,91 ms,
com duas chamadas ao adaptador. Portanto, não reproduziu a mensagem de falha
específica do usuário; sem o trace daquele turno, sua causa imediata permanece
indeterminada. A ausência de cursor no backend foi comprovada por inspeção e
pelos testes, independentemente dessa variabilidade do modelo.

**Severidade baixa — indicação incorreta de páginas restantes.** O renderer comparava
o total apenas com o tamanho da página, ignorando o offset. Agora compara
`offset + itens retornados` com o total, mostra a faixa e identifica a última página.

O backend passa a guardar, por sessão, somente os parâmetros validados de
`search_products` e a posição. Pedidos inequívocos como “continuar”, “pode
continuar?” e “próxima página” executam essa mesma ferramenta com o próximo offset.
Essa execução usa os limites, timeout, validação do retorno e detecção de conteúdo
suspeito já existentes. O renderer recebe exclusivamente evidências novas.
Não há chamada ao LLM nesse caminho, nem preço/estoque reutilizado do histórico.

O cursor só avança depois da resposta fundamentada. Falha ou conteúdo suspeito
na ferramenta preserva a posição para nova tentativa, sem divulgar fatos parciais.
Outra sessão não recebe o cursor. Nova busca o substitui; mudança de assunto,
histórico removido, encerramento ou expiração o descartam. Múltiplas buscas numa
resposta exigem desambiguação. O cursor não integra a resposta HTTP nem sua
serialização pública; conhecer um ID continua sem conceder acesso a pedidos.

## Evidência real

Modelo mantido: `qwen3.5:9b`, temperatura 0, thinking `none`, finalização
estruturada ativa na busca inicial. Servidor Ollama local já configurado, sem
download ou envio a provedor externo. Catálogo original do desafio; acesso a
pedidos permanece restrito aos mecanismos anteriores.

| Mensagem | Itens | Latência backend | Chamadas ao adaptador LLM |
|---|---:|---:|---:|
| Quais são os violões disponíveis? | 1–10 de 33 | 37.853,40 ms | 2 |
| Continue | 11–20 de 33 | 4,88 ms | 0 |
| Pode continuar? | 21–30 de 33 | 5,79 ms | 0 |
| Próxima página | 31–33 de 33 | 4,63 ms | 0 |
| continuar | Nenhum restante | 3,86 ms | 0 |

Os 33 IDs entregues coincidiram, na ordem de preço/ID, com a consulta SQLite
de referência; não houve duplicação nem divulgação dos dois modelos indisponíveis.
A busca inicial informou 7.679 tokens agregados entre suas chamadas. Continuação
não solicita inferência; `usage` permanece ausente, sem inventar contagem do provedor.

Depois de reiniciar o FastAPI local, o mesmo fluxo passou por `POST /sessions` e
`POST /chat`, com HTTP 201/200. Tempos das cinco mensagens via HTTP:
12.207,63 / 6,77 / 6,55 / 5,43 / 4,80 ms. Uma sessão independente solicitou nova
busca, sem ferramentas. Tokens de sessão e credenciais não foram registrados.
Não foi feita inspeção visual automatizada do navegador nesta correção.

Essas são execuções pontuais, sem controle de cache/aquecimento; não constituem
benchmark estatístico de velocidade. Os turnos determinísticos do backend não
foram contabilizados como inferência real do modelo. Evidência sanitizada:
[pagination_evidence.json](pagination_evidence.json). Traces locais completos,
somente de catálogo, ficam em `data/derived/pagination_fix/`, ignorado pelo Git.

## Arquivos e verificações

- `app/agent/models.py`: cursor privado com contrato validado.
- `app/agent/memory.py` e `sessions.py`: estado e descarte por sessão.
- `app/agent/pagination.py`: reconhecimento limitado de continuação inequívoca.
- `app/agent/orchestrator.py`: continuação pela mesma execução restrita de tools.
- `app/agent/rendering.py`: faixa, total, instrução e fim dos resultados.
- `tests/integration/test_pagination.py` e `tests/unit/test_pagination.py`: 24 casos
  novos com dados sintéticos, ferramentas/SQLite reais e provedor roteirizado ou
  mocks. Estes testes não são inferência real.
- `README.md`: instruções de uso da paginação.

Comandos executados a partir da raiz do projeto:

```bash
.venv/bin/python -m pytest tests/integration/test_pagination.py -q --tb=short
# Antes da correção: 10 failed in 1.30s.

.venv/bin/python -m pytest tests/integration/test_pagination.py tests/unit/test_agent.py tests/integration/test_sessions.py tests/integration/test_api.py -q --tb=short
# Após a correção: 97 passed in 3.02s.

.venv/bin/python -m pytest -q --tb=short
# 519 passed in 18.13s; nenhum teste ignorado.

.venv/bin/ruff check .
# All checks passed!

.venv/bin/python -m compileall -q app
# Exit 0.

git status --short
git diff --stat
git diff --check
# Projeto continua sem arquivos rastreados/commits; diff vazio não comprova ausência
# de alterações. As cinco versões anteriores dos arquivos modificados foram
# preservadas localmente em data/derived/pagination_fix/before_source/.

.venv/bin/python -m uvicorn app.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
# Servidor local reiniciado com sucesso para carregar a correção.
```

Os testes assíncronos e chamadas a localhost foram executados fora do isolamento
restritivo, que impedia concluir asyncio/acessar sockets. Não houve commit, push,
publicação ou mudança no `.env`. Os gabaritos de 40 e 18 casos foram preservados;
não foram reexecutados integralmente com o Qwen para esta correção delimitada.

## Uso e limites

Atualize a interface em `http://127.0.0.1:8000`, inicie uma conversa e pergunte
“Quais são os violões disponíveis?”. Envie “continuar” três vezes para ver os
demais; uma quarta continuação informa que os resultados terminaram. O reinício
invalida as sessões anteriores.

Não foi adicionado botão nem alterado o limite de até 20 itens por chamada. A
busca inicial e pedidos que mudem filtros continuam dependendo do modelo.
Perguntas ambíguas ou sobre outro assunto não são interpretadas como continuação.
A paginação por offset pressupõe o snapshot estável: mudanças simultâneas de
preço/estoque podem mudar a ordenação entre páginas. Os limites atuais (offset
máximo 10.000 e memória/TTL de sessão) permanecem. Parecer: **correção aprovada
para o protótipo local**, com essas limitações e sem homologação comercial.
