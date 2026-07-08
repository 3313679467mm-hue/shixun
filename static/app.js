const state = {
  kbs: [],
  models: [],
  roles: [],
  users: [],
  permissions: [],
  systemConfig: {},
  ollamaModels: [],
  token: localStorage.getItem("authToken") || "",
  user: null,
  authMode: "login",
  editingUserId: "",
  editingRoleId: "",
  conversationId: localStorage.getItem("conversationId") || "",
  chatHistories: [],
  currentMessages: [],
  currentDocId: "",
  currentKbId: "",
  pendingAvatarData: "",
  isAnswering: false,
  logs: [],
  collapsedLogAccounts: new Set(),
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const DEFAULT_QUICK_PROMPTS = [
  "韩信怎么玩",
  "凯怎么玩",
  "后羿怎么出装",
  "貂蝉铭文怎么搭配",
  "点券不到账怎么办",
  "怎么改实名认证",
  "活动奖励没到账",
  "我要转人工客服",
  "账号被封怎么申诉",
];
const HERO_NAMES = [
  "韩信",
  "凯",
  "铠",
  "后羿",
  "鲁班七号",
  "孙尚香",
  "马可波罗",
  "狄仁杰",
  "李白",
  "赵云",
  "孙悟空",
  "澜",
  "镜",
  "兰陵王",
  "娜可露露",
  "露娜",
  "貂蝉",
  "妲己",
  "王昭君",
  "安琪拉",
  "诸葛亮",
  "小乔",
  "甄姬",
  "不知火舞",
  "亚瑟",
  "吕布",
  "程咬金",
  "夏侯惇",
  "花木兰",
  "关羽",
  "马超",
  "老夫子",
  "项羽",
  "张飞",
  "牛魔",
  "东皇太一",
  "蔡文姬",
  "瑶",
  "明世隐",
  "大乔",
  "孙膑",
];
const VIEW_PERMISSIONS = {
  chat: "chat:use",
  knowledge: ["kb:read", "kb:write", "doc:read", "doc:write"],
  vectors: "vector:manage",
  system: "system:manage",
  access: "auth:manage",
  logs: "log:read",
};

function formatTime(ms) {
  return new Date(ms).toLocaleString("zh-CN", { hour12: false });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function cleanDisplayText(value) {
  return String(value || "")
    .replace(/^\s*#{1,6}\s*/gm, "")
    .replaceAll("#", "")
    .trim();
}

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function renderAnswerLine(line, index) {
  const headingMatch = line.match(/^([^：:]{2,18})[：:]$/);
  if (headingMatch) {
    return `<p class="answer-heading">${escapeHtml(headingMatch[1])}</p>`;
  }
  const labelMatch = line.match(/^([^：:]{2,14}[：:])\s*(.+)$/);
  if (labelMatch && !/[，。！？!?；;]/.test(labelMatch[1])) {
    return `<p class="${index === 0 ? "answer-lead" : ""}"><strong class="answer-label">${escapeHtml(labelMatch[1])}</strong>${inlineMarkdown(labelMatch[2])}</p>`;
  }
  return `<p class="${index === 0 ? "answer-lead" : ""}">${inlineMarkdown(line)}</p>`;
}

function renderMessageHtml(value) {
  const lines = cleanDisplayText(value).split(/\n+/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return "";
  const html = [];
  let listItems = [];
  const flushList = () => {
    if (!listItems.length) return;
    html.push(`<ul>${listItems.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ul>`);
    listItems = [];
  };
  lines.forEach((line) => {
    const match = line.match(/^(?:[-*]|\d+[.、])\s*(.+)$/);
    if (match) {
      listItems.push(match[1]);
      return;
    }
    flushList();
    html.push(renderAnswerLine(line, html.length));
  });
  flushList();
  return html.join("");
}

function messageLoadingSvg() {
  return `
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
      <circle cx="4" cy="12" r="2" fill="currentColor">
        <animate id="spinner_qFRN" begin="0;spinner_OcgL.end+0.25s" attributeName="cy" calcMode="spline" dur="0.6s" values="12;6;12" keySplines=".33,.66,.66,1;.33,0,.66,.33" />
      </circle>
      <circle cx="12" cy="12" r="2" fill="currentColor">
        <animate begin="spinner_qFRN.begin+0.1s" attributeName="cy" calcMode="spline" dur="0.6s" values="12;6;12" keySplines=".33,.66,.66,1;.33,0,.66,.33" />
      </circle>
      <circle cx="20" cy="12" r="2" fill="currentColor">
        <animate id="spinner_OcgL" begin="spinner_qFRN.begin+0.2s" attributeName="cy" calcMode="spline" dur="0.6s" values="12;6;12" keySplines=".33,.66,.66,1;.33,0,.66,.33" />
      </circle>
    </svg>
  `;
}

function scrollMessagesToBottom() {
  const target = $("#messages");
  if (!target) return;
  requestAnimationFrame(() => {
    target.scrollTo({ top: target.scrollHeight, behavior: "smooth" });
  });
}

function promptButtonHtml(question) {
  return `<button type="button" data-quick-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`;
}

function renderPromptButtons(questions) {
  return questions.map(promptButtonHtml).join("");
}

function uniqueQuestions(questions, limit = 6) {
  return [...new Set(questions.map((item) => String(item || "").trim()).filter(Boolean))].slice(0, limit);
}

function extractHeroNames(text) {
  const value = String(text || "");
  return uniqueQuestions(
    HERO_NAMES.filter((name) => value.includes(name)).map((name) => (name === "铠" ? "凯" : name)),
    2,
  );
}

function buildRelatedQuestions(question, answer) {
  const combined = `${question} ${answer}`;
  const heroes = extractHeroNames(combined);
  const items = [];
  heroes.forEach((hero) => {
    items.push(`${hero}怎么出装`, `${hero}铭文怎么搭配`, `${hero}连招怎么打`, `哪些英雄克制${hero}`);
  });
  if (/实名|账号|封|处罚|申诉|登录|找回/.test(combined)) {
    items.push("账号被封怎么申诉", "实名认证怎么修改", "如何找回账号", "怎么转人工客服");
  }
  if (/点券|充值|支付|到账|订单/.test(combined)) {
    items.push("点券不到账怎么办", "充值扣款了怎么处理", "怎么查询订单号", "怎么联系人工客服");
  }
  if (/活动|奖励|皮肤|礼包|邮件/.test(combined)) {
    items.push("活动奖励没到账怎么办", "游戏邮件没收到奖励", "皮肤领取失败怎么处理", "活动规则在哪里看");
  }
  if (/排位|上分|打法|怎么玩|出装|铭文|连招|克制|英雄/.test(combined)) {
    items.push("射手怎么玩", "打野前期怎么带节奏", "新手适合练哪些英雄", "团战应该怎么站位");
  }
  return uniqueQuestions(items.length ? items : DEFAULT_QUICK_PROMPTS, 6);
}

function renderEmptyQuickPrompts() {
  const panel = $("#emptyQuickPrompts");
  if (!panel) return;
  const shouldShow = !state.currentMessages.length && !$("#messages")?.querySelector(".message");
  panel.classList.toggle("hidden", !shouldShow);
  panel.parentElement?.classList.toggle("has-empty-prompts", shouldShow);
  if (!shouldShow) return;
  panel.innerHTML = `
    <div class="quick-welcome-title">有什么我能帮你的吗？</div>
    <div class="quick-prompt-grid">${renderPromptButtons(DEFAULT_QUICK_PROMPTS)}</div>
  `;
}

function hideEmptyQuickPrompts() {
  const panel = $("#emptyQuickPrompts");
  if (!panel) return;
  panel.classList.add("hidden");
  panel.parentElement?.classList.remove("has-empty-prompts");
}

function removeFollowupPrompts() {
  $$(".message-followups").forEach((node) => node.remove());
}

function renderFollowupPrompts(messageNode, question, answer) {
  if (!messageNode) return;
  const questions = buildRelatedQuestions(question, answer);
  const panel = document.createElement("div");
  panel.className = "message-followups";
  panel.innerHTML = `<div class="followup-title">你还可以继续问</div><div class="followup-list">${renderPromptButtons(questions)}</div>`;
  messageNode.append(panel);
  scrollMessagesToBottom();
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) {
    headers.set("Authorization", `Bearer ${state.token}`);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && !["/api/auth/login", "/api/auth/register", "/api/auth/setup"].includes(path)) {
    state.token = "";
    state.user = null;
    localStorage.removeItem("authToken");
    applyPermissions();
    showAuth("login");
  }
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function showAuth(mode = "login") {
  state.authMode = mode;
  $("#authOverlay").classList.add("active");
  const isSetup = mode === "setup";
  const isRegister = mode === "register";
  $("#authTitle").textContent = isSetup ? "初始化超级管理员" : isRegister ? "注册普通用户" : "登录系统";
  $("#authHint").textContent = isSetup
    ? "首次使用需要先创建一个超级管理员账号。"
    : isRegister
      ? "注册后仅进入对话咨询界面。"
      : "请输入账号密码进入服务台。";
  $("#authSubmit").textContent = isSetup ? "创建管理员" : isRegister ? "注册并进入" : "登录";
  const switcher = $("#authSwitch");
  switcher.classList.toggle("hidden", isSetup);
  switcher.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", button.dataset.authMode === mode);
  });
  const email = $("#authForm").elements.email;
  email.style.display = isRegister || isSetup ? "block" : "none";
  email.required = false;
  email.placeholder = isSetup ? "管理员邮箱（可选）" : "邮箱（可选）";
}

function hideAuth() {
  $("#authOverlay").classList.remove("active");
}

function finishAuthLoading() {
  document.body.classList.remove("auth-loading");
}

function userInitial(label) {
  const text = String(label || "未").trim();
  return text ? text.slice(0, 1).toUpperCase() : "未";
}

function displayUserName() {
  if (!state.user) return "未登录";
  return state.user.displayName || state.user.username || "未命名用户";
}

function renderAvatar(target, name, avatarData) {
  if (!target) return;
  if (avatarData) {
    target.innerHTML = `<img src="${escapeHtml(avatarData)}" alt="" />`;
    return;
  }
  target.textContent = userInitial(name);
}

function fillProfileDialog() {
  const form = $("#profileForm");
  if (!form || !state.user) return;
  const name = displayUserName();
  state.pendingAvatarData = state.user.avatarData || "";
  form.elements.displayName.value = name;
  renderAvatar($("#profileAvatarPreview"), name, state.pendingAvatarData);
}

function openProfileDialog() {
  fillProfileDialog();
  $("#profileDialog")?.showModal();
}

function readAvatarFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("头像读取失败。"));
    reader.readAsDataURL(file);
  });
}

function readTextFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("文件读取失败。"));
    reader.readAsText(file, "utf-8");
  });
}

function splitRuleTerms(value) {
  return String(value || "")
    .split(/[\n,，;；|]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function mergeRuleTerms(current, imported) {
  return Array.from(new Set([...splitRuleTerms(current), ...splitRuleTerms(imported)])).join("\n");
}

function closeChatUserMenu() {
  const menu = $("#chatUserMenu");
  const button = $("#chatUserMenuBtn");
  if (!menu || !button) return;
  menu.classList.remove("open");
  menu.setAttribute("aria-hidden", "true");
  button.setAttribute("aria-expanded", "false");
}

function toggleChatUserMenu() {
  const menu = $("#chatUserMenu");
  const button = $("#chatUserMenuBtn");
  if (!menu || !button) return;
  const isOpen = menu.classList.toggle("open");
  menu.setAttribute("aria-hidden", String(!isOpen));
  button.setAttribute("aria-expanded", String(isOpen));
}

function updateCurrentUser() {
  const displayName = displayUserName();
  const label = state.user ? `${displayName} / ${state.user.roleName}` : "未登录";
  $("#currentUser").textContent = label;
  if ($("#chatCurrentUser")) {
    $("#chatCurrentUser").textContent = displayName;
  }
  if ($("#chatUserAvatar")) {
    renderAvatar($("#chatUserAvatar"), displayName, state.user?.avatarData || "");
  }
  const logoutBtn = $("#logoutBtn");
  if (state.user) {
    logoutBtn.textContent = "退出";
    logoutBtn.onclick = logoutCurrentUser;
  } else {
    logoutBtn.textContent = "登录";
    logoutBtn.onclick = () => { window.location.href = "/static/login.html"; };
    closeChatUserMenu();
  }
}

function can(permission) {
  if (!state.user) return false;
  return state.user.permissions.includes("*") || state.user.permissions.includes(permission);
}

function canAny(permissions) {
  const values = Array.isArray(permissions) ? permissions : [permissions];
  return values.some((permission) => can(permission));
}

function isChatOnlyUser() {
  return Boolean(state.user && can("chat:use") && !canAny(["kb:read", "kb:write", "doc:read", "doc:write", "vector:manage", "system:manage", "auth:manage", "log:read"]));
}

function chatHistoryKey() {
  const userId = state.user?.id || state.user?.username || "guest";
  return `chatHistories:${userId}`;
}

function loadChatHistories() {
  try {
    const rows = JSON.parse(localStorage.getItem(chatHistoryKey()) || "[]");
    state.chatHistories = Array.isArray(rows) ? rows : [];
  } catch {
    state.chatHistories = [];
  }
}

function saveChatHistories() {
  localStorage.setItem(chatHistoryKey(), JSON.stringify(state.chatHistories.slice(0, 80)));
}

function renderChatHistories() {
  const list = $("#chatHistoryList");
  if (!list) return;
  const keyword = ($("#chatHistorySearch")?.value || "").trim().toLowerCase();
  const rows = state.chatHistories
    .filter((item) => !keyword || `${item.title} ${item.preview || ""}`.toLowerCase().includes(keyword))
    .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  if (!rows.length) {
    list.innerHTML = '<div class="history-empty">还没有历史对话。发送一次问题后会自动保存。</div>';
    return;
  }
  list.innerHTML = rows
    .map(
      (item) => `
        <button type="button" class="history-item ${item.id === state.conversationId ? "active" : ""}" data-history-id="${item.id}">
          <div class="history-title">${escapeHtml(item.title || "未命名对话")}</div>
          <div class="history-date">${formatTime(item.updatedAt || Date.now())}</div>
        </button>
      `,
    )
    .join("");
}

function persistChatExchange(question, answer, sources = []) {
  if (!isChatOnlyUser() || !state.conversationId) return;
  const now = Date.now();
  const existing = state.chatHistories.find((item) => item.id === state.conversationId);
  const messages = state.currentMessages.slice(-80);
  const item = {
    id: state.conversationId,
    title: existing?.title || question.slice(0, 36) || "新对话",
    preview: answer.slice(0, 80),
    updatedAt: now,
    messages,
  };
  state.chatHistories = [item, ...state.chatHistories.filter((row) => row.id !== item.id)];
  saveChatHistories();
  renderChatHistories();
}

function renderCurrentConversation() {
  $("#messages").innerHTML = "";
  state.currentMessages.forEach((message, index) => {
    addMessage(message.role, message.content, message.sources || [], { track: false, index, debug: message.debug || null });
  });
  renderEmptyQuickPrompts();
  renderChatHistories();
}

function updateCurrentHistoryConversation() {
  if (!isChatOnlyUser() || !state.conversationId || !state.currentMessages.length) return;
  const existing = state.chatHistories.find((row) => row.id === state.conversationId);
  if (!existing) return;
  const firstUser = state.currentMessages.find((message) => message.role === "user");
  const lastAssistant = [...state.currentMessages].reverse().find((message) => message.role === "assistant");
  const item = {
    id: state.conversationId,
    title: existing.title || firstUser?.content?.slice(0, 36) || "新对话",
    preview: lastAssistant?.content?.slice(0, 80) || firstUser?.content?.slice(0, 80) || "",
    updatedAt: Date.now(),
    messages: state.currentMessages.slice(-80),
  };
  state.chatHistories = [item, ...state.chatHistories.filter((row) => row.id !== item.id)];
  saveChatHistories();
  renderChatHistories();
}

function loadChatHistory(id) {
  const item = state.chatHistories.find((row) => row.id === id);
  if (!item) return;
  state.conversationId = item.id;
  state.currentMessages = (item.messages || []).map((message) => ({ ...message }));
  localStorage.setItem("conversationId", item.id);
  renderCurrentConversation();
}

function startNewChatTask() {
  state.conversationId = "";
  state.currentMessages = [];
  localStorage.removeItem("conversationId");
  $("#messages").innerHTML = "";
  renderEmptyQuickPrompts();
  renderChatHistories();
}

function setupChatHistoryPanel() {
  if (!isChatOnlyUser()) return false;
  loadChatHistories();
  renderChatHistories();
  if (state.conversationId && state.chatHistories.some((item) => item.id === state.conversationId)) {
    loadChatHistory(state.conversationId);
    return true;
  }
  return false;
}

function activateView(view) {
  const target = $(`.nav-item[data-view="${view}"]`);
  if (!target || target.classList.contains("hidden")) return;
  $$(".nav-item").forEach((item) => item.classList.remove("active"));
  $$(".view").forEach((item) => item.classList.remove("active"));
  target.classList.add("active");
  $(`#${view}`).classList.add("active");
}

function applyPermissions() {
  const chatOnly = isChatOnlyUser();
  document.body.classList.toggle("chat-only", chatOnly);
  if (chatOnly && $("#globalKb")) {
    $("#globalKb").value = "";
  }
  $$(".nav-item").forEach((button) => {
    const allowed = state.user ? canAny(VIEW_PERMISSIONS[button.dataset.view] || []) : button.dataset.view === "chat";
    button.classList.toggle("hidden", !allowed);
  });
  const active = $(".nav-item.active");
  if (!active || active.classList.contains("hidden")) {
    const first = $$(".nav-item").find((button) => !button.classList.contains("hidden"));
    if (first) activateView(first.dataset.view);
  }
}

async function ensureAuth() {
  const status = await api("/api/auth/status");
  if (!status.initialized) {
    showAuth("setup");
    return false;
  }
  if (!state.token) {
    showAuth("login");
    return false;
  }
  try {
    const data = await api("/api/me");
    state.user = data.user;
    updateCurrentUser();
    applyPermissions();
    hideAuth();
    return true;
  } catch {
    showAuth("login");
    return false;
  }
}

function setOptions(select, items, includeAll = false) {
  if (!select) return;
  select.innerHTML = "";
  if (includeAll) {
    select.append(new Option("全部知识库", ""));
  }
  items.forEach((item) => {
    select.append(new Option(item.name, item.id));
  });
}

function setMultiOptions(select, items) {
  if (!select) return;
  select.innerHTML = "";
  items.forEach((item) => {
    select.append(new Option(item.name, item.id));
  });
}

function setModelOptions() {
  $$("[data-model-select]").forEach((select) => {
    const previous = select.value;
    select.innerHTML = "";
    state.models.forEach((model) => {
      const label = model.is_default ? `${model.name}（默认）` : model.name;
      select.append(new Option(label, model.name));
    });
    const defaultModel = state.models.find((model) => model.is_default) || state.models[0];
    if (previous && state.models.some((model) => model.name === previous)) {
      select.value = previous;
    } else if (defaultModel) {
      select.value = defaultModel.name;
    }
  });
}

function formatModelSize(size) {
  const value = Number(size || 0);
  if (!value) return "";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)}GB`;
  if (value >= 1024 ** 2) return `${Math.round(value / 1024 ** 2)}MB`;
  return `${value}B`;
}

function setOllamaModelOptions(selected = "") {
  const select = $("#ollamaModelSelect");
  if (!select) return;
  const previous = selected || select.value || state.systemConfig.ollamaModel || "";
  select.innerHTML = "";
  select.append(new Option("自动选择本地模型", ""));
  state.ollamaModels.forEach((model) => {
    const size = formatModelSize(model.size);
    select.append(new Option(size ? `${model.name}（${size}）` : model.name, model.name));
  });
  if (previous && !state.ollamaModels.some((model) => model.name === previous)) {
    select.append(new Option(`${previous}（当前配置，未检测到）`, previous));
  }
  select.value = previous;
}

async function loadOllamaModels() {
  const status = $("#ollamaModelStatus");
  const url = $("#systemForm")?.elements.ollamaUrl?.value || state.systemConfig.ollamaUrl || "http://127.0.0.1:11434";
  if (status) status.textContent = "正在检测本地 Ollama 模型...";
  try {
    const data = await api(`/api/ollama/models?url=${encodeURIComponent(url)}`);
    state.ollamaModels = data.models || [];
    setOllamaModelOptions(state.systemConfig.ollamaModel || "");
    if (status) {
      status.textContent = state.ollamaModels.length
        ? `已检测到 ${state.ollamaModels.length} 个模型，可在下拉框切换。`
        : "未检测到模型，请确认 Ollama 已启动并已 pull 模型。";
    }
  } catch (error) {
    state.ollamaModels = [];
    setOllamaModelOptions(state.systemConfig.ollamaModel || "");
    if (status) status.textContent = error.message;
  }
}

function syncLlmProviderFields() {
  const form = $("#systemForm");
  if (!form) return;
  const provider = form.elements.llmProvider?.value || "ollama";
  const status = $("#ollamaModelStatus");
  if (status && provider === "online") {
    status.textContent = "当前使用在线 API，保存配置后会按厂商、API 地址、模型名和 API Key 调用。";
  } else if (status && provider === "ollama") {
    status.textContent = "当前使用本地 Ollama，可点击按钮检测本地模型。";
  }
}

async function loadModels() {
  state.models = await api("/api/models");
  setModelOptions();
  renderModels();
}

async function loadSystemConfig() {
  state.systemConfig = await api("/api/system/config");
  const form = $("#systemForm");
  if (!form) return;
  Object.entries(state.systemConfig).forEach(([key, value]) => {
    const field = form.elements[key];
    if (!field) return;
    if (field.type === "checkbox") {
      field.checked = Boolean(value);
    } else {
      field.value = value;
    }
  });
  setOllamaModelOptions(state.systemConfig.ollamaModel || "");
  $("#chunkSize").value = state.systemConfig.chunkSize || 400;
  $("#chunkOverlap").value = state.systemConfig.chunkOverlap || 50;
  $("#vectorChunkSize").value = state.systemConfig.chunkSize || 400;
  $("#vectorChunkOverlap").value = state.systemConfig.chunkOverlap || 50;
  $("#topK").value = state.systemConfig.defaultTopK || 6;
  $("#threshold").value = state.systemConfig.defaultThreshold ?? 0.22;
  $("#systemConfigResult").textContent = "配置已加载。";
  syncLlmProviderFields();
  if (can("system:manage") && (state.systemConfig.llmProvider || "ollama") === "ollama") {
    await loadOllamaModels();
  }
}

async function loadKbs(options = {}) {
  const selectedGlobalKb = options.resetGlobal ? "" : $("#globalKb").value;
  const [sort, dir] = ($("#kbSort")?.value || "created_at:desc").split(":");
  const params = new URLSearchParams({
    q: $("#kbSearch")?.value || "",
    department: $("#kbDepartment")?.value || "",
    sort,
    dir,
  });
  state.kbs = await api(`/api/kbs?${params}`);
  setOptions($("#globalKb"), state.kbs, true);
  setOptions($("#uploadKb"), state.kbs, false);
  setOptions($("#vectorKb"), state.kbs, true);
  setOptions($("#testKb"), state.kbs, true);
  setMultiOptions($("#userKbScope"), state.kbs);
  if (options.resetGlobal) {
    $("#globalKb").value = "";
  } else if (selectedGlobalKb && state.kbs.some((kb) => kb.id === selectedGlobalKb)) {
    $("#globalKb").value = selectedGlobalKb;
  } else {
    $("#globalKb").value = "";
  }
  if ($("#vectorKb")) {
    $("#vectorKb").value = $("#globalKb").value || state.kbs[0]?.id || "";
  }
  renderKbs();
  if (can("doc:read")) {
    await loadDocuments();
  }
}

async function loadAccessData() {
  if (!can("auth:manage")) {
    $("#userList").innerHTML = '<div class="empty">当前账号没有权限管理权限。</div>';
    $("#roleList").innerHTML = '<div class="empty">当前账号没有角色管理权限。</div>';
    return;
  }
  const [roles, users, permissions] = await Promise.all([
    api("/api/roles"),
    api("/api/users"),
    api("/api/permissions/catalog"),
  ]);
  state.roles = roles;
  state.users = users;
  state.permissions = permissions;
  renderRoleOptions();
  renderPermissionList([]);
  renderUsers();
  renderRoles();
}

function renderRoleOptions() {
  const select = $("#userRole");
  select.innerHTML = "";
  state.roles.forEach((role) => select.append(new Option(role.name, role.id)));
}

function renderPermissionList(selected = []) {
  const target = $("#permissionList");
  target.innerHTML = state.permissions
    .map(
      (permission) => `
        <label class="check-row">
          <input type="checkbox" value="${permission.key}" ${selected.includes("*") || selected.includes(permission.key) ? "checked" : ""} />
          ${escapeHtml(permission.name)}
        </label>
      `,
    )
    .join("");
}

function renderUsers() {
  const target = $("#userList");
  if (!state.users.length) {
    target.innerHTML = '<div class="empty">还没有用户。</div>';
    return;
  }
  target.innerHTML = `
    <table>
      <thead><tr><th>用户</th><th>角色</th><th>部门</th><th>状态</th><th>知识库范围</th><th>操作</th></tr></thead>
      <tbody>
        ${state.users
          .map((user) => {
            const scope = user.allowedKbIds.length
              ? user.allowedKbIds.map((id) => state.kbs.find((kb) => kb.id === id)?.name || id).join("、")
              : "全部";
            return `
              <tr>
                <td>${escapeHtml(user.username)}<br /><span class="muted">${escapeHtml(user.email || "未设置邮箱")}</span></td>
                <td>${escapeHtml(user.roleName)}</td>
                <td>${escapeHtml(user.department || "未设置")}</td>
                <td>${user.status === "enabled" ? "启用" : "禁用"}</td>
                <td>${escapeHtml(scope)}</td>
                <td>
                  <button class="secondary small" data-edit-user="${user.id}">编辑</button>
                  <button class="danger small" data-delete-user="${user.id}">删除</button>
                </td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
}

function renderRoles() {
  const target = $("#roleList");
  if (!state.roles.length) {
    target.innerHTML = '<div class="empty">还没有角色。</div>';
    return;
  }
  target.innerHTML = `
    <table>
      <thead><tr><th>角色</th><th>权限</th><th>用户数</th><th>操作</th></tr></thead>
      <tbody>
        ${state.roles
          .map((role) => `
            <tr>
              <td>${escapeHtml(role.name)}<br /><span class="muted">${escapeHtml(role.description || "")}</span></td>
              <td>${role.permissions.includes("*") ? "全部权限" : role.permissions.map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join(" ")}</td>
              <td>${role.user_count || 0}</td>
              <td>
                <button class="secondary small" data-edit-role="${role.id}">编辑</button>
                <button class="danger small" data-delete-role="${role.id}" ${role.builtin ? "disabled" : ""}>删除</button>
              </td>
            </tr>
          `)
          .join("")}
      </tbody>
    </table>
  `;
}

function resetUserForm() {
  state.editingUserId = "";
  $("#userForm").reset();
  $("#userForm").elements.status.value = "enabled";
  $("#userForm").elements.failedAttempts.value = 0;
}

function resetRoleForm() {
  state.editingRoleId = "";
  $("#roleForm").reset();
  renderPermissionList([]);
}

async function loadDocuments() {
  const [sort, dir] = ($("#docSort")?.value || "created_at:desc").split(":");
  const params = new URLSearchParams({
    q: $("#docSearch")?.value || "",
    sort,
    dir,
  });
  const rows = await api(`/api/documents?${params}`);
  const target = $("#docList");
  if (!rows.length) {
    target.innerHTML = '<div class="empty">还没有上传文档。</div>';
    return;
  }
  target.innerHTML = `
    <table>
      <thead>
        <tr>
          <th></th>
          <th>文档</th>
          <th>知识库</th>
          <th>格式</th>
          <th>大小</th>
          <th>分块</th>
          <th>状态</th>
          <th>上传时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                <td><input type="checkbox" data-doc-check="${row.id}" /></td>
                <td>${escapeHtml(row.name)}</td>
                <td>${escapeHtml(row.kb_name)}</td>
                <td>${escapeHtml(row.file_type)}</td>
                <td>${Math.ceil(row.size / 1024)} KB</td>
                <td>${row.chunk_count}</td>
                <td>${escapeHtml(row.status)}</td>
                <td>${formatTime(row.created_at)}</td>
                <td>
                  <button class="secondary" data-preview-doc="${row.id}">预览/编辑</button>
                  <button class="secondary" data-delete-doc="${row.id}">删除</button>
                </td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderKbs() {
  const target = $("#kbList");
  if (!state.kbs.length) {
    target.innerHTML = '<div class="empty">还没有知识库。</div>';
    return;
  }
  target.innerHTML = state.kbs
    .map(
      (kb) => `
        <article class="card">
          <div class="card-head">
            <h3>${escapeHtml(kb.name)}</h3>
          </div>
          <p>${escapeHtml(kb.description || "暂无描述")}</p>
          <div class="meta">
            <span class="pill">${escapeHtml(kb.category || "未分类")}</span>
            <span>${kb.document_count} 篇文档</span>
            <span>${kb.chunk_count} 个文本块</span>
            <span>部门：${escapeHtml(kb.department || "未设置")}</span>
            <span>负责人：${escapeHtml(kb.owner || "未设置")}</span>
            <span>模型：${escapeHtml(kb.embedding_model || "未设置")}</span>
          </div>
          <div class="card-actions">
            <button class="secondary small" data-edit-kb="${kb.id}">编辑</button>
            <button class="secondary small" data-clone-kb="${kb.id}" data-kb-name="${escapeHtml(kb.name)}">克隆</button>
            <button class="secondary small" data-delete-kb="${kb.id}" data-delete-mode="logical" data-kb-name="${escapeHtml(kb.name)}">逻辑删除</button>
            <button class="danger small" data-delete-kb="${kb.id}" data-delete-mode="physical" data-kb-name="${escapeHtml(kb.name)}">物理删除</button>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderModels() {
  const target = $("#modelList");
  if (!target) return;
  if (!state.models.length) {
    target.innerHTML = '<div class="empty">还没有模型配置。</div>';
    return;
  }
  target.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>模型</th>
          <th>路径</th>
          <th>维度</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${state.models
          .map(
            (model) => `
              <tr>
                <td>${escapeHtml(model.name)}</td>
                <td>${escapeHtml(model.path || "未设置")}</td>
                <td>${model.dimension || "-"}</td>
                <td>${model.is_default ? "默认" : "可用"}</td>
                <td>
                  <button class="secondary small" data-default-model="${model.id}" ${model.is_default ? "disabled" : ""}>设为默认</button>
                </td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function openKbEditor(kbId) {
  const kb = state.kbs.find((item) => item.id === kbId);
  if (!kb) return;
  state.currentKbId = kbId;
  $("#editKbName").value = kb.name || "";
  $("#editKbDepartment").value = kb.department || "";
  $("#editKbOwner").value = kb.owner || "";
  $("#editKbCategory").value = kb.category || "英雄攻略";
  $("#editKbEmbedding").value = kb.embedding_model || "local-keyword-vector";
  $("#editKbDescription").value = kb.description || "";
  $("#kbDialog").showModal();
}

async function loadVectorPreview() {
  const params = new URLSearchParams({
    kbId: $("#vectorKb")?.value || "",
    q: $("#vectorSearch")?.value || "",
    limit: $("#vectorLimit")?.value || "12",
  });
  const data = await api(`/api/vectors/preview?${params}`);
  renderVectorPreview(data.items);
}

function renderVectorPreview(items) {
  const target = $("#vectorPreviewList");
  if (!items.length) {
    target.innerHTML = '<div class="empty">没有可预览的向量数据。</div>';
    return;
  }
  target.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>文本块</th>
          <th>知识库/文档</th>
          <th>模型</th>
          <th>维度</th>
          <th>范数</th>
          <th>相似度</th>
          <th>向量词项预览</th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map(
            (item) => `
              <tr>
                <td>
                  <strong>#${item.chunkIndex + 1}</strong>
                  <p class="cell-snippet">${escapeHtml(item.text)}</p>
                </td>
                <td>${escapeHtml(item.knowledgeBase)}<br /><span class="muted">${escapeHtml(item.document)}</span></td>
                <td>${escapeHtml(item.model)}</td>
                <td>${item.dimension}</td>
                <td>${Number(item.norm || 0).toFixed(2)}</td>
                <td>${Number(item.similarity).toFixed(2)}</td>
                <td>${item.terms.map((term) => `<span class="pill">${escapeHtml(term)}</span>`).join(" ")}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

async function runKbTest() {
  const question = ($("#testQuestion")?.value || "").trim();
  if (!question) {
    $("#kbTestSummary").textContent = "请输入测试问题。";
    return;
  }
  $("#kbTestSummary").textContent = "正在测试检索...";
  const data = await api("/api/kb-test", {
    method: "POST",
    body: JSON.stringify({
      question,
      kbId: $("#testKb")?.value || "",
      topK: Number($("#testLimit")?.value || state.systemConfig.defaultTopK || 6),
      threshold: Number($("#threshold")?.value || state.systemConfig.defaultThreshold || 0.22),
      answerMode: state.systemConfig.answerMode || "enhanced",
      contextMessages: state.currentMessages.slice(-20),
    }),
  });
  renderKbTestResult(data);
}

function renderKbTestResult(data) {
  const hits = data.hits || [];
  const debug = data.debug || {};
  if (data.skipped) {
    $("#kbTestSummary").innerHTML = `
      <strong>无需进入知识库检索</strong>
      <span>原因：${escapeHtml(data.skipReason || debug.status || "当前问题没有明确检索意图")}</span>
      <span>有效问题：${escapeHtml(data.effectiveQuestion || data.question || "")}</span>
    `;
    $("#kbTestResult").innerHTML = '<div class="empty">这类问候或寒暄问题会由对话规则直接处理，不应该用知识库命中结果判断。</div>';
    return;
  }
  $("#kbTestSummary").innerHTML = `
    <strong>${data.matched ? "已命中可靠知识库内容" : "未达到可靠命中"}</strong>
    <span>有效问题：${escapeHtml(data.effectiveQuestion || data.question || "")}</span>
    <span>实际检索：${escapeHtml(data.searchQuery || "")}</span>
    <span>模式：${escapeHtml(modeLabel(data.answerMode))}，可靠阈值：${Number(data.reliableThreshold || 0).toFixed(2)}，最高分：${Number(debug.bestScore || 0).toFixed(2)}</span>
  `;
  if (!hits.length) {
    $("#kbTestResult").innerHTML = '<div class="empty">没有召回文本块。请检查知识库是否选错、文档是否向量化、问题关键词是否过少。</div>';
    return;
  }
  $("#kbTestResult").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>分数</th>
          <th>知识库/文档</th>
          <th>命中文本</th>
        </tr>
      </thead>
      <tbody>
        ${hits
          .map(
            (hit) => `
              <tr>
                <td><strong>${Number(hit.score || 0).toFixed(2)}</strong></td>
                <td>${escapeHtml(hit.knowledgeBase)}<br /><span class="muted">${escapeHtml(hit.document)}</span></td>
                <td><p class="cell-snippet">${escapeHtml(hit.snippet || "")}</p></td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderRebuildResult(data) {
  $("#vectorProgress").value = 100;
  const lines = data.progress
    .map((item) => `${item.percent}% ${item.document}：${item.chunks} 个文本块`)
    .join("\n");
  $("#vectorBuildResult").textContent = `已重建 ${data.documents} 篇文档，生成 ${data.chunks} 个文本块。\n${lines}`;
}

function iconSvg(name) {
  const icons = {
    copy: '<rect x="9" y="9" width="10" height="12" rx="2"></rect><rect x="5" y="3" width="10" height="12" rx="2"></rect>',
    edit: '<path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path>',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || ""}</svg>`;
}

function userMessageActions(index) {
  if (!Number.isInteger(index)) return "";
  return `
    <div class="message-actions">
      <button type="button" class="message-icon-button" data-copy-message="${index}" title="复制对话" aria-label="复制对话">
        ${iconSvg("copy")}
      </button>
      <button type="button" class="message-icon-button" data-edit-message="${index}" title="更新对话" aria-label="更新对话">
        ${iconSvg("edit")}
      </button>
    </div>
  `;
}

function renderUserMessageHtml(content, index) {
  return `
    <div class="user-message-bubble">
      <span class="message-content">${renderMessageHtml(content)}</span>
    </div>
    ${userMessageActions(index)}
  `;
}

function modeLabel(mode) {
  return {
    strict: "严格",
    enhanced: "增强",
    free: "自由",
  }[mode] || mode || "默认";
}

function sourceLabel(value) {
  return {
    knowledge: "知识库",
    free: "自由生成",
    fallback: "兜底话术",
    direct: "直接规则",
    test: "测试检索",
  }[value] || value || "未知";
}

function renderRetrievalDebug(debug) {
  if (!debug) return "";
  const hits = debug.hits || [];
  return `
    <details class="retrieval-debug">
      <summary>命中调试 · ${escapeHtml(sourceLabel(debug.answerSource))} · ${Number(debug.bestScore || 0).toFixed(2)}</summary>
      <div class="debug-grid">
        <span>模式</span><strong>${escapeHtml(modeLabel(debug.answerMode))}</strong>
        <span>有效问题</span><strong>${escapeHtml(debug.effectiveQuestion || "-")}</strong>
        <span>实际检索</span><strong>${escapeHtml(debug.searchQuery || "-")}</strong>
        <span>阈值</span><strong>${Number(debug.reliableThreshold || 0).toFixed(2)}</strong>
        <span>状态</span><strong>${escapeHtml(debug.status || "-")}</strong>
      </div>
      ${
        hits.length
          ? `<div class="debug-hit-list">${hits
              .map(
                (hit) => `
                  <article class="debug-hit">
                    <div><strong>${escapeHtml(hit.knowledgeBase)} / ${escapeHtml(hit.document)}</strong><span>${Number(hit.score || 0).toFixed(2)}</span></div>
                    <p>${escapeHtml(hit.snippet || "")}</p>
                  </article>
                `,
              )
              .join("")}</div>`
          : `<div class="empty mini-empty">没有召回文本块。</div>`
      }
    </details>
  `;
}

function appendRetrievalDebug(node, debug) {
  if (!debug) return;
  const wrapper = document.createElement("div");
  wrapper.innerHTML = renderRetrievalDebug(debug);
  const child = wrapper.firstElementChild;
  if (child) node.append(child);
}

function addMessage(role, content, sources = [], options = {}) {
  hideEmptyQuickPrompts();
  const node = document.createElement("div");
  node.className = `message ${role}`;
  let index = options.index;
  if (options.track) {
    state.currentMessages.push({ role, content: cleanDisplayText(content), sources, debug: options.debug || null });
    index = state.currentMessages.length - 1;
  }
  if (Number.isInteger(index)) {
    node.dataset.messageIndex = String(index);
  }
  const sourceHtml = sources.length
    ? `<div class="source">${sources
        .map((source) => `${escapeHtml(source.document)} / ${Number(source.score).toFixed(2)}`)
        .join(" · ")}</div>`
    : "";
  node.innerHTML =
    role === "user"
      ? renderUserMessageHtml(content, index)
      : `<span class="message-content">${renderMessageHtml(content)}</span>${sourceHtml}${renderRetrievalDebug(options.debug)}`;
  $("#messages").append(node);
  scrollMessagesToBottom();
  return node;
}

function updateLastUserMessage(content) {
  const text = cleanDisplayText(content);
  if (!text) return;
  for (let index = state.currentMessages.length - 1; index >= 0; index -= 1) {
    if (state.currentMessages[index].role === "user") {
      state.currentMessages[index].content = text;
      break;
    }
  }
  const nodes = $$("#messages .message.user");
  const node = nodes[nodes.length - 1];
  if (node) {
    const index = Number(node.dataset.messageIndex);
    node.innerHTML = renderUserMessageHtml(text, Number.isInteger(index) ? index : undefined);
  }
}

function addThinkingMessage() {
  hideEmptyQuickPrompts();
  const node = document.createElement("div");
  node.className = "message assistant thinking-message";
  node.innerHTML = `
    <span class="message-content message-loading" aria-live="polite">
      ${messageLoadingSvg()}
      <span>模型思考中</span>
    </span>
  `;
  $("#messages").append(node);
  scrollMessagesToBottom();
  return node;
}

function removeThinkingMessage(node) {
  if (node?.isConnected) node.remove();
}

function appendSources(node, sources = []) {
  if (!sources.length) return;
  const source = document.createElement("div");
  source.className = "source";
  source.textContent = sources.map((item) => `${item.document} / ${Number(item.score).toFixed(2)}`).join(" · ");
  node.append(source);
}

async function addTypingMessage(content, sources = [], options = {}) {
  hideEmptyQuickPrompts();
  const text = cleanDisplayText(content);
  const node = document.createElement("div");
  node.className = "message assistant typing";
  const contentNode = document.createElement("span");
  contentNode.className = "message-content";
  node.append(contentNode);
  $("#messages").append(node);
  scrollMessagesToBottom();
  for (let index = 1; index <= text.length; index += 1) {
    contentNode.textContent = text.slice(0, index);
    scrollMessagesToBottom();
    const current = text[index - 1];
    const delay = /[。！？\n]/.test(current) ? 70 : /[，；、]/.test(current) ? 35 : 10;
    await new Promise((resolve) => setTimeout(resolve, delay));
  }
  node.classList.remove("typing");
  contentNode.innerHTML = renderMessageHtml(text);
  appendSources(node, sources);
  appendRetrievalDebug(node, options.debug);
  if (options.track) {
    state.currentMessages.push({ role: "assistant", content: text, sources, debug: options.debug || null });
    node.dataset.messageIndex = String(state.currentMessages.length - 1);
  }
  scrollMessagesToBottom();
  return node;
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.append(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function showCopyToast(text) {
  const existing = $(".copy-toast");
  if (existing) existing.remove();
  const toast = document.createElement("div");
  toast.className = "copy-toast";
  toast.innerHTML = `
    <span>已复制提示</span>
    <button type="button">发起新对话</button>
  `;
  document.body.append(toast);
  requestAnimationFrame(() => toast.classList.add("show"));
  const timer = setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 180);
  }, 4000);
  toast.querySelector("button").addEventListener("click", () => {
    clearTimeout(timer);
    toast.remove();
    startNewChatTask();
    sendQuestion(text);
  });
}

function closeMessageEditors() {
  $$(".message-edit-form").forEach((node) => node.remove());
  $$(".message.user.editing").forEach((node) => node.classList.remove("editing"));
}

function openMessageEditor(messageNode, index) {
  const message = state.currentMessages[index];
  if (!message || message.role !== "user") return;
  closeMessageEditors();
  messageNode.classList.add("editing");
  const original = cleanDisplayText(message.content);
  const form = document.createElement("form");
  form.className = "message-edit-form";
  form.innerHTML = `
    <textarea class="message-edit-input" rows="1" aria-label="更新对话内容">${escapeHtml(original)}</textarea>
    <div class="message-edit-actions">
      <button type="button" class="message-edit-cancel">取消</button>
      <button type="submit" class="message-edit-submit" disabled>更新</button>
    </div>
  `;
  messageNode.append(form);
  const input = form.querySelector(".message-edit-input");
  const submit = form.querySelector(".message-edit-submit");
  const resize = () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  };
  const syncSubmit = () => {
    const value = cleanDisplayText(input.value);
    submit.disabled = !value || value === original || state.isAnswering;
  };
  input.addEventListener("input", () => {
    resize();
    syncSubmit();
  });
  form.querySelector(".message-edit-cancel").addEventListener("click", () => {
    form.remove();
    messageNode.classList.remove("editing");
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = cleanDisplayText(input.value);
    if (!value || value === original || state.isAnswering) return;
    form.remove();
    messageNode.classList.remove("editing");
    await sendQuestion(value);
  });
  input.focus();
  input.select();
  resize();
  syncSubmit();
  scrollMessagesToBottom();
}

async function logoutCurrentUser() {
  if (state.token) {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
  }
  state.token = "";
  state.user = null;
  localStorage.removeItem("authToken");
  updateCurrentUser();
  applyPermissions();
  addMessage("assistant", "已退出登录，可以浏览对话记录。如需发送对话，请先登录。");
}

function setSendButtonBusy(isBusy) {
  state.isAnswering = isBusy;
  const button = $(".send-button");
  if (!button) return;
  button.classList.toggle("is-sending", isBusy);
  button.disabled = isBusy;
  button.title = isBusy ? "正在生成" : "发送";
  button.setAttribute("aria-label", isBusy ? "正在生成" : "发送");
}

async function sendQuestion(question) {
  if (state.isAnswering) return;
  if (!state.token) {
    if (confirm("您尚未登录，是否前往登录页面？")) {
      window.location.href = "/static/login.html";
    }
    return;
  }
  closeMessageEditors();
  removeFollowupPrompts();
  hideEmptyQuickPrompts();
  addMessage("user", question, [], { track: true });
  const payload = {
    question,
    conversationId: state.conversationId,
    contextMessages: state.currentMessages.slice(-20),
    kbId: $("#globalKb").value,
    topK: Number($("#topK").value || state.systemConfig.defaultTopK || 6),
    threshold: Number($("#threshold").value || state.systemConfig.defaultThreshold || 0.22),
    answerMode: state.systemConfig.answerMode || "enhanced",
  };
  const thinkingNode = addThinkingMessage();
  setSendButtonBusy(true);
  try {
    const data = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    removeThinkingMessage(thinkingNode);
    if (data.question && data.question !== question) {
      updateLastUserMessage(data.question);
    }
    state.conversationId = data.conversationId;
    localStorage.setItem("conversationId", state.conversationId);
    const assistantNode = await addTypingMessage(data.answer, data.sources, { track: true, debug: data.debug });
    renderFollowupPrompts(assistantNode, question, data.answer);
    persistChatExchange(question, data.answer, data.sources);
  } catch (error) {
    removeThinkingMessage(thinkingNode);
    addMessage("assistant", error.message);
  } finally {
    setSendButtonBusy(false);
  }
}

async function loadLogs() {
  state.logs = await api("/api/logs");
  renderLogs();
}

function renderLogs() {
  const target = $("#logList");
  const keyword = ($("#logSearch")?.value || "").trim().toLowerCase();
  const rows = state.logs.filter((row) => {
    if (!keyword) return true;
    return [
      row.display_name,
      row.username,
      row.question,
      row.answer,
      row.kb_name,
      row.conversation_id,
    ]
      .map((item) => String(item || "").toLowerCase())
      .some((value) => value.includes(keyword));
  });
  if (!rows.length) {
    target.innerHTML = `<div class="empty">${state.logs.length ? "没有匹配的对话日志。" : "还没有对话日志。"}</div>`;
    return;
  }
  const groups = rows.reduce((map, row) => {
    const key = row.user_id || "legacy";
    if (!map.has(key)) {
      map.set(key, {
        id: key,
        name: row.display_name || row.username || "未归属账号",
        username: row.username || "",
        rows: [],
      });
    }
    map.get(key).rows.push(row);
    return map;
  }, new Map());
  target.innerHTML = Array.from(groups.values())
    .map(
      (group) => {
        const collapsed = state.collapsedLogAccounts.has(group.id);
        return `
          <section class="log-account-group ${collapsed ? "collapsed" : ""}">
            <button type="button" class="log-account-head" data-log-account="${escapeHtml(group.id)}" aria-expanded="${String(!collapsed)}">
              <span class="log-account-title">
                <span class="log-chevron"></span>
                <strong>${escapeHtml(group.name)}</strong>
              </span>
              <span>${group.username ? escapeHtml(group.username) : "历史日志"} · ${group.rows.length} 条</span>
            </button>
            <div class="log-account-body">
              <table>
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>问题</th>
                    <th>答案</th>
                    <th>知识库</th>
                    <th>相似度</th>
                    <th>耗时</th>
                  </tr>
                </thead>
                <tbody>
                  ${group.rows
                    .map(
                      (row) => `
                        <tr>
                          <td>${formatTime(row.created_at)}</td>
                          <td>${escapeHtml(row.question)}</td>
                          <td>${escapeHtml(row.answer.slice(0, 120))}</td>
                          <td>${escapeHtml(row.kb_name || "全部")}</td>
                          <td>${Number(row.score).toFixed(2)}</td>
                          <td>${row.latency_ms} ms</td>
                        </tr>
                      `,
                    )
                    .join("")}
                </tbody>
              </table>
            </div>
          </section>
        `;
      },
    )
    .join("");
}

function toggleLogAccount(id) {
  if (state.collapsedLogAccounts.has(id)) {
    state.collapsedLogAccounts.delete(id);
  } else {
    state.collapsedLogAccounts.add(id);
  }
  renderLogs();
}

async function openDocumentPreview(docId) {
  state.currentDocId = docId;
  const keyword = $("#chunkSearch")?.value || "";
  const data = await api(`/api/documents/${docId}/preview?q=${encodeURIComponent(keyword)}`);
  $("#docDialogTitle").textContent = `文档预览：${data.document.name}`;
  $("#docEditor").value = data.original;
  renderChunks(data.chunks);
  $("#docDialog").showModal();
}

function renderChunks(chunks) {
  const target = $("#chunkPreview");
  if (!chunks.length) {
    target.innerHTML = '<div class="empty">没有匹配的文本块。</div>';
    return;
  }
  target.innerHTML = chunks
    .map(
      (chunk) => `
        <article class="chunk-item">
          <strong>#${chunk.chunk_index + 1}</strong>
          <p>${escapeHtml(chunk.text)}</p>
        </article>
      `,
    )
    .join("");
}

function bindEvents() {
  $$(".nav-item").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.classList.contains("hidden")) return;
      activateView(button.dataset.view);
      if (button.dataset.view === "logs") {
        await loadLogs();
      } else if (button.dataset.view === "vectors") {
        await loadVectorPreview();
      } else if (button.dataset.view === "system") {
        await loadModels();
        await loadSystemConfig();
      } else if (button.dataset.view === "access") {
        await loadAccessData();
      }
    });
  });

  $("#authSwitch").addEventListener("click", (event) => {
    const button = event.target.closest("[data-auth-mode]");
    if (!button) return;
    showAuth(button.dataset.authMode);
  });

  $("#authForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = Object.fromEntries(form.entries());
    payload.remember = formElement.elements.remember.checked;
    const endpoint =
      state.authMode === "setup"
        ? "/api/auth/setup"
        : state.authMode === "register"
          ? "/api/auth/register"
          : "/api/auth/login";
    const data = await api(endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("authToken", state.token);
    updateCurrentUser();
    applyPermissions();
    const restoredHistory = setupChatHistoryPanel();
    hideAuth();
    formElement.reset();
    if (can("kb:read")) {
      await loadModels();
    }
    if (can("system:manage")) {
      await loadSystemConfig();
    }
    if (can("kb:read")) {
      await loadKbs();
    }
    if (isChatOnlyUser() && !restoredHistory) {
      $("#messages").innerHTML = "";
      state.currentMessages = [];
      renderEmptyQuickPrompts();
    } else if (!isChatOnlyUser()) {
      addMessage("assistant", state.authMode === "register" ? "注册成功，可以开始咨询。" : "登录成功，可以开始使用系统。");
    }
  });


  $("#logoutBtn").addEventListener("click", logoutCurrentUser);
  $("#chatUserMenuBtn").addEventListener("click", (event) => {
    event.stopPropagation();
    toggleChatUserMenu();
  });
  $("#chatUserMenu").addEventListener("click", async (event) => {
    const item = event.target.closest("[data-user-menu-action]");
    if (!item) return;
    const action = item.dataset.userMenuAction;
    closeChatUserMenu();
    if (action === "logout") {
      await logoutCurrentUser();
    } else if (action === "switch") {
      await logoutCurrentUser();
      window.location.href = "/static/login.html";
    } else if (action === "settings") {
      openProfileDialog();
    } else if (action === "favorites") {
      addMessage("assistant", "收藏夹功能已预留，后续可接入常用问题或收藏对话。", [], { track: false });
    }
  });
  $("#profileAvatarInput").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      addMessage("assistant", "请选择图片文件作为头像。", [], { track: false });
      event.target.value = "";
      return;
    }
    if (file.size > 512 * 1024) {
      addMessage("assistant", "头像图片请控制在 500KB 以内。", [], { track: false });
      event.target.value = "";
      return;
    }
    state.pendingAvatarData = await readAvatarFile(file);
    const name = $("#profileForm").elements.displayName.value || displayUserName();
    renderAvatar($("#profileAvatarPreview"), name, state.pendingAvatarData);
  });
  $("#removeProfileAvatar").addEventListener("click", () => {
    state.pendingAvatarData = "";
    const name = $("#profileForm").elements.displayName.value || displayUserName();
    renderAvatar($("#profileAvatarPreview"), name, "");
    $("#profileAvatarInput").value = "";
  });
  $("#closeProfileDialog").addEventListener("click", () => {
    $("#profileDialog").close();
  });
  $("#profileForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const displayName = form.elements.displayName.value.trim();
    const data = await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({
        displayName,
        avatarData: state.pendingAvatarData || "",
      }),
    });
    state.user = data.user;
    updateCurrentUser();
    $("#profileDialog").close();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".chat-history-user")) closeChatUserMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeChatUserMenu();
  });
  $("#chatForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("#question");
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    input.style.height = "";
    await sendQuestion(question);
  });

  $("#question").addEventListener("input", (event) => {
    const input = event.currentTarget;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  });

  $("#question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("#chatForm").requestSubmit();
    }
  });
  $("#modalInput").addEventListener("change", (event) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    addMessage("assistant", `已选择“${file.name}”。当前演示版暂未接入 OCR 图片识别或 ASR 语音转文字，请先把图片/语音内容转成文字后再提问。`, [], { track: false });
    event.currentTarget.value = "";
  });
  $(".voice-button")?.addEventListener("click", () => {
    addMessage("assistant", "语音输入入口已保留，当前演示版暂未接入语音识别。", [], { track: false });
  });

  $("#newChatTask").addEventListener("click", startNewChatTask);
  $("#chatHistorySearch").addEventListener("input", renderChatHistories);
  $("#chatHistoryList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-history-id]");
    if (button) loadChatHistory(button.dataset.historyId);
  });
  $("#messages").addEventListener("click", (event) => {
    const copyButton = event.target.closest("[data-copy-message]");
    if (copyButton) {
      const index = Number(copyButton.dataset.copyMessage);
      const text = state.currentMessages[index]?.content || "";
      if (text) {
        copyTextToClipboard(text).then(() => {
          showCopyToast(text);
        });
      }
      return;
    }
    const editButton = event.target.closest("[data-edit-message]");
    if (editButton) {
      const index = Number(editButton.dataset.editMessage);
      const messageNode = editButton.closest(".message.user");
      if (messageNode) openMessageEditor(messageNode, index);
      return;
    }
    const prompt = event.target.closest("[data-quick-question]");
    if (prompt) sendQuestion(prompt.dataset.quickQuestion);
  });

  $$(".quick-list button").forEach((button) => {
    button.addEventListener("click", () => sendQuestion(button.dataset.question));
  });

  $("#emptyQuickPrompts").addEventListener("click", (event) => {
    const button = event.target.closest("[data-quick-question]");
    if (button) sendQuestion(button.dataset.quickQuestion);
  });
  $("#logSearch").addEventListener("input", renderLogs);
  $("#logList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-log-account]");
    if (button) toggleLogAccount(button.dataset.logAccount);
  });

  $("#clearChat").addEventListener("click", () => {
    state.conversationId = "";
    state.currentMessages = [];
    localStorage.removeItem("conversationId");
    $("#messages").innerHTML = "";
    renderEmptyQuickPrompts();
    renderChatHistories();
  });

  $("#kbForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    await api("/api/kbs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(form.entries())),
    });
    formElement.reset();
    await loadKbs();
  });

  $("#uploadForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const kbId = $("#uploadKb").value;
    const files = Array.from($("#file").files);
    if (!kbId || !files.length) return;
    $("#uploadProgress").value = 0;
    for (let index = 0; index < files.length; index += 1) {
      const data = new FormData();
      data.append("file", files[index]);
      data.append("chunkSize", $("#chunkSize").value || state.systemConfig.chunkSize || 400);
      data.append("chunkOverlap", $("#chunkOverlap").value || state.systemConfig.chunkOverlap || 50);
      await api(`/api/kbs/${kbId}/documents`, { method: "POST", body: data });
      $("#uploadProgress").value = Math.round(((index + 1) / files.length) * 100);
    }
    $("#file").value = "";
    await loadKbs({ resetGlobal: true });
  });

  $("#refreshKbs").addEventListener("click", loadKbs);
  $("#kbSearch").addEventListener("input", loadKbs);
  $("#kbDepartment").addEventListener("input", loadKbs);
  $("#kbSort").addEventListener("change", loadKbs);
  $("#refreshLogs").addEventListener("click", loadLogs);
  $("#docSearch").addEventListener("input", loadDocuments);
  $("#docSort").addEventListener("change", loadDocuments);
  $("#previewVectors").addEventListener("click", loadVectorPreview);
  $("#vectorSearch").addEventListener("input", loadVectorPreview);
  $("#vectorKb").addEventListener("change", loadVectorPreview);
  $("#runKbTest").addEventListener("click", runKbTest);
  $("#testQuestion").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runKbTest();
    }
  });
  $("#clearVectorSearch").addEventListener("click", async () => {
    $("#vectorSearch").value = "";
    await loadVectorPreview();
  });
  $("#rebuildVectors").addEventListener("click", async () => {
    $("#vectorProgress").value = 5;
    $("#vectorBuildResult").textContent = "正在重新生成向量...";
    const data = await api("/api/vectors/rebuild", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kbId: $("#vectorKb").value,
        chunkSize: Number($("#vectorChunkSize").value || 400),
        chunkOverlap: Number($("#vectorChunkOverlap").value || 50),
      }),
    });
    renderRebuildResult(data);
    await loadKbs();
    await loadVectorPreview();
  });
  $("#normalizeVectors").addEventListener("click", async () => {
    $("#normalizeResult").textContent = "正在归一化向量...";
    const data = await api("/api/vectors/normalize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kbId: $("#vectorKb").value }),
    });
    $("#normalizeResult").textContent = `已归一化 ${data.chunks} 个文本块，平均范数 ${Number(data.averageNorm).toFixed(2)}。`;
    await loadVectorPreview();
  });
  $("#deduplicateVectors").addEventListener("click", async () => {
    if (!confirm("确认删除重复文本块的向量索引？原始上传文档不会被删除。")) return;
    const data = await api("/api/vectors/deduplicate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kbId: $("#vectorKb").value,
        threshold: Number($("#dedupeThreshold").value || 0.92),
      }),
    });
    $("#dedupeResult").textContent = `已删除 ${data.removed} 个重复向量，阈值 ${Number(data.threshold).toFixed(2)}。`;
    await loadKbs();
    await loadVectorPreview();
  });
  $("#reloadPreview").addEventListener("click", () => openDocumentPreview(state.currentDocId));
  $("#saveDocEdit").addEventListener("click", async () => {
    if (!state.currentDocId) return;
    await api(`/api/documents/${state.currentDocId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: $("#docEditor").value,
        chunkSize: Number($("#chunkSize").value || 400),
        chunkOverlap: Number($("#chunkOverlap").value || 50),
      }),
    });
    await openDocumentPreview(state.currentDocId);
    await loadKbs();
  });
  $("#batchDeleteDocs").addEventListener("click", async () => {
    const ids = $$("[data-doc-check]:checked").map((item) => item.dataset.docCheck);
    if (!ids.length) return;
    if (!confirm(`确认批量删除 ${ids.length} 篇文档及其向量索引？`)) return;
    await api("/api/documents/batch-delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    await loadKbs();
  });
  $("#saveKbEdit").addEventListener("click", async () => {
    if (!state.currentKbId) return;
    await api(`/api/kbs/${state.currentKbId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: $("#editKbName").value,
        department: $("#editKbDepartment").value,
        owner: $("#editKbOwner").value,
        category: $("#editKbCategory").value,
        embeddingModel: $("#editKbEmbedding").value,
        description: $("#editKbDescription").value,
      }),
    });
    $("#kbDialog").close();
    await loadKbs();
  });
  $("#refreshModels").addEventListener("click", loadModels);
  $("#modelForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = Object.fromEntries(form.entries());
    payload.isDefault = formElement.elements.isDefault.checked;
    await api("/api/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    formElement.reset();
    await loadModels();
  });
  $("#saveSystemConfig").addEventListener("click", async () => {
    const formElement = $("#systemForm");
    const form = new FormData(formElement);
    const payload = Object.fromEntries(form.entries());
    payload.llmEnabled = Boolean(formElement.elements.llmEnabled.checked);
    const data = await api("/api/system/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.systemConfig = data;
    await loadSystemConfig();
    $("#systemConfigResult").textContent = "配置已保存，并会用于后续上传、编辑和重建。";
  });
  $("#refreshOllamaModels").addEventListener("click", loadOllamaModels);
  $("#llmProviderSelect").addEventListener("change", syncLlmProviderFields);
  $("#sensitiveWordsFile").addEventListener("change", async (event) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    const isTxt = file.name.toLowerCase().endsWith(".txt") || file.type === "text/plain";
    if (!isTxt) {
      $("#systemConfigResult").textContent = "请上传 txt 格式的违禁词文件。";
      event.currentTarget.value = "";
      return;
    }
    if (file.size > 1024 * 1024) {
      $("#systemConfigResult").textContent = "违禁词文件请控制在 1MB 以内。";
      event.currentTarget.value = "";
      return;
    }
    const imported = await readTextFile(file);
    const field = $("#systemForm").elements.sensitiveWords;
    field.value = mergeRuleTerms(field.value, imported);
    $("#systemConfigResult").textContent = `已导入“${file.name}”，请点击保存配置生效。`;
    event.currentTarget.value = "";
  });
  $("#refreshUsers").addEventListener("click", loadAccessData);
  $("#refreshRoles").addEventListener("click", loadAccessData);
  $("#resetUserForm").addEventListener("click", resetUserForm);
  $("#resetRoleForm").addEventListener("click", resetRoleForm);
  $("#userForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const selectedKbs = Array.from(formElement.elements.allowedKbIds.selectedOptions).map((item) => item.value);
    const payload = Object.fromEntries(form.entries());
    payload.allowedKbIds = selectedKbs;
    payload.failedAttempts = Number(payload.failedAttempts || 0);
    const url = state.editingUserId ? `/api/users/${state.editingUserId}` : "/api/users";
    const method = state.editingUserId ? "PUT" : "POST";
    await api(url, { method, body: JSON.stringify(payload) });
    resetUserForm();
    await loadAccessData();
  });
  $("#roleForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const permissions = Array.from($("#permissionList").querySelectorAll("input:checked")).map((item) => item.value);
    const payload = Object.fromEntries(new FormData(formElement).entries());
    payload.permissions = permissions;
    const url = state.editingRoleId ? `/api/roles/${state.editingRoleId}` : "/api/roles";
    const method = state.editingRoleId ? "PUT" : "POST";
    await api(url, { method, body: JSON.stringify(payload) });
    resetRoleForm();
    await loadAccessData();
  });

  document.addEventListener("click", async (event) => {
    const editUserButton = event.target.closest("[data-edit-user]");
    if (editUserButton) {
      const user = state.users.find((item) => item.id === editUserButton.dataset.editUser);
      if (!user) return;
      state.editingUserId = user.id;
      const form = $("#userForm");
      form.elements.username.value = user.username;
      form.elements.password.value = "";
      form.elements.email.value = user.email || "";
      form.elements.department.value = user.department || "";
      form.elements.roleId.value = user.roleId;
      form.elements.status.value = user.status;
      form.elements.failedAttempts.value = user.failedAttempts || 0;
      Array.from(form.elements.allowedKbIds.options).forEach((option) => {
        option.selected = user.allowedKbIds.includes(option.value);
      });
      return;
    }

    const deleteUserButton = event.target.closest("[data-delete-user]");
    if (deleteUserButton) {
      if (!confirm("确认删除这个用户？")) return;
      await api(`/api/users/${deleteUserButton.dataset.deleteUser}`, { method: "DELETE" });
      await loadAccessData();
      return;
    }

    const editRoleButton = event.target.closest("[data-edit-role]");
    if (editRoleButton) {
      const role = state.roles.find((item) => item.id === editRoleButton.dataset.editRole);
      if (!role) return;
      state.editingRoleId = role.id;
      const form = $("#roleForm");
      form.elements.name.value = role.name;
      form.elements.description.value = role.description || "";
      renderPermissionList(role.permissions);
      return;
    }

    const deleteRoleButton = event.target.closest("[data-delete-role]");
    if (deleteRoleButton) {
      if (!confirm("确认删除这个角色？")) return;
      await api(`/api/roles/${deleteRoleButton.dataset.deleteRole}`, { method: "DELETE" });
      await loadAccessData();
      return;
    }

    const defaultModelButton = event.target.closest("[data-default-model]");
    if (defaultModelButton) {
      await api(`/api/models/${defaultModelButton.dataset.defaultModel}/default`, { method: "POST" });
      await loadModels();
      return;
    }

    const editKbButton = event.target.closest("[data-edit-kb]");
    if (editKbButton) {
      openKbEditor(editKbButton.dataset.editKb);
      return;
    }

    const cloneKbButton = event.target.closest("[data-clone-kb]");
    if (cloneKbButton) {
      const sourceName = cloneKbButton.dataset.kbName || "知识库";
      const name = prompt("请输入克隆后的知识库名称", `${sourceName} 副本`);
      if (!name) return;
      await api(`/api/kbs/${cloneKbButton.dataset.cloneKb}/clone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      await loadKbs();
      return;
    }

    const previewButton = event.target.closest("[data-preview-doc]");
    if (previewButton) {
      $("#chunkSearch").value = "";
      await openDocumentPreview(previewButton.dataset.previewDoc);
      return;
    }

    const docButton = event.target.closest("[data-delete-doc]");
    if (docButton) {
      if (!confirm("确认删除这篇文档及其向量索引？")) return;
      await api(`/api/documents/${docButton.dataset.deleteDoc}`, { method: "DELETE" });
      await loadKbs();
      return;
    }

    const kbButton = event.target.closest("[data-delete-kb]");
    if (kbButton) {
      const name = kbButton.dataset.kbName || "该知识库";
      const mode = kbButton.dataset.deleteMode || "logical";
      const label = mode === "physical" ? "物理删除，会同时删除文档和向量数据" : "逻辑删除，会从列表中隐藏";
      if (!confirm(`确认${label}“${name}”？`)) return;
      await api(`/api/kbs/${kbButton.dataset.deleteKb}?mode=${mode}`, { method: "DELETE" });
      await loadKbs();
    }
  });
}

async function start() {
  bindEvents();
  const authenticated = await ensureAuth();
  if (!authenticated) {
    updateCurrentUser();
    applyPermissions();
    finishAuthLoading();
    return;
  }
  const restoredHistory = setupChatHistoryPanel();
  finishAuthLoading();
  if (can("kb:read")) {
    await loadModels();
  }
  if (can("system:manage")) {
    await loadSystemConfig();
  }
  if (can("kb:read")) {
    await loadKbs();
  }
  if (!restoredHistory) {
    renderEmptyQuickPrompts();
  }
}

start().catch((error) => {
  finishAuthLoading();
  document.body.innerHTML = `<main><div class="panel"><h1>启动失败</h1><p>${escapeHtml(error.message)}</p></div></main>`;
});
