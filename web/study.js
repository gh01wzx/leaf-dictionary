'use strict';
// Pure review helpers shared by the page and the Node tests. No DOM access here.
globalThis.LeafStudy = (() => {
  const clean = value => String(value ?? '').normalize('NFKC').replace(/[’‘`]/g, "'")
    .replace(/\s+/g, ' ').trim().toLowerCase();

  function distance(a, b) {
    if (a === b) return 0;
    const row = Array.from({length: b.length + 1}, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      let previous = row[0]; row[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const saved = row[j];
        row[j] = Math.min(row[j] + 1, row[j - 1] + 1, previous + (a[i - 1] === b[j - 1] ? 0 : 1));
        previous = saved;
      }
    }
    return row[b.length];
  }

  // correct: the exact form in the sentence; form: right word, other inflection;
  // close: a small slip (one or two letters); wrong: anything else.
  function checkAnswer(input, cloze) {
    const typed = clean(input);
    if (!typed) return {result: 'empty'};
    const answer = clean(cloze.answer);
    if (typed === answer) return {result: 'correct'};
    if ((cloze.accept || []).some(form => clean(form) === typed)) return {result: 'form'};
    // One slip for ordinary words, two only for long ones, so a different word is not accepted.
    const allowed = answer.length >= 9 ? 2 : 1;
    if (distance(typed, answer) <= allowed) return {result: 'close'};
    return {result: 'wrong'};
  }

  // Produce-the-word is harder than recognition, so a correct answer counts as
  // "记得"; a hint or a slip counts as "费力想起"; failure is "忘了".
  function suggestedRating(result, usedHint) {
    if (result === 'correct') return usedHint ? 2 : 3;
    if (result === 'form' || result === 'close') return 2;
    return 1;
  }

  function hint(answer, level) {
    const letters = [...String(answer)];
    let shown = 0;
    return letters.map(ch => {
      if (!/[A-Za-z]/.test(ch)) return ch;
      shown++;
      return shown <= level ? ch : '·';
    }).join('');
  }

  function intervalLabel(dueISO, nowMs = Date.now()) {
    const minutes = Math.max(0, (Date.parse(dueISO) - nowMs) / 60000);
    if (minutes < 1.5) return '1 分钟后';
    if (minutes < 60) return `${Math.round(minutes)} 分钟后`;
    const hours = minutes / 60;
    if (hours < 22) return `${Math.round(hours)} 小时后`;
    const days = hours / 24;
    if (days < 1.5) return '明天';
    if (days < 31) return `${Math.round(days)} 天后`;
    if (days < 365) return `${Math.round(days / 30)} 个月后`;
    return `${(days / 365).toFixed(1)} 年后`;
  }

  // Goals describe progress; they never restrict the next learning session.
  function reviewPlan(stats) {
    const q = stats.queue, g = stats.goal;
    const ready = q.ready ?? q.due ?? 0;
    const batch = Math.min(10, Math.max(0, q.new_total - q.new_left));
    return {
      ready, batch,
      title: !stats.total ? '从阅读里带回第一个词'
        : !stats.active ? '生词都已暂停'
        : ready ? '继续学习'
        : g.met_goal ? '目标达成，想学就继续'
        : q.later_today ? '这一轮完成了'
        : '当前到期的词学完了',
      description: !stats.total ? '查词后点“加入生词本”，就能开始学习。'
        : !stats.active ? '在生词本恢复想学的词，它们就会重新进入安排。'
        : g.met_goal ? '每日目标已经完成，继续学多少由你决定。'
        : '每个词按自己的时间安排回来，不需要为了凑数提前复习。'
    };
  }

  function nextRefreshDelay(stats) {
    const now = Date.parse(stats.as_of);
    const moments = [stats.queue.next_due, stats.day_ends_at].filter(Boolean).map(Date.parse);
    const delay = Math.min(60000, ...moments.map(due => due - now + 250));
    return Number.isFinite(delay) ? Math.max(1000, delay) : 60000;
  }

  // Split a pasted passage into clickable English words.
  function tokens(text) {
    const parts = [];
    const pattern = /\p{Script=Latin}[\p{Script=Latin}\p{M}]*(?:['’-]\p{Script=Latin}[\p{Script=Latin}\p{M}]*)*/gu;
    let index = 0, match;
    while ((match = pattern.exec(text))) {
      if (match.index > index) parts.push({text: text.slice(index, match.index), word: false});
      parts.push({text: match[0], word: true});
      index = match.index + match[0].length;
    }
    if (index < text.length) parts.push({text: text.slice(index), word: false});
    return parts;
  }

  function looksLikePassage(text) {
    const value = String(text).trim();
    const words = value.split(/\s+/).length;
    return value.length > 120 || words >= 9 || (words > 1 && /[.!?;:。！？\n]/.test(value));
  }

  return {clean, distance, checkAnswer, suggestedRating, hint, intervalLabel, reviewPlan, nextRefreshDelay, tokens, looksLikePassage};
})();
