# Revisão sênior — alterações da Fase 10

Escopo delimitado pelo inventário `/tmp/emporio-phase10-before.json`, pois o Git
não tem HEAD/commits. Revisados README, decisões finais, exemplos, scripts de
entrega, auditoria e evidências. Código das fases anteriores não foi alterado.
As reproduções usaram sentinelas e repositórios temporários, nunca originais.

## Falhas comprovadas e correções

| ID | Severidade | Reprodução antes da correção | Correção aplicada |
|---|---|---|---|
| R10-01 | Alta | Saída `01_catalogo.md` ligada por hard link a CSV-sentinela modificava a fonte. Escrita do relatório tinha o mesmo padrão de truncamento | Estágio e substituição da entrada por arquivo; symlinks de saída recusados. Testes verificam fonte intacta no gerador e no relatório |
| R10-02 | Média | Falha na validação da promoção deixava catálogo anterior já sobrescrito; `python -O` desativava asserts e aceitava cinco exemplos inválidos | Todos os cenários são validados antes de gravar; checagens explícitas, ativas em modo otimizado; manifesto por último |
| R10-03 | Média | Erro 128 no `git rev-list` resultava em zero commits e `technical_scan_passed=true` | Códigos de cada comando Git são conferidos; auditoria falha com código 2 e preserva relatório anterior |
| R10-04 | Média | `.env` rastreado apontando para o relatório escapava pela exclusão de autorreferência | Restrições/symlinks são conferidos antes; apenas o caminho exato do relatório é excluído |
| R10-05 | Média | Telefone conhecido seguido por ID `12` não era detectado, pois o regex consumia os dígitos extras | Busca por número conhecido com separadores e limites, sem exportar o valor |
| R10-06 | Baixa | `ssh://git@...` era apontado como credencial | Usuário de transporte SSH é permitido; senha embutida é erro e userinfo HTTP requer revisão |
| R10-07 | Alta | Segredo sintético staged, seguido de limpeza apenas do arquivo local, recebia resultado limpo | Blobs e tipos do índice são conferidos com `git cat-file`; inclusive o relatório staged é examinado |

Os sete comportamentos foram reproduzidos antes das respectivas correções; a aceitação
inválida com `-O` e a corrupção por hard link no relatório foram confirmadas na
cópia original cujo hash coincidia com o inventário anterior à revisão. Nenhum
segredo real foi necessário para as reproduções.

## Verificações reais após as correções

| Verificação | Resultado |
|---|---|
| Testes direcionados dos scripts de entrega | **37 passed in 2.01s** |
| Regressão completa do projeto | **444 passed in 17.74s** |
| Regressão na cópia pública isolada | **409 passed, 35 skipped in 16.13s** |
| Ruff | **All checks passed!**; **104 files already formatted** |
| Instalação no venv novo e reinstalação após o último ajuste | Código 0; dependências iguais ao lock |
| `pip check` | **No broken requirements found.** |
| Cinco exemplos válidos gerados com `python -O` | Cinco hashes conferidos; nenhum provedor real |
| API com TestClient no ambiente isolado | health 200, sessions 201, chat 200, pedido visitante 403 |
| Scanner no projeto atual | Zero achados; zero arquivos no índice; publicação não autorizada |

Detalhes e comandos: [phase10_review_validation.json](phase10_review_validation.json).
O venv foi criado novo nesta revisão, sem pacotes do sistema, pytest pré-instalado,
`.env` privado, anexos ou banco. Após o último ajuste de índice, a cópia pública
foi atualizada e a instalação editável repetida antes das verificações finais.
Os 95 arquivos executáveis/fixtures/configuração conferidos coincidem com o
workspace validado. O `.env` usado veio somente do exemplo público. Logs brutos
ficaram em `/tmp`; nenhum token de sessão foi exportado.

Os testes novos acrescentados na revisão são 27; os dez testes de auditoria da
Fase 10 anterior foram preservados. Os casos Git criam índices/repositórios
temporários, sem commit ou conexão de rede; não alteram o Git do projeto.

Comandos efetivamente executados:

```bash
python -m pytest tests/unit/test_release_audit.py tests/integration/test_release_examples.py -q
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
python scripts/audit_release.py
# Em cópia isolada, após instalar o lock:
python -O scripts/generate_examples.py --output <diretorio-temporario>
```

O placeholder representa a saída temporária usada, não um argumento literal.
Testes async/threads rodaram fora do sandbox pelo problema já documentado nas
fases anteriores. O único tráfego externo necessário foi instalação de pacotes;
nenhum LLM real foi chamado. A API foi verificada em processo por TestClient.

## Avaliação técnica do escopo

- **Correção e erros:** sete falhas demonstradas corrigidas. Comandos Git
  incompletos impedem aprovação; falha de validação não altera evidência anterior.
- **Arquitetura:** mudanças limitadas a utilitários de entrega, testes e documentos.
  Sem nova dependência, framework, UI ou alteração das camadas do agente.
- **Segurança:** fontes ligadas não são truncadas; índice e worktree são verificados
  separadamente; restrições não podem ser contornadas por alias do relatório.
  `self_report_excluded` refere-se ao relatório no worktree; seu blob staged
  continua sendo inspecionado, conforme o teste específico.
- **Regras da loja:** preservados cálculos Decimal, não acumulação PIX/promoção,
  parcelas, autorização demonstrativa, histórico e ausência de rastreamento.
  Exemplos continuam sintéticos e claramente roteirizados.
- **Reprodução e evidências:** README, manifesto e links conferidos; evidência
  inicial separada da verificação pós-revisão. Não foram fabricados resultados
  reais de LLM nem alterados os resultados 25/40 da avaliação.
- **Complexidade:** helpers locais para validação, estágio, leitura do índice e
  códigos Git. Não houve refatoração do produto para resolver problemas de scripts.

Arquivos corrigidos: `scripts/{audit_release,generate_examples}.py`,
`tests/unit/test_release_audit.py`, `README.md`, anotações de auditoria/decisões e
snapshot de verificação inicial. Novos: `tests/integration/test_release_examples.py`,
este parecer e seu JSON de reprodução. Os cinco Markdown e seu manifesto foram
conferidos sem sobrescrever a evidência anterior.

## Limites mantidos

A troca é atômica por arquivo, não transação de seis arquivos diante de falha de
disco/interrupção durante os renames. Usar diretório novo para reprodução e
conferir manifesto; o relatório não promete atomicidade de diretório. Heurísticas
de PII/segredos seguem incompletas. Não houve mudança no agente, regras de negócio,
retrieval, modelo, API, dados originais ou resultados da avaliação 25/40.

As pendências de modelo real, histórico Git, permissão de anexos e prazo já
documentadas não são defeitos novos desta revisão e não foram ocultadas/corrigidas
por mudanças fora do escopo. A varredura segue heurística, sem auditoria de todo
o histórico; zero achados não é consentimento de publicação nem garantia absoluta.

## Recomendação

**Aprovação técnica local da Fase 10 após as correções. Não avançar para
publicação/envio como entrega completa** enquanto não forem resolvidas a validação
de modelo real, a ausência de commits/remoto,
o prazo e as permissões/revisão do candidato já documentados na auditoria final.
O resultado 25/40 do roteiro permanece visível; não foi convertido em limiar
artificial de aprovação de um LLM que ainda não foi medido.
Não há próxima fase a implementar automaticamente. Nenhum commit, push,
publicação ou mudança de histórico do projeto foi realizado. Esta é revisão
técnica pelo Codex, sem alegar aceite humano independente ou do avaliador.
