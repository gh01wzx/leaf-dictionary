'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons = {
  leaf:'<path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15"/><path d="M5 19c3-4 6-7 10-9"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  speaker:'<path d="m11 5-6 4H2v6h3l6 4V5Z"/><path d="M15 8.5a5 5 0 0 1 0 7m3-10a9 9 0 0 1 0 13"/>',
  book:'<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5v-15Z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/>',
  cards:'<rect x="7" y="6" width="13" height="15" rx="2.5"/><path d="M4 17V5a2 2 0 0 1 2-2h10"/>',
  settings:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  close:'<path d="M6 6l12 12M18 6 6 18"/>',
  quote:'<path d="M7 7h4v4c0 3-1.5 5-4 6M14 7h4v4c0 3-1.5 5-4 6"/>',
  edit:'<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/>',
  check:'<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  pause:'<path d="M9 5v14M15 5v14"/>',
  play:'<path d="m8 5 11 7-11 7V5Z"/>',
  trash:'<path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  clock:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  spark:'<path d="M12 3v4m0 10v4M3 12h4m10 0h4M6 6l2.5 2.5m7 7L18 18M6 18l2.5-2.5m7-7L18 6"/>',
  pen:'<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z"/>',
};
function icon(name) { return `<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${icons[name] || ''}</svg>`; }
// Inline style attributes are blocked by the page's CSP; set sizes through the CSSOM.
function applySizes(root) {
  root.querySelectorAll('[data-h]').forEach(el => el.style.setProperty('--h', el.dataset.h + '%'));
  root.querySelectorAll('[data-w]').forEach(el => { el.style.width = el.dataset.w + '%'; });
  root.querySelectorAll('[data-b]').forEach(el => { el.style.bottom = el.dataset.b + '%'; });
}
function decorate(root = document) { root.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); }); }

const token = $('meta[name="leaf-token"]').content;
const api = LeafRequests.createClient(token);
const Study = LeafStudy;
const lookupRequest = new LeafRequests.LatestRequest();
const suggestRequest = new LeafRequests.LatestRequest();
const libraryRequest = new LeafRequests.LatestRequest();
const reviewRequest = new LeafRequests.LatestRequest();
const libraryPageSize = 40;
const RATINGS = [[1,'忘了','没想起来'],[2,'费力','想了很久或有提示'],[3,'记得','顺利想起'],[4,'轻松','立刻想起']];
const STATE_LABEL = {new:'新词', learning:'学习中', relearning:'重新学习', review:'复习中'};

let currentView = 'lookup', currentResult = null, statsData = null, settings = null;
let review = {card:null, shown:false, busy:false, loading:false, startedAt:0, check:null, hintLevel:0, suggested:null};
let lastRated = null, waitTimer = null;
let libraryRows = [], libraryShown = 0, libraryFilter = 'all';
let sheetCard = null, sheetResult = null;
let definitionEditor = null, definitionBusy = false, saveBusy = false;
let suggestions = [], suggestionIndex = -1, suggestTimer = null, toastTimer = null, statsPending = null;

// ------------------------------------------------------------------ basics
function toast(message, options = {}) {
  if (typeof options === 'boolean') options = {error:options};
  clearTimeout(toastTimer);
  const el = $('#toast'), action = $('#toast-action');
  $('#toast-text').textContent = message;
  el.classList.toggle('error', Boolean(options.error));
  el.classList.toggle('celebrate', Boolean(options.celebrate));
  action.hidden = !options.action;
  action.textContent = options.actionLabel || '撤销';
  action.onclick = options.action ? async () => { el.hidden = true; try { await options.action(); } catch (e) { toast(e.message, true); } } : null;
  el.hidden = false;
  toastTimer = setTimeout(() => { el.hidden = true; }, options.duration || (options.action ? 6500 : options.error ? 6000 : 2800));
}
function dateLabel(value, options = {}) { return new Date(value).toLocaleDateString('zh-CN', {month:'numeric', day:'numeric', ...options}); }
function confirmAction(title, message, ok = '确认') {
  const dialog = $('#confirm-dialog');
  $('#confirm-title').textContent = title; $('#confirm-message').textContent = message; $('#confirm-ok').textContent = ok;
  dialog.returnValue = ''; dialog.showModal();
  return new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), {once:true}));
}
function inField() { const el = document.activeElement; return el && (['INPUT','TEXTAREA','SELECT'].includes(el.tagName) || el.isContentEditable); }
function anyDialogOpen() { return $$('dialog').some(d => d.open); }
function highlightWord(text, word) {
  const safe = escapeHTML(text);
  if (!word) return safe;
  const stem = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/e$/, '');
  try { return safe.replace(new RegExp(`(?<![A-Za-z])(${stem}[a-z]*)`, 'gi'), '<mark>$1</mark>'); } catch { return safe; }
}

// ------------------------------------------------------------------ theme
function applyTheme(choice) {
  if (choice === 'light' || choice === 'dark') document.documentElement.dataset.theme = choice;
  else delete document.documentElement.dataset.theme;
  $$('#setting-theme [data-theme-choice]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.themeChoice === (choice || 'auto'))));
}
let themeChoice = 'auto';
try { themeChoice = localStorage.getItem('leaf-theme') || 'auto'; } catch {}
applyTheme(themeChoice);

// ------------------------------------------------------------------ stats
function goalSummary(data) {
  const g = data.goal;
  if (!data.total) return {state:'', label:'', text:'查词后加入生词本，就能开始复习。'};
  if (g.met_goal) return {state:'goal', label:'目标完成', text:`今天的目标完成了${g.done > g.target ? `，还多复习了 ${g.done - g.target} 个` : ''}。`};
  const shortage = g.reachable < g.target
    ? (g.new_available ? ' 今天到期的词不够，复习完后可以加学新词补足。' : ' 今天能复习的词不够这么多，全部复习完就好。') : '';
  if (g.met_minimum) return {state:'min', label:'已达最低', text:`最低目标完成了，再复习 ${g.remaining} 个就能完成今天的目标。${shortage}`};
  if (!g.done) return {state:'none', label:'未开始', text:`今天还没开始，先完成最低的 ${g.minimum} 个就不算中断。${shortage}`};
  return {state:'none', label:'进行中', text:`还差 ${g.to_minimum} 个达到最低目标（${g.minimum} 个）。${shortage}`};
}
function paintGoalBar(bar, g) {
  if (!bar) return;
  const fill = bar.querySelector('.goal-fill'), tick = bar.querySelector('.goal-min');
  fill.style.width = Math.min(100, Math.round(g.done / g.target * 100)) + '%';
  fill.className = 'goal-fill ' + (g.met_goal ? 'goal' : g.met_minimum ? 'min' : 'below');
  tick.style.left = Math.min(100, g.minimum / g.target * 100) + '%';
  tick.hidden = g.minimum >= g.target;
  bar.setAttribute('aria-valuemax', String(g.target));
  bar.setAttribute('aria-valuenow', String(g.done));
  bar.setAttribute('aria-valuetext', `已复习 ${g.done} 个，目标 ${g.target} 个，最低 ${g.minimum} 个`);
}
// Returns a short message when this update crosses the minimum or the goal.
function renderStats(data) {
  if (statsData?.as_of && data.as_of && Date.parse(data.as_of) < Date.parse(statsData.as_of)) return '';
  const previous = statsData; statsData = data;
  const q = data.queue, g = data.goal, summary = goalSummary(data);
  const level = g.met_goal ? 'goal' : g.met_minimum ? 'min' : 'below';
  for (const id of ['#nav-due', '#tab-due']) { const el = $(id); el.textContent = data.due; el.hidden = !data.due; }
  $('#nav-total').textContent = data.total;
  // Sidebar: progress toward today's goal.
  $('#ring-value').style.strokeDashoffset = String(97.4 * (1 - Math.min(1, g.done / g.target)));
  $('#today-ring').className = 'ring ' + level;
  $('#today-ring').setAttribute('aria-label', `今日已复习 ${g.done} 个，目标 ${g.target} 个`);
  $('#ring-text').textContent = g.done;
  $('#today-summary').textContent = `${g.done} / ${g.target} 个词`;
  $('#today-detail').textContent = g.met_goal ? `目标完成${data.streak > 1 ? ` · 连续 ${data.streak} 天` : ''}`
    : g.met_minimum ? `已达最低 · 还差 ${g.remaining} 个` : `最低 ${g.minimum} 个 · 还差 ${g.to_minimum} 个`;
  // Home card.
  $('#goal-done').textContent = g.done;
  $('#goal-target').textContent = g.target;
  $('#goal-state').textContent = summary.label;
  $('#goal-state').hidden = !summary.label;
  $('#goal-state').className = 'pill ' + (summary.state === 'goal' ? 'ok' : summary.state === 'min' ? 'accent' : '');
  $('#goal-text').textContent = summary.text + (data.streak > 1 ? ` 已连续 ${data.streak} 天达到最低目标。` : '');
  $('#home-breakdown').textContent = data.total ? (data.due ? `现在可复习 ${data.due} 个` : '现在没有到期的词') : '';
  paintGoalBar($('#home-goal-bar'), g);
  // Review header.
  paintGoalBar($('#review-goal-bar'), g);
  $('#review-goal-label').innerHTML = `今日 <strong>${g.done}</strong> / ${g.target}${g.met_goal ? ' · 完成' : g.met_minimum ? ' · 已达最低' : ` · 最低 ${g.minimum}`}`;
  $('#queue-pills').innerHTML = data.total ? `<span class="pill">复习 ${q.review_due}</span><span class="pill">学习中 ${q.learning_due}</span><span class="pill accent">新词 ${q.new_left}</span>` : '';
  // Week chart with the goal drawn as a dashed line.
  const goalChanged = !previous?.goal || previous.goal.target !== g.target || previous.goal.minimum !== g.minimum;
  if (goalChanged || JSON.stringify(previous?.week) !== JSON.stringify(data.week)) {
    // Headroom above the goal keeps the dashed line visible when a day lands exactly on it.
    const week = Object.entries(data.week), scale = Math.max(g.target * 1.15, ...week.map(([, n]) => n));
    const line = Math.round(g.target / scale * 100);
    $('#week-chart').innerHTML = week.map(([day, n], i) => {
      const reached = n >= g.target ? 'goal' : n >= g.minimum ? 'min' : 'below';
      const label = `${dateLabel(day + 'T12:00:00')}：${n} 个词，${data.week_attempts?.[day] ?? n} 次练习${reached === 'goal' ? '，完成目标' : reached === 'min' ? '，达到最低' : ''}`;
      return `<button class="bar-col${i === 6 ? ' today' : ''}" data-chart-day="${day}" title="${label}" aria-label="${label}"><span class="bar-n">${n || ''}</span><span class="bar-track"><span class="bar ${reached}" data-h="${n ? Math.max(4, Math.round(n / scale * 100)) : 0}"></span><span class="goal-line" data-b="${line}"></span></span><span class="bar-d">${i === 6 ? '今天' : '日一二三四五六'[new Date(day + 'T12:00:00').getDay()]}</span></button>`;
    }).join('');
    applySizes($('#week-chart'));
  }
  if (JSON.stringify(previous?.recent) !== JSON.stringify(data.recent)) {
    $('#recent-list').innerHTML = data.recent.length ? data.recent.map(row => `<button class="recent glass" data-open-card="${row.id}"><strong>${escapeHTML(row.word)}</strong><span>${escapeHTML(row.meaning)}</span></button>`).join('')
      : '<div class="empty glass"><strong>生词本还是空的</strong><p class="muted">查一个词，点“加入生词本”，它就会出现在这里。</p></div>';
  }
  if (!previous?.goal || previous.today !== data.today) return '';
  if (!previous.goal.met_goal && g.met_goal) return `今天的目标完成了（${g.done} 个）`;
  if (!previous.goal.met_minimum && g.met_minimum) return `最低目标完成（${g.done} / ${g.target}）`;
  return '';
}
function refreshStats({force = false} = {}) {
  if (statsPending && !force) return statsPending;
  const pending = api('stats').then(data => { renderStats(data); return data; }).finally(() => { if (statsPending === pending) statsPending = null; });
  statsPending = pending;
  return pending;
}

// ------------------------------------------------------------------ navigation
const VIEWS = ['lookup', 'review', 'library', 'settings'];
async function navigate(view) {
  if (!VIEWS.includes(view)) view = 'lookup';
  if (currentView !== view) stopSpeech();
  libraryRequest.cancel(); reviewRequest.cancel(); review.loading = false;
  clearTimeout(waitTimer);
  currentView = view;
  $$('.view').forEach(el => { el.hidden = el.id !== 'view-' + view; });
  $$('[data-view]').forEach(el => {
    if (el.classList.contains('brand')) return;
    const active = el.dataset.view === view;
    el.classList.toggle('active', active);
    if (active) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
  });
  if (location.hash !== '#' + view) history.replaceState(null, '', '#' + view);
  window.scrollTo({top:0, behavior:'instant'});
  try {
    const work = view === 'review' ? loadReview() : view === 'library' ? loadLibrary() : view === 'settings' ? loadSettings() : Promise.resolve();
    await Promise.all([refreshStats(), work]);
  } catch (error) { if (error.name !== 'AbortError') toast(error.message, true); }
}

// ------------------------------------------------------------------ lookup
function setContextOpen(open) {
  $('#context-panel').hidden = !open;
  $('#context-toggle').setAttribute('aria-expanded', String(open));
  updateContextState();
}
function updateContextState() {
  const value = $('#context').value.trim();
  $('#context-state').textContent = value ? '· 已填写' : '';
  const words = $('#context-words');
  if (!value) { words.innerHTML = ''; return; }
  const current = Study.clean($('#query').value);
  words.innerHTML = Study.tokens(value.slice(0, 1500)).map(part => part.word
    ? `<button type="button" class="token${Study.clean(part.text) === current ? ' on' : ''}" data-token="${escapeHTML(part.text)}">${escapeHTML(part.text)}</button>`
    : `<span>${escapeHTML(part.text)}</span>`).join('');
}
function placePassage(text) {
  $('#context').value = text.trim().slice(0, 6000);
  $('#query').value = '';
  setContextOpen(true);
  hideSuggestions();
  toast('已放入原句，点句中的词来查');
}
function showHome(show) { $('#home').hidden = !show; }
function hideSuggestions() {
  suggestRequest.cancel(); clearTimeout(suggestTimer);
  suggestions = []; suggestionIndex = -1;
  $('#suggestions').hidden = true; $('#suggestions').innerHTML = '';
  $('#query').setAttribute('aria-expanded', 'false');
  $('#query').removeAttribute('aria-activedescendant');
}
function renderSuggestions() {
  const list = $('#suggestions');
  if (!suggestions.length) { hideSuggestions(); return; }
  list.innerHTML = suggestions.map((item, i) => `<li role="option" id="sg-${i}" class="${i === suggestionIndex ? 'active' : ''}" aria-selected="${i === suggestionIndex}" data-suggest="${escapeHTML(item.word)}"><strong>${escapeHTML(item.word)}</strong><span>${escapeHTML(item.gloss)}</span>${item.own ? '<em>生词本</em>' : ''}</li>`).join('');
  list.hidden = false;
  $('#query').setAttribute('aria-expanded', 'true');
  if (suggestionIndex >= 0) $('#query').setAttribute('aria-activedescendant', 'sg-' + suggestionIndex);
}
function scheduleSuggestions() {
  clearTimeout(suggestTimer);
  const value = $('#query').value.trim();
  if (!value || Study.looksLikePassage(value)) { hideSuggestions(); return; }
  suggestTimer = setTimeout(async () => {
    const request = suggestRequest.start();
    try {
      const data = await api('suggest?q=' + encodeURIComponent(value), undefined, request.signal);
      if (!request.current() || document.activeElement !== $('#query')) return;
      suggestions = data.items; suggestionIndex = -1; renderSuggestions();
    } catch (error) { if (error.name !== 'AbortError') hideSuggestions(); }
  }, 90);
}
async function searchWord(word) {
  word = String(word || '').trim();
  if (!word) { $('#query').focus(); return; }
  if (Study.looksLikePassage(word)) { placePassage(word); return; }
  hideSuggestions(); stopSpeech();
  const request = lookupRequest.start();
  $('#query').value = word; $('#clear-query').hidden = false;
  currentResult = null;
  const panel = $('#search-result');
  panel.setAttribute('aria-busy', 'true');
  panel.innerHTML = '<div class="skeleton glass"><span></span><span></span><span></span></div>';
  showHome(false);
  updateContextState();
  try {
    const result = await api('explain', {query:word, context:$('#context').value, source:$('#source').value, save:false}, request.signal);
    if (!request.current()) return;
    if (!result.found) {
      panel.innerHTML = `<div class="notice glass"><strong>没有找到「${escapeHTML(result.query)}」</strong><p class="muted">${escapeHTML(result.explanation?.warning || '检查一下拼写，或试试单词原形。')}</p></div>`;
      return;
    }
    currentResult = result;
    renderResult();
  } catch (error) {
    if (request.current() && error.name !== 'AbortError') panel.innerHTML = `<div class="notice glass"><strong>这次查询没有完成</strong><p class="muted">${escapeHTML(error.message)}</p><button class="button secondary" id="retry-query">重试</button></div>`;
  } finally { if (request.current()) panel.removeAttribute('aria-busy'); }
}
function saveButtonHTML(result) {
  const saved = result.saved_card;
  if (result.can_save === false) return '<span class="pill muted-pill">暂缺中文解释</span>';
  if (!saved) return `<button class="button primary" id="save-word">${icon('plus')}加入生词本 <kbd>S</kbd></button>`;
  const newContext = result.context && (result.context !== saved.context || result.source !== saved.source);
  if (newContext) return `<button class="button secondary" id="save-word">${icon('quote')}保存这条原句</button>`;
  return `<span class="pill ok">${icon('check')}已在生词本${saved.paused ? ' · 已暂停' : ''}</span>`;
}
function wordHeaderHTML(word, phonetic, meta) {
  return `<div class="word-line"><h2 class="headword">${escapeHTML(word)}</h2>${pronunciationControls(word)}</div><div class="word-meta">${phonetic ? `<span class="phonetic">/${escapeHTML(phonetic)}/</span>` : ''}${meta}</div>`;
}
function renderResult() {
  const result = currentResult;
  if (!result) return;
  const meaning = result.explanation;
  const base = (result.lemma && result.lemma !== result.query && result.lemma) || meaning.related_lemma;
  const lemma = base && base !== result.query ? `<span>原形 <button class="link-button" data-search="${escapeHTML(base)}">${escapeHTML(base)}</button></span>` : '';
  $('#search-result').innerHTML = `<article class="result glass strong">
    <header class="result-head"><div>${wordHeaderHTML(result.query, result.phonetic, `${meaning.part_of_speech ? `<span>${escapeHTML(meaning.part_of_speech)}</span>` : ''}${lemma}`)}</div>
      <div class="result-actions">${saveButtonHTML(result)}</div></header>
    ${explanationHTML(meaning, Boolean(result.context), 'lookup', result.query)}
    ${result.context ? `<details class="fold"><summary>本次原句</summary><blockquote>${highlightWord(result.context, result.query)}</blockquote></details>` : ''}
    <footer class="result-foot muted small"><span>${escapeHTML(result.dictionary_source || meaning.dictionary_source || '词典')}</span>${result.saved_card ? `<button class="link-button" data-open-card="${result.saved_card.id}">查看学习记录</button>` : ''}</footer>
  </article>`;
  bindFolds($('#search-result'));
}
async function saveCurrent() {
  if (!currentResult || saveBusy || currentResult.can_save === false) return;
  const result = currentResult, wasNew = !result.saved_card;
  saveBusy = true;
  const button = $('#save-word');
  if (button) { button.disabled = true; }
  try {
    const data = await api('explain', {query:result.query, context:result.context, source:result.source, save:true});
    if (!data.saved_card) throw new Error('这个词暂时无法收录，请稍后重试。');
    if (currentResult === result) { currentResult = data; renderResult(); }
    refreshStats({force:true}).catch(() => {});
    if (wasNew) toast(`已加入生词本，将在复习中出现`, {action:async () => {
      await api('delete', {id:data.saved_card.id});
      if (currentResult?.query === data.query) { currentResult.saved_card = null; renderResult(); }
      await refreshStats({force:true}); toast('已从生词本移除');
    }});
    else toast('原句已保存，复习进度不变');
  } catch (error) { toast(error.message, true); if (button?.isConnected) button.disabled = false; }
  finally { saveBusy = false; }
}

// ------------------------------------------------------------------ explanation markup
const foldStore = new Map(); let foldCounter = 0;
function foldHTML(label, senses) {
  const id = 'f' + (++foldCounter); foldStore.set(id, senses);
  return `<details class="fold" data-fold="${id}"><summary>${escapeHTML(label)}<span class="muted">${senses.length}</span></summary><div class="fold-body"></div></details>`;
}
function bindFolds(root) {
  root.querySelectorAll('[data-fold]').forEach(el => { el.foldSenses = foldStore.get(el.dataset.fold); foldStore.delete(el.dataset.fold); el.removeAttribute('data-fold'); });
}
document.addEventListener('toggle', event => {
  const el = event.target;
  if (el.open && el.foldSenses) { el.querySelector('.fold-body').innerHTML = el.foldSenses.map(s => senseHTML(s)).join(''); el.foldSenses = null; }
}, true);
function senseHTML(sense, hideDefinition = false) {
  const example = sense.examples?.[0];
  return `<div class="sense"><div class="sense-head"><span class="pos">${escapeHTML(sense.pos_label)}</span><strong>${escapeHTML(sense.gloss)}</strong>${sense.section_label ? `<small class="muted">${escapeHTML(sense.section_label)}</small>` : ''}</div>${hideDefinition ? '' : `<p>${escapeHTML(sense.definition)}</p>`}${sense.verified_usage && sense.usage ? `<p class="usage">${escapeHTML(sense.usage)}</p>` : ''}${example ? `<div class="example"><p lang="en">${escapeHTML(example.text)}</p><p>${escapeHTML(example.translation)}</p></div>` : ''}</div>`;
}
function coreHTML(meaning, scope) {
  return `<section class="core"><div class="core-head"><span class="label">${escapeHTML(meaning.core_label || '核心释义')}${meaning.custom_definition ? '<span class="pill accent tiny">我的释义</span>' : ''}</span><button class="link-button" data-edit-definition="${scope}">${icon('edit')}用自己的话改写</button></div><p class="core-text">${escapeHTML(meaning.core_meaning)}</p></section>`;
}
function explanationHTML(meaning, hasContext, scope, word) {
  const parts = [coreHTML(meaning, scope)];
  if (hasContext && meaning.context_meaning) parts.push(`<section class="in-context"><span class="label">在这句话里</span><p>${escapeHTML(meaning.context_meaning)}</p>${meaning.context_translation ? `<p class="muted">${escapeHTML(meaning.context_translation)}</p>` : ''}${meaning.explanation ? `<p class="muted small">${escapeHTML(meaning.explanation)}</p>` : ''}</section>`);
  else if (meaning.explanation) parts.push(`<p class="note">${escapeHTML(meaning.explanation)}</p>`);
  if (meaning.word_family) parts.push(`<p class="note">${escapeHTML(meaning.word_family)}</p>`);
  if (meaning.learner_senses) {
    parts.push(`<div class="senses">${meaning.learner_senses.map(s => senseHTML(s, meaning.learner_senses.length === 1)).join('')}</div>`);
    if (meaning.more_main_senses?.length) parts.push(foldHTML('更多常用义', meaning.more_main_senses));
    if (meaning.supplementary_senses?.length) parts.push(foldHTML('专业、少见及专名用法', meaning.supplementary_senses));
  } else {
    if (meaning.usage) parts.push(`<div class="usage-strip"><strong lang="en">${escapeHTML(meaning.usage)}</strong><span>${escapeHTML(meaning.usage_meaning)}</span></div>`);
    if (meaning.example_en) parts.push(`<div class="example"><p lang="en">${highlightWord(meaning.example_en, word)}</p><p>${escapeHTML(meaning.example_zh)}</p></div>`);
    if (meaning.other_uses?.length) parts.push(`<details class="fold"><summary>${escapeHTML(meaning.other_uses_label || '其他用法')}</summary><div class="fold-body">${meaning.other_uses.map(u => `<p>${escapeHTML(u)}</p>`).join('')}</div></details>`);
    if (meaning.source_meanings?.length) parts.push(`<details class="fold"><summary>更多中文释义</summary><div class="fold-body">${meaning.source_meanings.map(u => `<p>${escapeHTML(u)}</p>`).join('')}</div></details>`);
    if (meaning.english_definition) parts.push(`<details class="fold"><summary>英文原始释义</summary><div class="fold-body"><p lang="en">${escapeHTML(meaning.english_definition)}</p></div></details>`);
  }
  if (meaning.warning) parts.push(`<p class="warning">${escapeHTML(meaning.warning)}</p>`);
  if (meaning.source_note) {
    const refs = (meaning.editorial_references || []).filter(u => /^https:\/\//.test(u));
    const link = meaning.reference_url && /^https:\/\//.test(meaning.reference_url) ? `<a href="${escapeHTML(meaning.reference_url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(meaning.reference_title || '来源')} ↗</a>` : '';
    parts.push(`<details class="fold quiet"><summary>来源与说明</summary><div class="fold-body"><p class="muted small">${escapeHTML(meaning.source_note)}</p>${link ? `<p class="small">${link}</p>` : ''}${refs.length ? `<p class="small">修订参考：${refs.map((u, i) => `<a href="${escapeHTML(u)}" target="_blank" rel="noopener noreferrer">${i + 1} ↗</a>`).join(' · ')}</p>` : ''}</div></details>`);
  }
  return parts.join('');
}

// ------------------------------------------------------------------ definition editor
function editorTarget(scope) {
  if (scope === 'review') return review.shown ? {word:review.card.word, meaning:review.card.explanation} : null;
  if (scope === 'sheet') return sheetResult ? {word:sheetResult.query, meaning:sheetResult.explanation} : null;
  return currentResult ? {word:currentResult.query, meaning:currentResult.explanation} : null;
}
function openDefinitionEditor(scope) {
  if (definitionBusy) return;
  const target = editorTarget(scope);
  if (!target) return;
  const m = target.meaning;
  definitionEditor = {scope, word:target.word, expected:m.custom_updated || ''};
  $('#definition-word').textContent = target.word;
  $('#definition-text').value = m.core_meaning;
  $('#definition-original').textContent = m.dictionary_core_meaning ?? m.core_meaning;
  const personal = m.origin === 'personal';
  $('#definition-reference summary').textContent = personal ? '查看导入时的释义' : '查看词典原释义';
  $('#definition-restore').textContent = personal ? '恢复导入时的释义' : '恢复词典释义';
  $('#definition-restore').hidden = !m.custom_definition;
  $('#definition-reference').open = false;
  $('#definition-error').hidden = true;
  updateDefinitionInput();
  $('#definition-dialog').showModal();
  $('#definition-text').focus();
}
function updateDefinitionInput() {
  const field = $('#definition-text');
  $('#definition-count').textContent = `${field.value.length.toLocaleString()} / 3,000`;
  $('#definition-save').disabled = definitionBusy || !field.value.trim() || field.value.length > 3000;
}
async function persistDefinition(reset = false) {
  if (!definitionEditor || definitionBusy) return;
  const editor = definitionEditor, text = $('#definition-text').value.trim();
  if (!reset && (!text || text.length > 3000)) { updateDefinitionInput(); return; }
  definitionBusy = true; $('#definition-error').hidden = true;
  for (const id of ['definition-save', 'definition-cancel', 'definition-restore']) $('#' + id).disabled = true;
  try {
    const change = await api('definition', {word:editor.word, meaning:reset ? null : text, expected:editor.expected});
    const apply = m => {
      if (!m) return;
      m.dictionary_core_meaning ??= m.core_meaning;
      m.core_meaning = change.meaning ?? m.dictionary_core_meaning;
      m.custom_definition = change.meaning !== null;
      m.custom_updated = change.updated;
    };
    if (currentResult?.query === editor.word) { apply(currentResult.explanation); const el = $('#search-result .core'); if (el) el.outerHTML = coreHTML(currentResult.explanation, 'lookup'); }
    if (review.card?.word === editor.word) { apply(review.card.explanation); review.card.meaning = review.card.explanation.core_meaning; const el = $('#review-answer .core'); if (el) el.outerHTML = coreHTML(review.card.explanation, 'review'); }
    if (sheetResult?.query === editor.word) { apply(sheetResult.explanation); const el = $('#sheet-body .core'); if (el) el.outerHTML = coreHTML(sheetResult.explanation, 'sheet'); }
    $('#definition-dialog').close();
    refreshStats({force:true}).catch(() => {});
    if (currentView === 'library') loadLibrary().catch(() => {});
    toast(reset ? '已恢复原释义' : '已保存，查词和复习都会用你的释义');
  } catch (error) {
    $('#definition-error').textContent = error.message; $('#definition-error').hidden = false;
  } finally {
    definitionBusy = false;
    for (const id of ['definition-cancel', 'definition-restore']) $('#' + id).disabled = false;
    updateDefinitionInput();
  }
}

// ------------------------------------------------------------------ review
async function loadReview({focus = null, last = null} = {}) {
  stopSpeech(); clearTimeout(waitTimer);
  const request = reviewRequest.start();
  review = {card:null, shown:false, busy:false, loading:true, startedAt:0, check:null, hintLevel:0, suggested:null};
  const box = $('#review-content');
  if (!box.firstElementChild) box.innerHTML = '<div class="skeleton glass tall"><span></span><span></span><span></span></div>';
  try {
    const params = new URLSearchParams();
    if (focus) params.set('focus', focus);
    if (last) params.set('last', last);
    const {card, stats} = await api('review?' + params, undefined, request.signal);
    if (!request.current()) return;
    renderStats(stats);
    review.card = card;
    if (!card) { renderReviewDone(stats, last); return; }
    renderReviewCard(card);
  } catch (error) {
    if (request.current() && error.name !== 'AbortError') box.innerHTML = `<div class="notice glass"><p>${escapeHTML(error.message)}</p><button class="button secondary" id="retry-review">重新加载</button></div>`;
  } finally { if (request.current()) review.loading = false; }
}
function renderReviewDone(stats, last) {
  const q = stats.queue, box = $('#review-content');
  if (!stats.total) {
    box.innerHTML = `<div class="done glass strong"><div class="done-icon">${icon('leaf')}</div><h2>从阅读里带回第一个词</h2><p class="muted">查词后点“加入生词本”，回来就能开始复习。</p><button class="button primary" data-view="lookup">去查词</button></div>`;
    return;
  }
  const soon = q.next_learning && Date.parse(q.next_learning) - Date.now() < 30 * 60000;
  if (soon) {
    const wait = Math.max(0, Date.parse(q.next_learning) - Date.now());
    box.innerHTML = `<div class="done glass strong"><div class="done-icon">${icon('clock')}</div><h2>${Study.intervalLabel(q.next_learning)}再看一次</h2><p class="muted">刚学的词需要隔一小会儿再回忆，间隔本身就是记忆的一部分。到时间会自动出现。</p><div class="button-row center">${!stats.goal.met_goal && q.new_total > 0 ? `<button class="button primary" data-extra-new="${Math.min(stats.goal.remaining, q.new_total)}">先学 ${Math.min(stats.goal.remaining, q.new_total)} 个新词</button>` : ''}<button class="button secondary" id="review-now">现在就看</button><button class="button ghost" data-view="lookup">先去阅读</button></div></div>`;
    waitTimer = setTimeout(() => { if (currentView === 'review' && !review.card) loadReview(); }, Math.min(wait + 800, 30 * 60000));
    return;
  }
  const g = stats.goal;
  const tomorrow = Object.values(stats.forecast || {})[0] || 0;
  const topUp = !g.met_goal && q.new_total > 0 ? Math.min(g.remaining, q.new_total) : 0;
  const title = g.met_goal ? '今天的目标完成了' : g.met_minimum ? '最低目标完成了' : '到期的词复习完了';
  const gap = g.met_goal ? '' : g.met_minimum ? `离今天的目标还差 ${g.remaining} 个。` : `离最低目标还差 ${g.to_minimum} 个。`;
  const streak = stats.streak > 1 ? `已连续 <strong>${stats.streak}</strong> 天达到最低目标。` : '';
  const retention = stats.retention?.reviews >= 20 ? `<p class="muted small">近 30 天复习记住率 ${(stats.retention.rate * 100).toFixed(0)}%（目标 ${Math.round((settings?.retention ?? 0.9) * 100)}%）</p>` : '';
  box.innerHTML = `<div class="done glass strong"><div class="done-icon ${g.met_minimum ? 'ok' : ''}">${icon(g.met_minimum ? 'check' : 'clock')}</div><h2>${title}</h2>
    <div class="done-goal"><div class="today-big"><span>${g.done}</span><span class="goal-of">/ ${g.target} 个词</span></div><div class="goal-bar" id="done-goal-bar"><span class="goal-fill"></span><span class="goal-min"></span></div></div>
    ${gap || streak ? `<p>${gap}${streak}</p>` : ''}
    <p class="muted">${topUp ? `到期的词都复习完了，还有 ${q.new_total} 个新词在排队。` : ''}${tomorrow ? `明天约有 ${tomorrow} 个词到期。` : stats.next_due ? `下一个词 ${Study.intervalLabel(stats.next_due)}到期。` : ''}</p>${retention}
    <div class="button-row center">${topUp ? `<button class="button primary" data-extra-new="${topUp}">再学 ${topUp} 个新词，完成今天的目标</button><button class="button ghost" data-view="lookup">先去阅读</button>` : '<button class="button primary" data-view="lookup">继续阅读</button>'}</div></div>`;
  paintGoalBar($('#done-goal-bar'), g);
}
function reviewContextHTML(card) {
  const own = card.encounters?.find(e => e.context && e.source !== '我的造句') || (card.context ? {context:card.context, source:card.source} : null);
  if (!own) return '';
  return `<button class="link-button" id="context-hint">${icon('quote')}想不起来？看看当时的原句</button><blockquote id="review-hint" hidden>${highlightWord(own.context, card.word)}${own.source ? `<cite>${escapeHTML(own.source)}</cite>` : ''}</blockquote>`;
}
function renderReviewCard(card) {
  const cloze = card.mode === 'cloze' ? card.cloze : null;
  const progress = card.progress;
  const tag = cloze ? '<span class="mode-tag alt">写出这个词</span>' : '<span class="mode-tag">想一想意思</span>';
  const state = `<span class="pill">${STATE_LABEL[progress.state] || ''}</span>${card.learned_ahead ? '<span class="pill">提前一点</span>' : ''}`;
  const leech = progress.leech ? `<div class="leech">${icon('spark')}<span>这个词已经忘了 ${progress.failures} 次。翻开后试试<strong>用自己的话改写释义</strong>，或<strong>写一个自己的句子</strong>，比反复看更有效。</span></div>` : '';
  let prompt;
  if (cloze) {
    let inputPlaced = false;
    const sentence = cloze.segments.map(s => {
      if (!s.blank) return escapeHTML(s.text);
      if (!card.typing || inputPlaced) return '<span class="blank">_____</span>';
      inputPlaced = true;
      return `<input class="cloze-input" id="cloze-input" autocomplete="off" spellcheck="false" autocapitalize="off" aria-label="填入单词" size="${Math.max(5, s.text.length + 2)}">`;
    }).join('');
    prompt = `<p class="cloze-meaning"><span class="label">意思</span>${escapeHTML(cloze.hint)}</p>
      <p class="cloze-sentence" lang="en">${sentence}</p>
      ${cloze.own ? `<p class="muted small">来自${escapeHTML(cloze.source || '你的阅读')}</p>` : ''}
      <div id="cloze-feedback" class="cloze-feedback" aria-live="polite"></div>
      <div class="button-row" id="cloze-actions">${card.typing ? `<button class="button primary" id="cloze-check">检查 <kbd>↵</kbd></button><button class="button ghost" id="cloze-hint">提示首字母</button>` : `<button class="button primary" id="reveal">翻开答案 <kbd>空格</kbd></button>`}<button class="link-button" id="cloze-giveup">想不起来</button></div>`;
  } else {
    prompt = `${wordHeaderHTML(card.word, card.phonetic, '')}<p class="prompt">它是什么意思？先在心里说出来，再翻开。</p>${reviewContextHTML(card)}<div class="button-row"><button class="button primary" id="reveal">翻开答案 <kbd>空格</kbd></button></div>`;
  }
  $('#review-content').innerHTML = `<article class="review-card glass strong" data-mode="${card.mode}">
      <div class="review-top">${tag}<span class="spacer"></span>${state}</div>
      ${leech}
      <div class="review-prompt">${prompt}</div>
      <div id="review-answer" class="review-answer" hidden></div>
    </article>
    <div id="rating-dock" class="rating-dock glass strong" hidden>
      <div class="rating-buttons">${RATINGS.map(([n, label, help]) => `<button class="rate r${n}" data-rating="${n}"><kbd>${n}</kbd><strong>${label}</strong><small>${help}</small></button>`).join('')}</div>
      <p class="muted small rating-tip">看了答案才想起来，请选“忘了”。评分只影响下次出现的时间。</p>
    </div>`;
  review.startedAt = Date.now();
  if (cloze && card.typing) setTimeout(() => $('#cloze-input')?.focus(), 30);
}
function answerHTML(card) {
  const parts = [];
  if (card.mode === 'cloze' && card.cloze) {
    const c = card.cloze;
    parts.push(wordHeaderHTML(card.word, card.phonetic, ''));
    parts.push(`<div class="example solved"><p lang="en">${c.segments.map(s => s.blank ? `<mark>${escapeHTML(s.text)}</mark>` : escapeHTML(s.text)).join('')}</p>${c.translation ? `<p>${escapeHTML(c.translation)}</p>` : ''}</div>`);
  }
  parts.push(explanationHTML(card.explanation, false, 'review', card.word));
  const contexts = (card.encounters || []).filter(e => e.context);
  if (contexts.length) parts.push(`<details class="fold" ${card.mode === 'recognize' ? 'open' : ''}><summary>你遇到它的地方<span class="muted">${contexts.length}</span></summary><div class="fold-body">${contexts.slice(0, 5).map(e => `<blockquote>${highlightWord(e.context, card.word)}${e.source ? `<cite>${escapeHTML(e.source)}</cite>` : ''}</blockquote>`).join('')}</div></details>`);
  parts.push(`<form class="own-sentence" id="own-sentence"><label for="own-sentence-text">${icon('pen')}用它造个句子 <span class="muted small">选填 · 会用于以后的填空练习</span></label><div class="inline-field"><input id="own-sentence-text" maxlength="500" placeholder="Write your own sentence with “${escapeHTML(card.word)}”…" lang="en"><button class="button secondary" type="submit">保存</button></div></form>`);
  return parts.join('');
}
function revealAnswer() {
  const card = review.card;
  if (!card || review.shown) return;
  review.shown = true;
  const answer = $('#review-answer');
  answer.innerHTML = answerHTML(card);
  bindFolds(answer);
  answer.hidden = false;
  $('#reveal')?.remove();
  $('#cloze-actions')?.remove();
  const prompt = $('.review-prompt .prompt'); if (prompt) prompt.hidden = true;
  $('#rating-dock').hidden = false;
  if (review.suggested) {
    $(`.rate[data-rating="${review.suggested}"]`)?.classList.add('suggested');
    $('.rating-tip').textContent = `按 ↵ 采用建议评分“${RATINGS[review.suggested - 1][1]}”，也可以自己选。`;
  }
  if (document.activeElement && document.activeElement.id === 'cloze-input') document.activeElement.blur();
}
function checkCloze(giveUp = false) {
  const card = review.card;
  if (!card?.cloze || review.shown) return;
  const input = $('#cloze-input');
  const verdict = giveUp ? {result:'wrong'} : Study.checkAnswer(input?.value || '', card.cloze);
  if (verdict.result === 'empty') { input?.focus(); return; }
  review.check = verdict.result;
  review.suggested = Study.suggestedRating(verdict.result, review.hintLevel > 0);
  const answer = card.cloze.answer;
  const messages = {correct:['ok', '完全正确'], form:['near', `对了，这句里应写作 ${answer}`], close:['near', `差一点，正确拼写是 ${answer}`], wrong:['bad', giveUp ? `答案是 ${answer}` : `答案是 ${answer}`]};
  const [kind, text] = messages[verdict.result];
  $('#cloze-feedback').innerHTML = `<span class="verdict ${kind}">${kind === 'ok' ? icon('check') : ''}${escapeHTML(text)}</span>`;
  if (input) { input.readOnly = true; input.classList.add(kind); if (!input.value) input.value = answer; }
  revealAnswer();
}
function useHint() {
  const card = review.card, input = $('#cloze-input');
  if (!card?.cloze || !input || review.shown) return;
  review.hintLevel = Math.min(review.hintLevel + 1, card.cloze.answer.length);
  input.placeholder = Study.hint(card.cloze.answer, review.hintLevel);
  input.focus();
}
async function submitRating(rating) {
  const card = review.card;
  if (!card || !review.shown || review.busy || anyDialogOpen()) return;
  review.busy = true;
  $$('[data-rating]').forEach(el => { el.disabled = true; });
  try {
    const data = await api('rate', {id:card.id, rating:Number(rating), version:card.card_json, mode:card.mode, duration_ms:Date.now() - review.startedAt});
    const milestone = renderStats(data.stats);
    lastRated = {review_id:data.review_id, card_id:card.id, word:card.word};
    const next = `${card.word} · ${Study.intervalLabel(data.due)}再复习`;
    toast(milestone ? `${milestone}　${next}` : next, {action:undoLastRating, duration:milestone ? 8000 : undefined, celebrate:Boolean(milestone)});
    if (currentView === 'review') { window.scrollTo({top:0, behavior:'instant'}); await loadReview({last:card.id}); }
  } catch (error) {
    if (error.name !== 'AbortError') toast(error.message, true);
    if (error.status === 409 && currentView === 'review') await loadReview();
  } finally {
    review.busy = false;
    $$('[data-rating]').forEach(el => { el.disabled = false; });
  }
}
async function undoLastRating() {
  if (!lastRated) return;
  const target = lastRated; lastRated = null;
  const data = await api('undo', {review_id:target.review_id});
  renderStats(data.stats);
  if (currentView !== 'review') await navigate('review');
  await loadReview({focus:target.card_id});
  toast(`已撤销 ${target.word} 的评分`);
}
async function saveOwnSentence(form) {
  const card = review.card || sheetCard, field = form.querySelector('input');
  const text = field.value.trim();
  if (!card || !text) { field.focus(); return; }
  const data = await api('sentence', {id:card.id, text});
  field.value = '';
  if (review.card) review.card.encounters = data.encounters;
  toast(data.contains_word ? '已保存，以后会用你的句子来练习' : `已保存。句子里没找到“${card.word}”，所以不会用于填空`);
}

// ------------------------------------------------------------------ library
async function loadLibrary() {
  const request = libraryRequest.start();
  const list = $('#library-list');
  list.setAttribute('aria-busy', 'true');
  try {
    const q = $('#library-search').value.trim();
    const data = await api(`library?q=${encodeURIComponent(q)}&status=${libraryFilter}&sort=${$('#library-sort').value}`, undefined, request.signal);
    if (!request.current()) return;
    libraryRows = data.cards; libraryShown = 0; list.innerHTML = '';
    const filtered = q || libraryFilter !== 'all';
    $('#library-summary').textContent = `${filtered ? '找到' : '共'} ${data.cards.length.toLocaleString()} 个词${data.cards.length >= 2000 ? '（显示前 2,000 个，可搜索）' : ''}`;
    if (data.cards.length) showMoreLibrary();
    else list.innerHTML = filtered ? '<div class="empty glass"><strong>没有符合条件的词</strong><p class="muted">换个关键词或筛选试试。</p><button class="button secondary" id="reset-library">显示全部</button></div>'
      : '<div class="empty glass"><strong>留下你想学会的词</strong><p class="muted">查词后点“加入生词本”。</p><button class="button primary" data-view="lookup">去查词</button></div>';
  } catch (error) {
    if (request.current() && error.name !== 'AbortError') list.innerHTML = `<div class="notice glass"><p>${escapeHTML(error.message)}</p><button class="button secondary" id="retry-library">重新加载</button></div>`;
  } finally { if (request.current()) list.removeAttribute('aria-busy'); }
}
function strengthHTML(row) {
  if (row.paused) return '<span class="pill">已暂停</span>';
  if (row.state === 'new') return '<span class="pill accent">新词</span>';
  const r = Math.round((row.retrievability ?? 0) * 100);
  const due = new Date(row.due) <= new Date();
  return `<span class="strength" title="现在记得的概率约 ${r}%"><span class="meter"><span data-w="${r}"></span></span>${due ? '<span class="due-now">待复习</span>' : `<span class="muted">${Study.intervalLabel(row.due)}</span>`}</span>`;
}
function libraryRowHTML(row) {
  return `<button class="word-row glass" data-open-card="${row.id}"><span class="row-main"><strong>${escapeHTML(row.word)}</strong><span class="row-meaning">${escapeHTML(row.meaning)}</span></span><span class="row-side">${strengthHTML(row)}${row.failures >= 3 ? '<span class="pill warn">常忘</span>' : ''}</span></button>`;
}
function showMoreLibrary() {
  $('#library-more')?.remove();
  const next = libraryRows.slice(libraryShown, libraryShown + libraryPageSize);
  libraryShown += next.length;
  $('#library-list').insertAdjacentHTML('beforeend', next.map(libraryRowHTML).join(''));
  applySizes($('#library-list'));
  if (libraryShown < libraryRows.length) $('#library-list').insertAdjacentHTML('beforeend', `<button class="button secondary wide" id="library-more">再显示 ${Math.min(libraryPageSize, libraryRows.length - libraryShown)} 个</button>`);
}
async function openCard(id) {
  const sheet = $('#card-sheet');
  $('#sheet-title').innerHTML = '';
  $('#sheet-body').innerHTML = '<div class="skeleton"><span></span><span></span><span></span></div>';
  if (!sheet.open) sheet.showModal();
  try {
    const detail = await api('card?id=' + Number(id));
    if (!detail.card) { sheet.close(); toast('这个词已被移除', true); return; }
    sheetCard = detail.card;
    const result = await api('explain', {query:detail.card.word, context:detail.card.context, source:detail.card.source});
    sheetResult = result;
    renderSheet(detail, result);
  } catch (error) { $('#sheet-body').innerHTML = `<p class="error-text">${escapeHTML(error.message)}</p>`; }
}
function renderSheet(detail, result) {
  const card = detail.card, p = card.progress;
  $('#sheet-title').innerHTML = wordHeaderHTML(card.word, result.phonetic, `<span class="pill">${card.paused ? '已暂停' : STATE_LABEL[p.state]}</span>`);
  const facts = [
    p.is_new ? '还没开始复习' : `复习 ${p.reviews} 次 · 忘记 ${p.failures} 次`,
    card.paused ? '' : (new Date(card.due) <= new Date() ? '现在待复习' : `下次 ${dateLabel(card.due)}（${Study.intervalLabel(card.due)}）`),
    p.retrievability != null ? `现在记得的概率约 ${Math.round(p.retrievability * 100)}%` : '',
    p.stability ? `记忆稳定性 ${p.stability} 天` : '',
    `${dateLabel(card.created, {year:'numeric'})} 收录`,
  ].filter(Boolean);
  const history = detail.history.length ? `<div class="history" aria-label="复习记录">${detail.history.slice(-30).map(h => `<span class="dot-r r${h.rating}" title="${dateLabel(h.created)} · ${RATINGS[h.rating - 1][1]}"></span>`).join('')}</div>` : '';
  const contexts = detail.encounters.filter(e => e.context);
  $('#sheet-body').innerHTML = `<div class="facts">${facts.map(f => `<span>${escapeHTML(f)}</span>`).join('')}</div>${history}
    ${result.found ? explanationHTML(result.explanation, false, 'sheet', card.word) : `<p>${escapeHTML(card.meaning)}</p>`}
    ${contexts.length ? `<details class="fold" open><summary>你遇到它的地方<span class="muted">${contexts.length}</span></summary><div class="fold-body">${contexts.map(e => `<blockquote>${highlightWord(e.context, card.word)}${e.source ? `<cite>${escapeHTML(e.source)}</cite>` : ''}</blockquote>`).join('')}</div></details>` : ''}
    <form class="own-sentence" id="sheet-sentence"><label for="sheet-sentence-text">${icon('pen')}用它造个句子</label><div class="inline-field"><input id="sheet-sentence-text" maxlength="500" lang="en" placeholder="Write your own sentence…"><button class="button secondary" type="submit">保存</button></div></form>
    <div class="sheet-actions"><button class="button secondary" data-sheet-toggle="${card.id}">${icon(card.paused ? 'play' : 'pause')}${card.paused ? '恢复复习' : '暂停复习'}</button><button class="button ghost danger" data-sheet-delete="${card.id}">${icon('trash')}移除</button></div>`;
  bindFolds($('#sheet-body'));
}

// ------------------------------------------------------------------ settings
async function loadSettings() {
  const [info] = await Promise.all([api('info'), loadSpeechInfo().catch(() => { $('#speech-status').textContent = '本机语音暂时不可用。'; })]);
  settings = info.settings;
  renderSettings();
  $('#app-info').innerHTML = [
    ['词库', info.dictionary.current], ['中文学习词条', `${Number(info.dictionary.learner?.entries || 0).toLocaleString()} 条`],
    ['复习算法', info.algorithm], ['数据位置', info.data_dir], ['许可', 'Wiktionary / Open Dictionary · CC BY-SA 4.0'],
  ].map(([k, v]) => `<div><span class="muted">${k}</span><span>${escapeHTML(v)}</span></div>`).join('');
}
function renderSettings() {
  if (!settings) return;
  $('#setting-new').value = settings.new_per_day;
  $('#setting-goal').value = settings.daily_goal;
  $('#setting-minimum').value = settings.daily_minimum;
  $$('#setting-retention [data-retention]').forEach(b => b.setAttribute('aria-checked', String(Number(b.dataset.retention) === settings.retention)));
  $('#retention-note').textContent = {0.85:'复习最少，适合词很多的时候；忘得会多一些。', 0.9:'推荐。记忆效果和复习量比较平衡。', 0.95:'记得更牢，但复习量大约是 90% 时的两倍。'}[settings.retention] || '';
  $('#setting-typing').checked = settings.typing;
  applyTheme(themeChoice);
}
async function changeSetting(change) {
  try { settings = await api('settings', change); renderSettings(); refreshStats({force:true}).catch(() => {}); toast('已保存'); }
  catch (error) { toast(error.message, true); renderSettings(); }
}

// ------------------------------------------------------------------ events
document.addEventListener('click', async event => {
  const el = event.target.closest('button,[data-open-card],li[data-suggest],a[data-view]');
  if (!el) return;
  try {
    if (el.dataset.view) { event.preventDefault(); if ($('#card-sheet').open) $('#card-sheet').close(); return navigate(el.dataset.view); }
    if (el.dataset.suggest) return searchWord(el.dataset.suggest);
    if (el.dataset.search) return searchWord(el.dataset.search);
    if (el.dataset.token) { $('#query').value = el.dataset.token; return searchWord(el.dataset.token); }
    if (el.dataset.speak) return speakWord(el.dataset.speak, el.dataset.slow === 'true', el);
    if (el.dataset.editDefinition) return openDefinitionEditor(el.dataset.editDefinition);
    if (el.dataset.openCard) return openCard(el.dataset.openCard);
    if (el.dataset.rating) return submitRating(el.dataset.rating);
    if (el.dataset.close) return $('#' + el.dataset.close).close();
    if (el.dataset.filter) { libraryFilter = el.dataset.filter; $$('#library-filter [data-filter]').forEach(b => b.setAttribute('aria-selected', String(b === el))); return loadLibrary(); }
    if (el.dataset.adjust) return changeSetting(adjustedSetting(el.dataset.adjust, (settings?.[el.dataset.adjust] ?? 0) + Number(el.dataset.by)));
    if (el.dataset.extraNew) { el.disabled = true; renderStats(await api('extra-new', {count:Number(el.dataset.extraNew)})); return loadReview(); }
    if (el.dataset.retention) return changeSetting({retention:Number(el.dataset.retention)});
    if (el.dataset.themeChoice) { themeChoice = el.dataset.themeChoice; try { localStorage.setItem('leaf-theme', themeChoice); } catch {} return applyTheme(themeChoice); }
    if (el.dataset.chartDay && statsData) { const d = el.dataset.chartDay; $('#week-note').textContent = `${dateLabel(d + 'T12:00:00')}：${statsData.week[d]} 个不同的词，${statsData.week_attempts?.[d] ?? 0} 次练习`; return; }
    if (el.dataset.sheetToggle) {
      const data = await api('toggle', {id:Number(el.dataset.sheetToggle)}); renderStats(data.stats);
      await openCard(el.dataset.sheetToggle); if (currentView === 'library') loadLibrary(); return;
    }
    if (el.dataset.sheetDelete) {
      if (!await confirmAction('移除这个词？', '它的原句和复习记录也会一起移除，无法恢复。个人释义会保留。', '移除')) return;
      const data = await api('delete', {id:Number(el.dataset.sheetDelete)}); renderStats(data.stats);
      $('#card-sheet').close(); toast('已移除'); if (currentView === 'library') loadLibrary();
      if (currentResult?.saved_card?.id === Number(el.dataset.sheetDelete)) { currentResult.saved_card = null; renderResult(); }
      return;
    }
    switch (el.id) {
      case 'save-word': return saveCurrent();
      case 'clear-query': $('#query').value = ''; el.hidden = true; $('#search-result').innerHTML = ''; currentResult = null; showHome(true); hideSuggestions(); updateContextState(); $('#query').focus(); return;
      case 'context-toggle': setContextOpen($('#context-panel').hidden); if (!$('#context-panel').hidden) $('#context').focus(); return;
      case 'retry-query': return searchWord($('#query').value);
      case 'reveal': return revealAnswer();
      case 'context-hint': $('#review-hint').hidden = !$('#review-hint').hidden; return;
      case 'cloze-check': return checkCloze();
      case 'cloze-hint': return useHint();
      case 'cloze-giveup': return review.card?.typing ? checkCloze(true) : (review.suggested = 1, revealAnswer());
      case 'review-now': return loadReview();
      case 'retry-review': return loadReview();
      case 'retry-library': return loadLibrary();
      case 'reset-library': $('#library-search').value = ''; libraryFilter = 'all'; $$('#library-filter [data-filter]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.filter === 'all'))); return loadLibrary();
      case 'library-more': return showMoreLibrary();
      case 'definition-cancel': if (!definitionBusy) $('#definition-dialog').close(); return;
      case 'definition-restore': return persistDefinition(true);
      case 'import-button': return $('#import-file').click();
      case 'quit-button':
        if (await confirmAction('退出 Leaf？', '停止本地服务后可以关闭这个窗口。下次双击 Leaf 即可重新打开。', '退出')) {
          await api('quit', {});
          document.body.innerHTML = '<div class="farewell"><div class="glass strong done"><h2>学习记录已保存</h2><p class="muted">本地服务已停止，可以关闭这个窗口了。</p></div></div>';
        }
        return;
    }
  } catch (error) { toast(error.message, true); }
});
$('#search-form').addEventListener('submit', event => {
  event.preventDefault();
  if (suggestionIndex >= 0 && suggestions[suggestionIndex]) return searchWord(suggestions[suggestionIndex].word);
  searchWord($('#query').value);
});
$('#query').addEventListener('input', () => { $('#clear-query').hidden = !$('#query').value; lookupRequest.cancel(); scheduleSuggestions(); });
$('#query').addEventListener('paste', event => {
  const text = event.clipboardData?.getData('text') || '';
  if (Study.looksLikePassage(text)) { event.preventDefault(); placePassage(text); }
});
$('#query').addEventListener('keydown', event => {
  if (!suggestions.length || $('#suggestions').hidden) return;
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    const n = suggestions.length;
    suggestionIndex = event.key === 'ArrowDown' ? (suggestionIndex + 1) % n : (suggestionIndex - 1 + n) % n;
    renderSuggestions();
  } else if (event.key === 'Escape') { event.stopPropagation(); hideSuggestions(); }
});
$('#query').addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== $('#query')) hideSuggestions(); }, 150));
$('#query').addEventListener('focus', () => $('#query').select());
$('#suggestions').addEventListener('mousedown', event => event.preventDefault());
$('#context').addEventListener('input', () => { clearTimeout($('#context').t); $('#context').t = setTimeout(updateContextState, 200); });
$('#definition-form').addEventListener('submit', event => { event.preventDefault(); persistDefinition(); });
$('#definition-text').addEventListener('input', updateDefinitionInput);
$('#definition-dialog').addEventListener('cancel', event => { if (definitionBusy) event.preventDefault(); });
$('#definition-dialog').addEventListener('close', () => { definitionEditor = null; });
$('#card-sheet').addEventListener('close', () => { sheetCard = null; sheetResult = null; stopSpeech(); });
$('#card-sheet').addEventListener('click', event => { if (event.target === $('#card-sheet')) $('#card-sheet').close(); });
document.addEventListener('submit', async event => {
  if (event.target.id === 'own-sentence' || event.target.id === 'sheet-sentence') {
    event.preventDefault();
    try { await saveOwnSentence(event.target); } catch (error) { toast(error.message, true); }
  }
});
let libraryTimer;
$('#library-search').addEventListener('input', () => { libraryRequest.cancel(); clearTimeout(libraryTimer); libraryTimer = setTimeout(() => { if (currentView === 'library') loadLibrary().catch(e => toast(e.message, true)); }, 160); });
$('#library-sort').addEventListener('change', () => loadLibrary());
// Keep the minimum at or below the goal, whichever one is changed.
function adjustedSetting(key, value) {
  const limits = {new_per_day:[0, 100], daily_goal:[1, 500], daily_minimum:[1, 500]};
  const [low, high] = limits[key];
  value = Math.max(low, Math.min(high, Math.round(Number(value) || 0)));
  if (key === 'daily_goal' && value < (settings?.daily_minimum ?? 1)) return {daily_goal:value, daily_minimum:value};
  if (key === 'daily_minimum' && value > (settings?.daily_goal ?? 500)) return {daily_minimum:value, daily_goal:value};
  return {[key]:value};
}
$$('[data-setting]').forEach(input => input.addEventListener('change', event => changeSetting(adjustedSetting(event.target.dataset.setting, event.target.value))));
$('#setting-typing').addEventListener('change', event => changeSetting({typing:event.target.checked}));
$('#speech-accent').addEventListener('change', event => { stopSpeech(); speechAccent = event.target.value; try { localStorage.setItem('leaf-speech-accent', speechAccent); } catch {} });
$('#import-file').addEventListener('change', async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    if (file.size > 15_000_000) throw new Error('备份文件过大。');
    const data = JSON.parse(await file.text());
    if (data.app !== 'leaf-offline-dictionary-v1') throw new Error('请选择 Leaf 导出的备份文件。');
    if (await confirmAction('合并这份备份？', '同一个词只保留一条，原句和历史记录合并，本机已有的复习进度和个人释义优先。', '合并')) {
      const result = await api('import', data); await refreshStats({force:true}); toast(`已导入 ${result.imported} 个词`);
    }
  } catch (error) { toast(error instanceof SyntaxError ? '文件不是有效的备份。' : error.message, true); }
  finally { event.target.value = ''; }
});
window.addEventListener('pagehide', stopSpeech);
window.addEventListener('hashchange', () => { const v = location.hash.slice(1); if (v !== currentView) navigate(v); });

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') stopSpeech();
  if (event.repeat || anyDialogOpen()) return;
  const mod = event.ctrlKey || event.metaKey;
  if (mod && event.key.toLowerCase() === 'z' && lastRated && !inField()) { event.preventDefault(); undoLastRating().catch(e => toast(e.message, true)); return; }
  if (currentView === 'review' && review.card) {
    if (document.activeElement?.id === 'cloze-input' && event.key === 'Enter') { event.preventDefault(); checkCloze(); return; }
    if (inField() || mod || event.altKey) return;
    if (event.code === 'Space' && document.activeElement?.tagName !== 'BUTTON') { event.preventDefault(); if (review.card.mode === 'cloze' && review.card.typing) $('#cloze-input')?.focus(); else revealAnswer(); return; }
    if (['1', '2', '3', '4'].includes(event.key)) { submitRating(event.key); return; }
    if (event.key === 'Enter' && review.shown && review.suggested && document.activeElement?.tagName !== 'BUTTON') { event.preventDefault(); submitRating(review.suggested); return; }
    if (event.key.toLowerCase() === 'h') { useHint(); return; }
    if (event.key.toLowerCase() === 'p' && (review.card.mode !== 'cloze' || review.shown)) { $('#review-content [data-speak]')?.click(); return; }
  }
  if (inField() || mod || event.altKey) return;
  if (event.key === '/') { event.preventDefault(); navigate('lookup').then(() => $('#query').focus()); }
  else if (event.key.toLowerCase() === 'r' && currentView !== 'review') navigate('review');
  else if (event.key.toLowerCase() === 's' && currentView === 'lookup' && currentResult) saveCurrent();
  else if (event.key.toLowerCase() === 'p' && currentView === 'lookup' && currentResult) $('#search-result [data-speak]')?.click();
});

// ------------------------------------------------------------------ start
decorate();
api('settings').then(data => { settings = data; }).catch(() => {});
loadSpeechInfo().catch(() => {});
navigate(location.hash.slice(1) || 'lookup');
setInterval(() => { if (!document.hidden && !review.busy) refreshStats().catch(() => {}); }, 60000);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  refreshStats().then(() => { if (currentView === 'review' && !review.card && !review.loading && statsData?.due) loadReview(); }).catch(() => {});
});
