const ERRORS = {
  forbidden: "Acesso negado. Esta sessão visitante não pode consultar pedidos privados.",
  unauthorized: "Sua sessão não pôde ser validada. Inicie uma nova conversa.",
  session_access_denied: "A sessão expirou ou não está disponível. Inicie uma nova conversa.",
  capacity_reached: "O atendimento está com muitas conversas abertas. Tente novamente mais tarde.",
  invalid_request: "Revise sua mensagem. Use entre 1 e 2.000 caracteres.",
  request_too_large: "A mensagem ultrapassou o limite permitido.",
  service_unavailable: "O atendimento está indisponível. Verifique a configuração local e tente novamente.",
  provider_error: "Não consegui consultar o modelo agora. Verifique se o Ollama está disponível e tente novamente.",
  timeout: "A consulta demorou mais que o esperado. Não consegui confirmar uma resposta agora.",
  agent_limit: "Não consegui concluir a consulta dentro dos limites. Tente uma pergunta mais específica.",
  network_error: "Não consegui acessar o servidor local. Verifique a conexão e tente novamente.",
  invalid_response: "O servidor não retornou uma resposta válida. Tente novamente.",
};

const TOOLS = {
  search_products: "Busca no catálogo",
  get_product_details: "Detalhes do instrumento",
  get_product_offers: "Preços e pagamento",
  get_order_status: "Consulta de pedido",
  search_store_policies: "Políticas da loja",
  get_store_info: "Informações da loja",
  unknown_tool: "Consulta não reconhecida",
};

export class ApiError extends Error {
  constructor(code) {
    super(ERRORS[code] || "Não foi possível concluir a consulta. Tente novamente.");
    this.code = code;
  }
}

export function formatDuration(milliseconds) {
  return `${(Math.max(0, milliseconds) / 1000).toLocaleString("pt-BR", {
    minimumFractionDigits: 1, maximumFractionDigits: 1,
  })} s`;
}

// Interpreta apenas a tabela de parcelas gerada pelo backend. Células e demais
// trechos continuam como texto; HTML, links e scripts nunca são interpretados.
export function renderReply(document, body, text) {
  body.replaceChildren();
  const lines = text.split("\n");
  const header = "| Parcelas | Valor de cada parcela |";
  let plain = [];
  const flush = () => {
    if (plain.some(line => line.trim())) {
      const block = document.createElement("div");
      block.className = "message-text";
      block.textContent = plain.join("\n").replace(/^\n+|\n+$/g, "");
      body.append(block);
    }
    plain = [];
  };
  for (let index = 0; index < lines.length; index++) {
    const rows = [];
    let end = index + 2;
    let valid = lines[index].trim() === header && lines[index + 1]?.trim() === "| --- | --- |";
    if (valid) {
      while (end < lines.length && lines[end].trim().startsWith("|")) {
        const match = lines[end].trim().match(/^\|\s*([1-9]|1[0-2])x\s*\|\s*([^|]{1,160}?)\s*\|$/u);
        if (!match || rows.length >= 12 || Number(match[1]) <= Number(rows.at(-1)?.[0] || 0)) {
          valid = false;
          break;
        }
        rows.push([match[1], match[2].trim()]);
        end++;
      }
    }
    if (!valid || rows.length === 0) {
      plain.push(lines[index]);
      continue;
    }
    flush();
    const wrapper = document.createElement("div");
    wrapper.className = "installment-table-wrapper";
    wrapper.setAttribute("tabindex", "0");
    const table = document.createElement("table");
    table.className = "installment-table";
    table.setAttribute("aria-label", "Opções de parcelamento sem juros");
    const head = document.createElement("thead");
    const heading = document.createElement("tr");
    for (const label of ["Parcelas", "Valor de cada parcela"]) {
      const cell = document.createElement("th");
      cell.setAttribute("scope", "col");
      cell.textContent = label;
      heading.append(cell);
    }
    head.append(heading);
    const content = document.createElement("tbody");
    for (const [count, value] of rows) {
      const row = document.createElement("tr");
      for (const label of [`${count}x`, value]) {
        const cell = document.createElement("td");
        cell.textContent = label;
        row.append(cell);
      }
      content.append(row);
    }
    table.append(head, content);
    wrapper.append(table);
    body.append(wrapper);
    index = end - 1;
  }
  flush();
}

export class ChatClient {
  #session = null;
  #fetch;

  constructor(fetcher = globalThis.fetch.bind(globalThis)) {
    this.#fetch = fetcher;
  }

  reset() { this.#session = null; }

  async request(path, options = {}, timeout = 150000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await this.#fetch(path, {
        ...options, signal: controller.signal, cache: "no-store", credentials: "omit",
      });
      let body;
      try { body = await response.json(); }
      catch { throw new ApiError("invalid_response"); }
      if (!response.ok) throw new ApiError(body?.error?.code || "invalid_response");
      return body;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(error?.name === "AbortError" ? "timeout" : "network_error");
    } finally {
      clearTimeout(timer);
    }
  }

  health() { return this.request("/health", {}, 10000); }

  async send(message) {
    if (typeof message !== "string" || !message.trim() || message.length > 2000) {
      throw new ApiError("invalid_request");
    }
    if (!this.#session) {
      const created = await this.request("/sessions", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      }, 10000);
      if (!created || !/^[A-Za-z0-9_-]{43}$/.test(created.session_id || "") ||
          !/^[A-Za-z0-9_-]{43}$/.test(created.session_token || "")) {
        throw new ApiError("invalid_response");
      }
      this.#session = { id: created.session_id, token: created.session_token };
    }
    try {
      const reply = await this.request("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${this.#session.token}` },
        body: JSON.stringify({ session_id: this.#session.id, message: message.trim() }),
      });
      if (!reply || typeof reply.text !== "string" ||
          !["answered", "abstained"].includes(reply.status) ||
          !["real", "offline_scripted"].includes(reply.execution_mode)) {
        throw new ApiError("invalid_response");
      }
      return reply;
    } catch (error) {
      if (["unauthorized", "session_access_denied"].includes(error.code)) this.reset();
      throw error;
    }
  }
}

export function boot(document) {
  const client = new ChatClient();
  const byId = (id) => document.getElementById(id);
  const field = byId("message");
  const feed = byId("messages");
  const scroll = byId("conversation-scroll");
  let busy = false;
  let ready = false;
  let expired = false;

  function controls() {
    byId("send").disabled = busy || !ready || expired || !field.value.trim();
    field.disabled = busy || expired;
    byId("new-chat").disabled = busy;
    byId("reconnect").disabled = busy;
    byId("character-count").textContent = `${field.value.length} / 2000`;
    document.querySelectorAll("[data-question]").forEach((button) => { button.disabled = busy; });
  }

  function notice(text = "") {
    byId("service-notice").textContent = text;
    byId("service-notice").hidden = !text;
  }

  function mode(value) {
    byId("mode-label").textContent = value === "real" ? "Modelo real" :
      value === "offline_scripted" ? "Simulação offline" : "Não configurado";
  }

  function bottom() { scroll.scrollTop = scroll.scrollHeight; }

  function message(text, role, pending = false) {
    const article = document.createElement("article");
    article.className = `message ${role}${pending ? " pending" : ""}`;
    article.setAttribute("aria-label", role === "user" ? "Sua mensagem" : "Resposta da loja");
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const label = document.createElement("strong");
    label.textContent = role === "user" ? "Você" : "Empório da Música";
    const time = document.createElement("span");
    time.textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    meta.append(label, time);
    const body = document.createElement("div");
    body.className = "message-body";
    if (role === "assistant" && !pending) renderReply(document, body, text);
    else body.textContent = text;
    article.append(meta, body);
    if (pending) article.setAttribute("aria-busy", "true");
    feed.append(article);
    bottom();
    return article;
  }

  function details(reply, duration) {
    const tools = Array.isArray(reply.tools) ? reply.tools : [];
    byId("tool-list").replaceChildren();
    byId("tools-empty").hidden = tools.length > 0;
    byId("tools-empty").textContent = "Esta resposta não usou consultas. Pode ser um esclarecimento ou redirecionamento.";
    tools.forEach((tool) => {
      const item = document.createElement("li");
      item.dataset.state = tool.status === "ok" ? "ok" : "error";
      const title = document.createElement("span");
      title.textContent = TOOLS[tool.name] || "Consulta não reconhecida";
      const status = document.createElement("small");
      status.textContent = tool.status === "ok" ? "Consulta concluída" : "Informação não confirmada";
      title.append(status);
      item.append(title);
      byId("tool-list").append(item);
    });
    byId("response-time").textContent = formatDuration(duration);
    byId("response-status").textContent = reply.status === "abstained" ? "Não confirmada" : "Concluída";
    byId("response-metrics").hidden = false;
    mode(reply.execution_mode);
  }

  function resetDetails(text) {
    byId("tool-list").replaceChildren();
    byId("tools-empty").hidden = false;
    byId("tools-empty").textContent = text;
    byId("response-metrics").hidden = true;
  }

  async function checkHealth() {
    ready = false;
    controls();
    byId("connection").dataset.state = "loading";
    byId("connection").textContent = "Verificando";
    try {
      const health = await client.health();
      ready = health.status === "ok" && health.chat_ready === true;
      mode(health.execution_mode);
      byId("connection").textContent = ready ? "API disponível" : "Indisponível";
      byId("connection").dataset.state = ready ? "ready" : "error";
      notice(ready ? "" : ERRORS.service_unavailable);
    } catch (error) {
      byId("connection").textContent = "Sem conexão";
      byId("connection").dataset.state = "error";
      notice(error.message);
    }
    controls();
  }

  byId("chat-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !ready || expired || !field.value.trim()) return;
    const text = field.value.trim();
    if (text.length > 2000) { notice(ERRORS.invalid_request); return; }
    busy = true;
    notice();
    byId("welcome").hidden = true;
    message(text, "user");
    field.value = "";
    controls();
    resetDetails("Consultando as informações necessárias para esta resposta…");
    const pending = message("Consultando as informações da loja", "assistant", true);
    const started = performance.now();
    try {
      const reply = await client.send(text);
      pending.remove();
      message(reply.text, "assistant");
      details(reply, performance.now() - started);
    } catch (error) {
      pending.remove();
      message(error.message, "error");
      resetDetails("A consulta não foi concluída. Nenhum dado foi confirmado nesta resposta.");
      expired = ["unauthorized", "session_access_denied"].includes(error.code);
      if (expired) notice("Inicie uma nova conversa para continuar com uma sessão válida.");
    } finally {
      busy = false;
      controls();
      if (!expired) field.focus();
      bottom();
    }
  });

  field.addEventListener("input", controls);
  field.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!byId("send").disabled) byId("chat-form").requestSubmit();
    }
  });
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      if (busy) return;
      field.value = button.dataset.question;
      controls();
      field.focus();
    });
  });
  byId("new-chat").addEventListener("click", () => {
    if (busy) return;
    client.reset();
    expired = false;
    feed.replaceChildren();
    field.value = "";
    byId("welcome").hidden = false;
    resetDetails("Ao conversar, você verá aqui quais informações a loja consultou.");
    notice();
    controls();
    field.focus();
  });
  byId("reconnect").addEventListener("click", checkHealth);
  controls();
  checkHealth();
}

if (typeof document !== "undefined") boot(document);
