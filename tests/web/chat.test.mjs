// Testes do cliente e do controlador com HTTP/DOM simulados, sem dependências.
// Execução opcional com Node moderno: node tests/web/chat.test.mjs
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const source = await readFile(new URL('../../app/web/chat.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../../app/web/index.html', import.meta.url), 'utf8');
const temporary = await mkdtemp(join(tmpdir(), 'emporio-ui-test-'));
await writeFile(join(temporary, 'chat.mjs'), source);
const { ChatClient, ApiError, formatDuration, renderReply, boot } = await import(join(temporary, 'chat.mjs'));
await rm(temporary, { recursive: true });
const passed = [];
const test = async (name, run) => { await run(); passed.push(name); };
const json = (body, ok = true) => ({ ok, json: async () => body });
const identity = (number) => ({
  session_id: String.fromCharCode(65 + number).repeat(43),
  session_token: String.fromCharCode(97 + number).repeat(43),
});
const reply = (text = 'Resposta sintética') => ({
  status: 'answered', text, execution_mode: 'offline_scripted', rounds: 2,
  tools: [{ name: 'get_product_details', status: 'ok', error_code: null }],
});

await test('reusa sessão e envia token somente no cabeçalho', async () => {
  const records = [];
  const client = new ChatClient(async (path, options) => {
    records.push({ path, options });
    return json(path === '/sessions' ? identity(0) : reply());
  });
  await client.send('  Primeiro instrumento  ');
  await client.send('E no PIX?');
  assert.deepEqual(records.map(r => r.path), ['/sessions', '/chat', '/chat']);
  for (const record of records.slice(1)) {
    assert.equal(record.options.headers.Authorization, 'Bearer ' + identity(0).session_token);
    assert.equal(record.options.credentials, 'omit');
    assert.equal(record.options.cache, 'no-store');
    assert.ok(!record.options.body.includes(identity(0).session_token));
    assert.equal(JSON.parse(record.options.body).session_id, identity(0).session_id);
  }
  assert.equal(JSON.parse(records[1].options.body).message, 'Primeiro instrumento');
  assert.equal(JSON.stringify(client), '{}');
});

await test('nova conversa e clientes independentes não reutilizam sessão', async () => {
  let count = 0;
  const sessions = [];
  const fetcher = async (path, options) => {
    if (path === '/sessions') return json(identity(count++));
    sessions.push(JSON.parse(options.body).session_id);
    return json(reply());
  };
  const a = new ChatClient(fetcher);
  const b = new ChatClient(fetcher);
  await a.send('a'); await b.send('b'); a.reset(); await a.send('nova');
  assert.equal(new Set(sessions).size, 3);
});

await test('entradas inválidas são recusadas antes da rede', async () => {
  const client = new ChatClient(() => assert.fail('Não deveria acessar rede'));
  for (const value of ['', '  ', 'a'.repeat(2001), null]) {
    await assert.rejects(client.send(value), error => error instanceof ApiError && error.code === 'invalid_request');
  }
});

await test('erro do servidor usa mensagem pública e não repete pedido', async () => {
  let calls = 0;
  const client = new ChatClient(async path => {
    calls++;
    return path === '/sessions' ? json(identity(0)) :
      json({ error: { code: 'forbidden', message: 'PRIVATE_SERVER_DETAIL' } }, false);
  });
  await assert.rejects(client.send('Pedido 1'), error => {
    assert.ok(!error.message.includes('PRIVATE_SERVER_DETAIL'));
    return error.code === 'forbidden';
  });
  assert.equal(calls, 2);
});

await test('falha de rede e timeout não expõem exceção original', async () => {
  for (const name of ['Error', 'AbortError']) {
    const client = new ChatClient(async () => { const error = new Error('PRIVATE_DETAIL'); error.name = name; throw error; });
    await assert.rejects(client.health(), error => error.code === (name === 'AbortError' ? 'timeout' : 'network_error') && !error.message.includes('PRIVATE_DETAIL'));
  }
});

await test('resposta de sessão malformada falha de forma controlada', async () => {
  const client = new ChatClient(async () => json(null));
  await assert.rejects(client.send('Olá'), error => error instanceof ApiError && error.code === 'invalid_response');
});

class Element {
  constructor(id = '', tag = 'div') { this.id = id; this.tagName = tag.toUpperCase(); this.value = ''; this.children = []; this.dataset = {}; this.events = {}; this.attributes = {}; this.hidden = false; this.disabled = false; this.content = ''; }
  set innerHTML(value) { assert.fail('Conteúdo não pode ser interpretado como HTML: ' + typeof value); }
  set textContent(value) { this.content = String(value); this.children = []; }
  get textContent() { return this.content + this.children.map(child => child.textContent).join(''); }
  append(...nodes) { for (const child of nodes) { child.parent = this; this.children.push(child); } }
  replaceChildren(...nodes) { this.children = []; this.content = ''; this.append(...nodes); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(node => node !== this); }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(name, callback) { (this.events[name] ||= []).push(callback); }
  async dispatch(name, event = {}) { for (const callback of this.events[name] || []) await callback({ preventDefault() {}, ...event }); }
  requestSubmit() { return this.dispatch('submit'); }
  focus() { this.focused = true; }
}
class Document {
  constructor() {
    this.elements = Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(match => [match[1], new Element(match[1])]));
    this.suggestions = [...html.matchAll(/data-question="([^"]+)"/g)].map(match => { const node = new Element(); node.dataset.question = match[1]; return node; });
  }
  getElementById(id) { assert.ok(this.elements[id], 'Elemento presente no HTML: ' + id); return this.elements[id]; }
  createElement(tag) { return new Element('', tag); }
  querySelectorAll(selector) { assert.equal(selector, '[data-question]'); return this.suggestions; }
}
const settle = () => new Promise(resolve => setTimeout(resolve, 0));
const descendants = (node, tag) => node.children.flatMap(child => [
  ...(child.tagName === tag ? [child] : []), ...descendants(child, tag),
]);
const paymentTable = '| Parcelas | Valor de cada parcela |\n| --- | --- |\n' +
  Array.from({ length: 12 }, (_, i) => `| ${i+1}x | R$ ${i+1},00 |`).join('\n');

await test('tabela de parcelas tem cabeçalhos acessíveis, todas as linhas e preserva o texto ao redor', async () => {
  const document = new Document();
  const body = new Element();
  renderReply(document, body, 'Antes da tabela\n\n' + paymentTable + '\n\nDepois da tabela');
  const table = descendants(body, 'TABLE')[0];
  assert.equal(descendants(body, 'TABLE').length, 1);
  assert.equal(table.attributes['aria-label'], 'Opções de parcelamento sem juros');
  assert.deepEqual(descendants(table, 'TH').map(cell => cell.textContent), ['Parcelas', 'Valor de cada parcela']);
  assert.ok(descendants(table, 'TH').every(cell => cell.attributes.scope === 'col'));
  assert.equal(descendants(table, 'TBODY')[0].children.length, 12);
  assert.ok(body.textContent.startsWith('Antes da tabela'));
  assert.ok(body.textContent.endsWith('Depois da tabela'));
});

await test('conteúdo HTML nas células permanece texto literal', async () => {
  const document = new Document();
  const body = new Element();
  renderReply(document, body, '| Parcelas | Valor de cada parcela |\n| --- | --- |\n| 1x | <img src=x onerror=alert(1)> |');
  assert.equal(descendants(body, 'TABLE').length, 1);
  assert.equal(descendants(body, 'IMG').length, 0);
  assert.ok(body.textContent.includes('<img src=x onerror=alert(1)>'));
});

await test('tabelas inválidas e outros formatos ficam como texto, sem perder conteúdo', async () => {
  const document = new Document();
  for (const text of [
    '| Outro | Cabeçalho |\n| --- | --- |\n| 1x | R$ 1,00 |',
    '| Parcelas | Valor de cada parcela |\n| --- | --- |\n| 2x | valor |\n| 1x | valor |',
    paymentTable + '\n| 13x | valor |',
    '| Parcelas | Valor de cada parcela |\n| --- | --- |',
  ]) {
    const body = new Element(); renderReply(document, body, text);
    assert.equal(descendants(body, 'TABLE').length, 0);
    assert.equal(body.textContent, text);
  }
});

const originalFetch = globalThis.fetch;
try {
  await test('somente respostas da loja renderizam tabelas; mensagem do usuário permanece literal', async () => {
    globalThis.fetch = async path => json(path === '/health' ? { status: 'ok', chat_ready: true, execution_mode: 'offline_scripted' } : path === '/sessions' ? identity(0) : reply(paymentTable));
    const document = new Document(); boot(document); await settle();
    document.getElementById('message').value = paymentTable;
    await document.getElementById('chat-form').dispatch('submit');
    const [user, assistant] = document.getElementById('messages').children;
    assert.equal(descendants(user, 'TABLE').length, 0);
    assert.ok(user.textContent.includes(paymentTable));
    assert.equal(descendants(assistant, 'TABLE').length, 1);
  });
  await test('sugestões só preenchem campo; modo simulado é identificado', async () => {
    const paths = [];
    globalThis.fetch = async path => { paths.push(path); return json({ status: 'ok', chat_ready: true, execution_mode: 'offline_scripted' }); };
    const document = new Document(); boot(document); await settle();
    await document.suggestions[0].dispatch('click');
    assert.equal(document.getElementById('mode-label').textContent, 'Simulação offline');
    assert.equal(document.getElementById('message').value, document.suggestions[0].dataset.question);
    assert.deepEqual(paths, ['/health']);
    assert.equal(document.getElementById('send').disabled, false);
  });

  await test('conversa renderiza texto sem executar markup e mostra consultas', async () => {
    globalThis.fetch = async path => json(path === '/health' ? { status: 'ok', chat_ready: true, execution_mode: 'offline_scripted' } : path === '/sessions' ? identity(0) : reply('<img src=x onerror=alert(1)>'));
    const document = new Document(); boot(document); await settle();
    const field = document.getElementById('message'); field.value = '<script>conteúdo</script>';
    await document.getElementById('chat-form').dispatch('submit');
    const messages = document.getElementById('messages');
    assert.equal(messages.children.length, 2);
    assert.ok(messages.textContent.includes('<img src=x onerror=alert(1)>'));
    assert.ok(messages.textContent.includes('<script>conteúdo</script>'));
    assert.ok(document.getElementById('tool-list').textContent.includes('Detalhes do instrumento'));
    assert.equal(document.getElementById('response-metrics').hidden, false);
  });

  await test('envio pendente impede envio duplicado e reinício no meio da resposta', async () => {
    let complete;
    let chatCalls = 0;
    globalThis.fetch = async path => {
      if (path === '/health') return json({ status: 'ok', chat_ready: true, execution_mode: 'real' });
      if (path === '/sessions') return json(identity(0));
      chatCalls++; return new Promise(resolve => { complete = () => resolve(json({ ...reply(), execution_mode: 'real' })); });
    };
    const document = new Document(); boot(document); await settle();
    document.getElementById('message').value = 'Instrumento';
    const pending = document.getElementById('chat-form').dispatch('submit');
    await settle();
    assert.equal(document.getElementById('message').disabled, true);
    assert.equal(document.getElementById('new-chat').disabled, true);
    await document.getElementById('chat-form').dispatch('submit');
    await document.getElementById('new-chat').dispatch('click');
    assert.equal(chatCalls, 1);
    complete(); await pending;
    assert.equal(document.getElementById('message').disabled, false);
    assert.equal(document.getElementById('messages').children.length, 2);
  });

  await test('sessão expirada exige novo contexto e não reenvia mensagem', async () => {
    let created = 0;
    const sent = [];
    globalThis.fetch = async (path, options) => {
      if (path === '/health') return json({ status: 'ok', chat_ready: true, execution_mode: 'real' });
      if (path === '/sessions') return json(identity(created++));
      sent.push(JSON.parse(options.body).session_id);
      return sent.length === 1 ? json({ error: { code: 'session_access_denied' } }, false) : json({ ...reply(), execution_mode: 'real' });
    };
    const document = new Document(); boot(document); await settle();
    document.getElementById('message').value = 'Pergunta';
    await document.getElementById('chat-form').dispatch('submit');
    assert.equal(document.getElementById('message').disabled, true);
    assert.equal(sent.length, 1);
    await document.getElementById('new-chat').dispatch('click');
    assert.equal(document.getElementById('messages').children.length, 0);
    document.getElementById('message').value = 'Nova pergunta';
    await document.getElementById('chat-form').dispatch('submit');
    assert.notEqual(sent[0], sent[1]);
  });

  await test('configuração indisponível bloqueia envio', async () => {
    globalThis.fetch = async () => json({ status: 'ok', chat_ready: false, execution_mode: 'not_configured' });
    const document = new Document(); boot(document); await settle();
    document.getElementById('message').value = 'Olá';
    await document.getElementById('message').dispatch('input');
    assert.equal(document.getElementById('send').disabled, true);
    assert.equal(document.getElementById('connection').textContent, 'Indisponível');
  });
} finally { globalThis.fetch = originalFetch; }

await test('tempo é duração medida, formatada em português', async () => {
  assert.equal(formatDuration(1250), '1,3 s');
});
export const result = { passed: passed.length, tests: passed, execution: 'mock_http_and_mock_dom_no_llm_no_browser' };
console.log(JSON.stringify(result));
