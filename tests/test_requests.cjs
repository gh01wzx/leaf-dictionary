const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({AbortController, fetch});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../web/requests.js'), 'utf8'), context);
const {LatestRequest, createClient} = context.LeafRequests;

test('starting a new lookup aborts the old request and invalidates late results', () => {
  const lane = new LatestRequest();
  const old = lane.start();
  const latest = lane.start();
  assert.equal(old.signal.aborted, true);
  assert.equal(old.current(), false);
  assert.equal(latest.current(), true);
  assert.equal(latest.signal.aborted, false);
});
test('typing or navigation invalidates an outstanding result before the next request', () => {
  const lane = new LatestRequest();
  const pending = lane.start();
  lane.cancel();
  assert.equal(pending.current(), false);
  assert.equal(pending.signal.aborted, true);
});
test('manual save has a token and no cancellation from read requests', async () => {
  let captured;
  const api = createClient('local-token', async (url, options) => {
    captured = {url, options};
    return {ok: true, json: async () => ({saved: true})};
  });
  const value = await api('explain', {query: 'field', save: true});
  assert.equal(value.saved, true);
  assert.equal(captured.url, '/api/explain');
  assert.equal(captured.options.headers['X-Leaf-Token'], 'local-token');
  assert.equal(captured.options.method, 'POST');
  assert.equal(JSON.parse(captured.options.body).save, true);
  assert.equal(captured.options.signal, undefined);
});
test('abort signals are forwarded and cancellation stays recognizable', async () => {
  const lane = new LatestRequest();
  const pending = lane.start();
  const api = createClient('', async (_, options) => {
    assert.equal(options.signal, pending.signal);
    const error = new Error('cancelled'); error.name = 'AbortError'; throw error;
  });
  await assert.rejects(api('library', undefined, pending.signal), {name:'AbortError'});
});
test('server messages remain actionable; connection errors have a readable message', async () => {
  const failed = createClient('', async () => ({ok:false,json:async () => ({error:'保存失败'})}));
  await assert.rejects(failed('explain',{}), /保存失败/);
  const offline = createClient('', async () => { throw new TypeError('Failed to fetch'); });
  await assert.rejects(offline('stats'), /重新打开 Leaf/);
});
