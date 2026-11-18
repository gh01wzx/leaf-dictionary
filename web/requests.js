'use strict';

// Read requests may be superseded. Mutations always finish independently.
globalThis.LeafRequests = (() => {
  function createClient(token, fetcher = globalThis.fetch.bind(globalThis)) {
    return async (path, payload, signal) => {
      const options = {signal};
      if (payload !== undefined) Object.assign(options, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Leaf-Token': token},
        body: JSON.stringify(payload)
      });
      let response;
      try { response = await fetcher('/api/' + path, options); }
      catch (error) {
        if (error.name === 'AbortError') throw error;
        throw new Error('暂时无法连接词典，请重新打开 Leaf 后再试。');
      }
      let data;
      try { data = await response.json(); }
      catch (error) {
        if (error.name === 'AbortError') throw error;
        throw new Error('词典返回的内容不完整，请重试。');
      }
      if (!response.ok) {
        const error = new Error(data.error || '操作没有完成，请重试。');
        error.status = response.status;
        throw error;
      }
      return data;
    };
  }

  class LatestRequest {
    constructor() { this.generation = 0; this.controller = null; }
    cancel() { this.controller?.abort(); this.controller = null; this.generation++; }
    start() {
      this.cancel();
      this.controller = new AbortController();
      const generation = this.generation;
      return {signal: this.controller.signal, current: () => generation === this.generation};
    }
  }
  return {createClient, LatestRequest};
})();
