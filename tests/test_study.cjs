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

test('pasted passages are detected and split into clickable words', () => {
  assert.equal(Study.looksLikePassage('take off'), false);
  assert.equal(Study.looksLikePassage('put up with'), false);
  assert.equal(Study.looksLikePassage('Her choices are informed by years of experience.'), true);
  const parts = Study.tokens("It's informed, isn't it?");
  assert.equal(JSON.stringify(parts.filter(p => p.word).map(p => p.text)), JSON.stringify(["It's", 'informed', "isn't", 'it']));
  assert.equal(parts.map(p => p.text).join(''), "It's informed, isn't it?");
});
