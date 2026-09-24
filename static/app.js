const form = document.querySelector('#observation-form');
const input = document.querySelector('#observation');
const count = document.querySelector('#char-count');
const button = document.querySelector('#analyze-button');
const progress = document.querySelector('#progress');
const errorPanel = document.querySelector('#error-panel');
const results = document.querySelector('#results');
const configStatus = document.querySelector('#config-status');
const folderStatus = document.querySelector('#folder-status');
const provider = document.querySelector('#model-provider');
const apiKey = document.querySelector('#api-key');
const baseUrl = document.querySelector('#base-url');
const modelName = document.querySelector('#model-name');
const pageModelFields = document.querySelector('#page-model-fields');
const chooseFolderButton = document.querySelector('#choose-folder');
const newChatButton = document.querySelector('#new-chat');
const conversationSection = document.querySelector('#conversation');
const CHAT_FORMAT = 'onesentencescience-chat';
const CHAT_VERSION = 1;
const CHAT_PREFIX = 'OneSentenceScience-';

let serverConfigured = false;
let directoryHandle = null;
let serverFolderName = null;
let currentConversation = null;
let analyzing = false;
const conversations = new Map();

const verdictLabels = {
  initial_support: '有初步支持',
  mixed: '结果不一致',
  insufficient: '证据不足',
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function safeSourceUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:') return null;
    if (url.hostname === 'doi.org' || url.hostname === 'openalex.org') return url.href;
  } catch (_) { /* Ignore malformed links from external data. */ }
  return null;
}

function makeLink(source, label) {
  const url = safeSourceUrl(source.url) || safeSourceUrl(source.openalex_url);
  if (!url) return element('span', 'source-ref', label);
  const link = element('a', 'source-ref', label);
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.title = source.title;
  return link;
}

function renderClaims(claims, sources) {
  const container = document.querySelector('#claims');
  container.replaceChildren();
  if (!claims.length) {
    container.append(element('p', 'empty-note', '这次没有足够直接的摘要证据来支持一个结论。'));
    return;
  }
  const sourceMap = new Map(sources.map(source => [source.id, source]));
  for (const claim of claims) {
    const card = element('div', 'claim');
    card.append(element('p', 'claim-text', claim.text));
    const refs = element('div', 'claim-refs');
    for (const id of claim.source_ids) {
      const source = sourceMap.get(id);
      if (source) refs.append(makeLink(source, id + ' ↗'));
    }
    card.append(refs);
    container.append(card);
  }
}

function renderCaveats(result) {
  const container = document.querySelector('#caveats');
  container.replaceChildren();
  const entries = [
    ...result.other_explanations.map(text => ['其他可能的解释', text]),
    ...result.limitations.map(text => ['研究局限', text]),
  ];
  if (!entries.length) entries.push(['研究局限', '仍需阅读全文、核对研究方法。']);
  for (const [label, text] of entries) {
    const item = element('div', 'caveat-item');
    item.append(element('span', 'caveat-label', label));
    item.append(element('p', '', text));
    container.append(item);
  }
}

function renderSources(sources) {
  const container = document.querySelector('#sources-list');
  container.replaceChildren();
  document.querySelector('#sources-count').textContent = `${sources.length} 篇论文`;
  if (!sources.length) {
    container.append(element('p', 'empty-note', '这次没有找到可用于分析的相关论文摘要。'));
    return;
  }
  for (const source of sources) {
    const item = element('div', 'source-item');
    item.append(element('span', 'source-id', source.id));
    const copy = element('div', 'source-copy');
    const url = safeSourceUrl(source.url) || safeSourceUrl(source.openalex_url);
    const title = url ? makeLink(source, source.title) : element('span', '', source.title);
    title.className = 'source-title';
    copy.append(title);
    copy.append(element('span', 'source-meta', source.year ? `${source.year} · OpenAlex 收录` : 'OpenAlex 收录'));
    item.append(copy);
    container.append(item);
  }
}

function renderResult(data) {
  document.querySelector('#phenomenon').textContent = data.phenomenon;
  document.querySelector('#research-question').textContent = data.research_question;
  document.querySelector('#conclusion').textContent = data.result.conclusion;
  document.querySelector('#method-note').textContent = data.method_note;
  const badge = document.querySelector('#verdict-badge');
  badge.textContent = verdictLabels[data.result.verdict] || '证据不足';
  badge.dataset.verdict = data.result.verdict;
  renderClaims(data.result.claims || [], data.sources || []);
  renderCaveats(data.result);
  renderSources(data.sources || []);
  document.querySelector('#next-step').textContent = `下一步 · ${data.result.next_step}`;
  results.hidden = false;
  results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function updateConfigStatus() {
  pageModelFields.hidden = provider.value === 'server';
  baseUrl.readOnly = provider.value === 'openai';
  if (provider.value === 'server') {
    configStatus.textContent = serverConfigured
      ? '本机环境变量已配置 · 可以开始探索。'
      : '本机环境变量尚未配置，请改用页面设置或参照 README。';
    configStatus.dataset.state = serverConfigured ? 'ready' : 'setup';
  } else if (provider.value === 'openai' && !apiKey.value.trim()) {
    configStatus.textContent = '填入 OpenAI API 密钥后即可开始探索。';
    configStatus.dataset.state = 'setup';
  } else if (!baseUrl.value.trim() || !modelName.value.trim()) {
    configStatus.textContent = '请填写兼容接口地址和模型名称。';
    configStatus.dataset.state = 'setup';
  } else {
    configStatus.textContent = '模型设置已填写 · 点击“开始探索”后连接服务。';
    configStatus.dataset.state = 'ready';
  }
}

function modelConfig() {
  if (provider.value === 'server') {
    if (!serverConfigured) throw new Error('本机环境变量尚未配置。');
    return null;
  }
  if (provider.value === 'openai' && !apiKey.value.trim()) {
    throw new Error('请先填写 OpenAI API 密钥。');
  }
  if (!baseUrl.value.trim() || !modelName.value.trim()) {
    throw new Error('请填写模型接口地址和模型名称。');
  }
  return { base_url: provider.value === 'openai'
    ? 'https://api.openai.com/v1' : baseUrl.value.trim(), model: modelName.value.trim(),
    api_key: apiKey.value.trim() };
}

async function checkConfig() {
  try {
    const response = await fetch('/api/health');
    const data = await response.json();
    serverConfigured = Boolean(data.configured);
    updateConfigStatus();
  } catch (_) {
    configStatus.textContent = '暂时无法连接本地服务，请刷新页面。';
    configStatus.dataset.state = 'setup';
  }
}

function setFolderStatus(message, isError = false) {
  folderStatus.textContent = message;
  folderStatus.dataset.state = isError ? 'error' : 'ready';
}

function newConversation(observation) {
  const now = new Date().toISOString();
  const id = crypto.randomUUID();
  return { id, fileName: `${CHAT_PREFIX}${id}.json`,
    title: observation.slice(0, 60), created_at: now, updated_at: now, turns: [] };
}

function shortString(value, max) {
  return typeof value === 'string' ? value.slice(0, max) : '';
}

function publicReport(raw) {
  const result = raw.result;
  return {
    observation: shortString(raw.observation, 500),
    phenomenon: shortString(raw.phenomenon, 220),
    research_question: shortString(raw.research_question, 220),
    search_queries: (Array.isArray(raw.search_queries) ? raw.search_queries : [])
      .slice(0, 2).map(q => shortString(q, 90)),
    result: {
      verdict: ['initial_support', 'mixed', 'insufficient'].includes(result.verdict)
        ? result.verdict : 'insufficient',
      conclusion: shortString(result.conclusion, 420),
      claims: result.claims.slice(0, 3).map(claim => ({
        text: shortString(claim.text, 360),
        source_ids: claim.source_ids.slice(0, 7).map(id => shortString(id, 12)),
      })),
      other_explanations: result.other_explanations.slice(0, 3)
        .map(text => shortString(text, 220)),
      limitations: result.limitations.slice(0, 3).map(text => shortString(text, 220)),
      next_step: shortString(result.next_step, 300),
    },
    sources: raw.sources.slice(0, 7).map(source => ({
      id: shortString(source.id, 12), title: shortString(source.title, 240),
      year: Number.isInteger(source.year) ? source.year : null,
      url: shortString(source.url, 500),
      openalex_url: shortString(source.openalex_url, 500),
    })),
    method_note: shortString(raw.method_note, 500),
  };
}

function conversationData(chat) {
  return { format: CHAT_FORMAT, version: CHAT_VERSION, id: chat.id,
    title: chat.title, created_at: chat.created_at, updated_at: chat.updated_at,
    turns: chat.turns.map(turn => ({ observation: turn.observation,
      created_at: turn.created_at, report: publicReport(turn.report) })) };
}

function parseConversation(raw, fileName) {
  if (!raw || raw.format !== CHAT_FORMAT || raw.version !== CHAT_VERSION ||
      !Array.isArray(raw.turns) || raw.turns.length > 100 ||
      typeof raw.id !== 'string' || typeof raw.title !== 'string') return null;
  const turns = [];
  for (const turn of raw.turns) {
    const report = turn && turn.report;
    if (!turn || typeof turn.observation !== 'string' || !report ||
        typeof report.phenomenon !== 'string' ||
        typeof report.research_question !== 'string' ||
        !report.result || typeof report.result.conclusion !== 'string' ||
        typeof report.result.next_step !== 'string' ||
        !Array.isArray(report.result.claims) ||
        !Array.isArray(report.result.other_explanations) ||
        !Array.isArray(report.result.limitations) ||
        !Array.isArray(report.sources) ||
        !report.sources.every(source => source &&
          typeof source.id === 'string' && typeof source.title === 'string') ||
        !report.result.claims.every(claim => claim &&
          typeof claim.text === 'string' && Array.isArray(claim.source_ids))) return null;
    turns.push({ observation: turn.observation.slice(0, 500),
      created_at: String(turn.created_at || ''), report: publicReport(report) });
  }
  return { id: raw.id.slice(0, 100), fileName,
    title: raw.title.slice(0, 60),
    created_at: String(raw.created_at || ''),
    updated_at: String(raw.updated_at || ''), turns };
}

function renderChatList() {
  const list = document.querySelector('#chat-list');
  list.replaceChildren();
  const chats = [...conversations.values()].filter(chat =>
    (chat.turns?.length || chat.turn_count || 0) > 0)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  if (!chats.length) {
    list.append(element('p', 'empty-note', '还没有聊天记录。'));
    return;
  }
  for (const chat of chats) {
    const item = element('button', 'chat-item');
    item.type = 'button';
    item.disabled = analyzing;
    item.setAttribute('aria-current', String(currentConversation?.id === chat.id));
    item.append(element('span', 'chat-item-title', chat.title || '未命名聊天'));
    item.append(element('span', 'chat-item-meta',
      `${chat.turns?.length || chat.turn_count} 轮`));
    item.addEventListener('click', () => openConversation(chat));
    list.append(item);
  }
}

function renderConversation() {
  const chat = currentConversation;
  conversationSection.hidden = !chat || !Array.isArray(chat.turns) || !chat.turns.length;
  const list = document.querySelector('#turn-list');
  list.replaceChildren();
  if (!chat || !Array.isArray(chat.turns) || !chat.turns.length) return;
  document.querySelector('#conversation-title').textContent = chat.title || '探索记录';
  for (const turn of chat.turns) {
    const card = element('article', 'turn-card');
    const copy = element('div');
    copy.append(element('p', 'turn-observation', turn.observation));
    copy.append(element('p', 'turn-conclusion', turn.report.result.conclusion));
    const view = element('button', '', '查看完整结果 ↗');
    view.type = 'button';
    view.addEventListener('click', () => renderResult(turn.report));
    card.append(copy, view);
    list.append(card);
  }
}

async function openConversation(chat) {
  if (analyzing) return;
  if (!Array.isArray(chat.turns)) {
    try {
      const response = await fetch(`/api/storage/chat/${encodeURIComponent(chat.id)}`,
        { headers: { 'X-OneSentenceScience': '1' } });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '无法读取聊天文件。');
      chat = parseConversation(data, `${CHAT_PREFIX}${chat.id}.json`);
      if (!chat) throw new Error('聊天文件格式不正确。');
      conversations.set(chat.id, chat);
    } catch (error) {
      setFolderStatus(`读取聊天失败：${error.message || '请重试。'}`, true);
      return;
    }
  }
  currentConversation = chat;
  input.value = '';
  input.dispatchEvent(new Event('input'));
  errorPanel.hidden = true;
  renderChatList();
  renderConversation();
  if (chat.turns.length) renderResult(chat.turns.at(-1).report);
  input.focus();
}

async function saveConversation(chat) {
  if (directoryHandle) {
    const handle = await directoryHandle.getFileHandle(chat.fileName, { create: true });
    const writer = await handle.createWritable();
    await writer.write(JSON.stringify(conversationData(chat), null, 2));
    await writer.close();
    return true;
  }
  if (serverFolderName) {
    const response = await fetch('/api/storage/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-OneSentenceScience': '1' },
      body: JSON.stringify(conversationData(chat)),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '无法保存聊天文件。');
    return true;
  }
  return false;
}

function loadServerChatList(data) {
  directoryHandle = null;
  serverFolderName = data.folder_name;
  conversations.clear();
  currentConversation = null;
  for (const chat of data.chats || []) {
    if (typeof chat.id !== 'string' || typeof chat.title !== 'string') continue;
    conversations.set(chat.id, { ...chat, turns: null,
      fileName: `${CHAT_PREFIX}${chat.id}.json` });
  }
  renderChatList();
  renderConversation();
  results.hidden = true;
}

async function checkStorage() {
  try {
    const response = await fetch('/api/storage',
      { headers: { 'X-OneSentenceScience': '1' } });
    const data = await response.json();
    if (response.ok && data.selected && !directoryHandle && !currentConversation) {
      loadServerChatList(data);
      setFolderStatus(`已打开文件夹“${data.folder_name}” · 找到 ${data.chats.length} 个聊天记录。`);
    }
  } catch (_) { /* Folder selection remains available. */ }
}

async function loadFolderChats(handle) {
  let loaded = 0;
  for await (const entry of handle.values()) {
    if (loaded >= 200) break;
    if (entry.kind !== 'file' || !entry.name.startsWith(CHAT_PREFIX) ||
        !entry.name.endsWith('.json')) continue;
    try {
      const file = await entry.getFile();
      if (file.size > 3_000_000) continue;
      const chat = parseConversation(JSON.parse(await file.text()), entry.name);
      if (chat) { conversations.set(chat.id, chat); loaded += 1; }
    } catch (_) { /* Skip unrelated or damaged files. */ }
  }
  return loaded;
}

function setBusy(busy) {
  analyzing = busy;
  button.disabled = busy;
  chooseFolderButton.disabled = busy;
  newChatButton.disabled = busy;
  document.querySelector('#import-chat').disabled = busy;
  renderChatList();
}

provider.addEventListener('change', () => {
  apiKey.value = '';
  apiKey.type = 'password';
  document.querySelector('#toggle-key').textContent = '显示';
  if (provider.value === 'openai') {
    baseUrl.value = 'https://api.openai.com/v1';
    modelName.value = 'gpt-4.1-mini';
  } else if (provider.value === 'custom') {
    baseUrl.value = 'http://127.0.0.1:11434/v1';
    modelName.value = 'qwen2.5:7b';
  }
  updateConfigStatus();
});
for (const field of [apiKey, baseUrl, modelName]) field.addEventListener('input', updateConfigStatus);
document.querySelector('#toggle-key').addEventListener('click', event => {
  const showing = apiKey.type === 'password';
  apiKey.type = showing ? 'text' : 'password';
  event.currentTarget.textContent = showing ? '隐藏' : '显示';
  event.currentTarget.setAttribute('aria-label', showing ? '隐藏密钥' : '显示密钥');
});

chooseFolderButton.addEventListener('click', async () => {
  try {
    const unsaved = directoryHandle || serverFolderName ? null : currentConversation;
    if ('showDirectoryPicker' in window) {
      const handle = await window.showDirectoryPicker({ id: 'onesentencescience-chats', mode: 'readwrite' });
      directoryHandle = handle;
      serverFolderName = null;
      conversations.clear();
      currentConversation = null;
      const loaded = await loadFolderChats(handle);
      if (unsaved?.turns.length) {
        conversations.set(unsaved.id, unsaved);
        currentConversation = unsaved;
        await saveConversation(unsaved);
      }
      setFolderStatus(`已打开文件夹“${handle.name}” · 找到 ${loaded} 个聊天记录。之后的回答会自动保存。`);
    } else {
      const response = await fetch('/api/storage/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-OneSentenceScience': '1' },
        body: '{}',
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '无法打开系统文件夹选择窗口。');
      if (!data.selected) return;
      loadServerChatList(data);
      if (unsaved?.turns.length) {
        conversations.set(unsaved.id, unsaved);
        currentConversation = unsaved;
        await saveConversation(unsaved);
      }
      setFolderStatus(`已打开文件夹“${data.folder_name}” · 找到 ${data.chats.length} 个聊天记录。之后的回答会自动保存。`);
    }
    renderChatList();
    renderConversation();
    if (currentConversation?.turns.length) renderResult(currentConversation.turns.at(-1).report);
    else results.hidden = true;
  } catch (error) {
    if (error.name !== 'AbortError') setFolderStatus(`无法打开文件夹：${error.message || '请重试。'}`, true);
  }
});

newChatButton.addEventListener('click', () => {
  currentConversation = null;
  input.value = '';
  input.dispatchEvent(new Event('input'));
  results.hidden = true;
  errorPanel.hidden = true;
  renderConversation();
  renderChatList();
  input.focus();
});

document.querySelector('#import-chat').addEventListener('click', () => {
  document.querySelector('#import-file').click();
});
document.querySelector('#import-file').addEventListener('change', async event => {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  try {
    if (file.size > 3_000_000) throw new Error('文件超过 3 MB。');
    const chat = parseConversation(JSON.parse(await file.text()), '');
    if (!chat) throw new Error('这不是有效的 OneSentenceScience 聊天文件。');
    chat.id = crypto.randomUUID();
    chat.fileName = `${CHAT_PREFIX}${chat.id}.json`;
    conversations.set(chat.id, chat);
    openConversation(chat);
    if (directoryHandle || serverFolderName) await saveConversation(chat);
    setFolderStatus(directoryHandle || serverFolderName
      ? '聊天已导入并保存到所选文件夹。' : '聊天已导入当前页面；选择文件夹后可自动保存。');
  } catch (error) {
    setFolderStatus(`导入失败：${error.message || '请检查文件。'}`, true);
  }
});

document.querySelector('#download-chat').addEventListener('click', () => {
  if (!currentConversation?.turns.length) {
    setFolderStatus('当前没有可以下载的聊天记录。', true);
    return;
  }
  const blob = new Blob([JSON.stringify(conversationData(currentConversation), null, 2)],
    { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = element('a');
  link.href = url;
  link.download = currentConversation.fileName;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

input.addEventListener('input', () => { count.textContent = `${input.value.length}/500`; });
input.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') form.requestSubmit();
});

document.querySelectorAll('.example-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    input.value = chip.dataset.example;
    input.dispatchEvent(new Event('input'));
    input.focus();
  });
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (analyzing) return;
  errorPanel.hidden = true;
  let settings;
  try {
    settings = modelConfig();
  } catch (error) {
    errorPanel.textContent = error.message;
    errorPanel.hidden = false;
    errorPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
  }
  progress.hidden = false;
  setBusy(true);
  button.textContent = '正在探索…';
  try {
    const history = (currentConversation?.turns || []).slice(-6).map(turn => ({
      observation: turn.observation,
      research_question: turn.report.research_question,
      conclusion: turn.report.result.conclusion,
    }));
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-OneSentenceScience': '1' },
      body: JSON.stringify({ observation: input.value.trim(), model_config: settings, history }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '暂时无法完成分析，请稍后重试。');
    const chat = currentConversation || newConversation(data.observation);
    chat.turns.push({ observation: data.observation, created_at: new Date().toISOString(),
      report: data });
    chat.updated_at = new Date().toISOString();
    currentConversation = chat;
    conversations.set(chat.id, chat);
    renderConversation();
    renderChatList();
    renderResult(data);
    input.value = '';
    input.dispatchEvent(new Event('input'));
    try {
      if (await saveConversation(chat)) {
        setFolderStatus(`已自动保存到“${directoryHandle?.name || serverFolderName}”。`);
      } else {
        setFolderStatus('回答已保留在当前页面；选择聊天文件夹后会自动保存。');
      }
    } catch (saveError) {
      setFolderStatus(`回答成功，但保存失败：${saveError.message || '请下载当前记录备份。'}`, true);
    }
  } catch (error) {
    errorPanel.textContent = error.message || '暂时无法完成分析，请稍后重试。';
    errorPanel.hidden = false;
    errorPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
  } finally {
    progress.hidden = true;
    setBusy(false);
    button.replaceChildren('开始探索 ', element('span', '', '↗'));
  }
});

renderChatList();
checkConfig();
checkStorage();
