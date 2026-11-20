const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'web', 'study.js'), 'utf8'), context);
const Study = context.LeafStudy;
const cloze = {answer: 'exerted', accept: ['exerted', 'exert', 'exerts', 'exerting']};

test('exact form in the sentence is correct, ignoring case, spaces and curly quotes', () => {
  assert.equal(Study.checkAnswer('  Exerted ', cloze).result, 'correct');
  assert.equal(Study.checkAnswer('don’t', {answer: "don't", accept: ["don't"]}).result, 'correct');
});

test('another form of the right word is recognised separately from a spelling slip', () => {
  assert.equal(Study.checkAnswer('exerts', cloze).result, 'form');
  assert.equal(Study.checkAnswer('exerded', cloze).result, 'close');
  assert.equal(Study.checkAnswer('excited', cloze).result, 'wrong');
  assert.equal(Study.checkAnswer('', cloze).result, 'empty');
});

test('short words tolerate only one slip', () => {
  const short = {answer: 'aide', accept: ['aide']};
  assert.equal(Study.checkAnswer('aid', short).result, 'close');
  assert.equal(Study.checkAnswer('ai', short).result, 'wrong');
});

test('suggested ratings follow how the recall went', () => {
  assert.equal(Study.suggestedRating('correct', false), 3);
  assert.equal(Study.suggestedRating('correct', true), 2);
  assert.equal(Study.suggestedRating('form', false), 2);
  assert.equal(Study.suggestedRating('close', false), 2);
  assert.equal(Study.suggestedRating('wrong', false), 1);
});

test('hints reveal letters one at a time and keep spaces', () => {
  assert.equal(Study.hint('take off', 1), 't··· ···');
  assert.equal(Study.hint('take off', 5), 'take o··');
});

test('interval labels are readable', () => {
  const now = Date.parse('2026-11-18T10:00:00Z');
  assert.equal(Study.intervalLabel('2026-11-18T10:00:30Z', now), '1 分钟后');
  assert.equal(Study.intervalLabel('2026-11-18T10:10:00Z', now), '10 分钟后');
  assert.equal(Study.intervalLabel('2026-11-19T10:00:00Z', now), '明天');
  assert.equal(Study.intervalLabel('2026-11-25T10:00:00Z', now), '7 天后');
  assert.equal(Study.intervalLabel('2027-02-18T10:00:00Z', now), '3 个月后');
});

test('goals never hide continuation; only the available word pool limits a batch', () => {
  const stats = {total:915, active:915, goal:{met_goal:true}, queue:{ready:0, new_total:854, new_left:0}};
  assert.equal(Study.reviewPlan(stats).batch, 10);
  assert.equal(Study.reviewPlan(stats).title, '目标达成，想学就继续');
  stats.goal.met_goal = false;
  assert.equal(Study.reviewPlan(stats).batch, 10);
  stats.queue.new_total = 4;
  assert.equal(Study.reviewPlan(stats).batch, 4);
  stats.queue.new_left = 4;
  assert.equal(Study.reviewPlan(stats).batch, 0);
  stats.queue.ready = 4;
  assert.equal(Study.reviewPlan(stats).title, '继续学习');
  stats.active = 0;
  assert.equal(Study.reviewPlan(stats).title, '生词都已暂停');
  stats.total = 0;
  assert.equal(Study.reviewPlan(stats).title, '从阅读里带回第一个词');
});

test('idle refresh respects actual due time and the study-day boundary', () => {
  const stats = {as_of:'2026-11-20T10:00:00Z', queue:{next_due:'2026-11-20T10:00:20Z'}, day_ends_at:'2026-11-20T15:00:00Z'};
  assert.equal(Study.nextRefreshDelay(stats), 20250);
  stats.queue.next_due = '2026-11-21T10:00:00Z';
  assert.equal(Study.nextRefreshDelay(stats), 60000);
  stats.day_ends_at = '2026-11-20T10:00:03Z';
  assert.equal(Study.nextRefreshDelay(stats), 3250);
  stats.queue.next_due = '2026-11-20T09:00:00Z';
  assert.equal(Study.nextRefreshDelay(stats), 1000, 'never spin in an immediate request loop');
});

test('pasted passages are detected and split into clickable words', () => {
  assert.equal(Study.looksLikePassage('take off'), false);
  assert.equal(Study.looksLikePassage('put up with'), false);
  assert.equal(Study.looksLikePassage('a storm in a teacup'), false);
  assert.equal(Study.tokens('ménage, déjà vu.')[0].text, 'ménage');
  assert.equal(Study.looksLikePassage('Her choices are informed by years of experience.'), true);
  const parts = Study.tokens("It's informed, isn't it?");
  assert.equal(JSON.stringify(parts.filter(p => p.word).map(p => p.text)), JSON.stringify(["It's", 'informed', "isn't", 'it']));
  assert.equal(parts.map(p => p.text).join(''), "It's informed, isn't it?");
});
