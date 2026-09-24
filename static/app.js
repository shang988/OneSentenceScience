const form = document.querySelector('#observation-form');
const input = document.querySelector('#observation');
const count = document.querySelector('#char-count');
const button = document.querySelector('#analyze-button');
const progress = document.querySelector('#progress');
const errorPanel = document.querySelector('#error-panel');
const results = document.querySelector('#results');
const configStatus = document.querySelector('#config-status');

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

async function checkConfig() {
  try {
    const response = await fetch('/api/health');
    const data = await response.json();
    if (data.configured) {
      configStatus.textContent = '模型已连接 · 检索来自 OpenAlex';
      configStatus.dataset.state = 'ready';
    } else {
      configStatus.textContent = '尚未配置语言模型。请先按 GitHub 仓库 README 的“快速开始”设置。';
      configStatus.dataset.state = 'setup';
    }
  } catch (_) {
    configStatus.textContent = '暂时无法连接本地服务，请刷新页面。';
    configStatus.dataset.state = 'setup';
  }
}

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
  errorPanel.hidden = true;
  results.hidden = true;
  progress.hidden = false;
  button.disabled = true;
  button.textContent = '正在探索…';
  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ observation: input.value.trim() }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '暂时无法完成分析，请稍后重试。');
    renderResult(data);
  } catch (error) {
    errorPanel.textContent = error.message || '暂时无法完成分析，请稍后重试。';
    errorPanel.hidden = false;
    errorPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
  } finally {
    progress.hidden = true;
    button.disabled = false;
    button.replaceChildren('开始探索 ', element('span', '', '↗'));
  }
});

checkConfig();
