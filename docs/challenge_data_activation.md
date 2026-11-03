# Ativação dos dados originais na interface

Configuração local atualizada em 02/11/2026, a pedido do usuário, mantendo
`qwen3.5:9b` via Ollama local (`127.0.0.1:11434`). Nenhuma mudança de código,
regras, autorização, modelo, gabaritos ou dados brutos foi realizada.

| Uso | Fonte ativa |
|---|---|
| Catálogo, estoque, categorias e promoções | `data/emporio.sqlite3`, derivado dos CSVs fornecidos |
| Políticas | `data/raw/políticas_da_loja.pdf`, original v2.1 |
| Pedidos demonstrativos do backend | Banco sintético anterior, preservado |
| Acesso pela interface HTTP | Visitante; pedidos privados continuam bloqueados |

O banco original foi conferido, em leitura apenas, com os seis CSVs: todos os
registros coincidem após as normalizações documentadas. Contagens: 9 categorias,
65 produtos, 50 clientes, 20 pedidos, 22 itens e 25 promoções. Não houve necessidade
de executar nova ingestão. FKs sem violações; `integrity_check=ok`.

Somente `EMPORIO_CHAT_CATALOG_DATABASE` e `EMPORIO_CHAT_POLICY_PDF` foram alterados
no `.env` local ignorado, por escrita atômica e modo 0600. Valores de credenciais
não foram registrados. Os sete arquivos originais (seis CSVs e PDF) permaneceram
com os mesmos hashes antes/depois. Totais históricos e JSON de specs preservados.

A API local foi reiniciada para aplicar os caminhos. **Atualize a página em
http://127.0.0.1:8000 e inicie uma nova conversa**; tokens das sessões anteriores
ao reinício não são válidos. O modelo e as proteções permaneceram iguais.

## Verificações

- 72 testes direcionados passaram em 7,43 s: snapshot original, serviços,
  recuperação documental e contratos HTTP. São testes offline, sem LLM externo.
- Ruff: `All checks passed!`.
- Chamadas reais ao Qwen local confirmaram o produto 127 como Kalani, PIX
  R$ 323,10 com referência ao produto, busca de nylon e citação do manual v2.1.
- Consulta ao pedido 20, em sessão nova, retornou HTTP 403 `forbidden`.
- Na conversa longa anterior, a mesma consulta gerou encaminhamento sem tool
  (HTTP 200), sem dados de pedido; não atendeu à expectativa inicial de HTTP 403.
  Essa limitação de roteamento foi registrada, sem alterar o modelo para ocultá-la.
- Rotas diretas para PDF, SQLite e `.env` retornaram HTTP 404.

Resultados HTTP completos, incluindo trechos do manual, ficam somente em
`data/derived/challenge_activation/`, ignorado pelo Git. A evidência pública
[challenge_data_activation.json](challenge_data_activation.json) contém apenas
metadados, verificações e resultados sanitizados, sem o texto interno do manual.

## Escopo e limites

O arquivo SQLite original também contém clientes e pedidos, mas os serviços de
catálogo só consultam as tabelas necessárias. O serviço de pedidos continua usando
as fixtures sintéticas autorizadas pelo backend; a interface não passou a liberar
os pedidos originais. Conhecer um ID não autentica um cliente. Não foi afrouxada a
verificação `DemoDatabase`, nem criada identidade por informação no chat.

O manual é classificado como interno. Está sendo usado localmente, sem upload,
rota de download ou publicação integral. Não se deve presumir autorização de
envio a provedor externo ou redistribuição dos anexos.

Os benchmarks de modelos e os 40/18 gabaritos continuam usando fontes sintéticas
próprias. Os resultados históricos não foram recalculados nem apresentados como
avaliação completa deste catálogo original. As falhas residuais do agente seguem
documentadas na avaliação da Fase 12C e na comparação de modelos.

Nenhum commit, push, publicação ou download de modelo foi realizado.
