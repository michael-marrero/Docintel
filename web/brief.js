// docintel — brief streaming (Story 2.2). Opens the SSE brief stream and
// dispatches section/done/refused events to caller-supplied handlers. The DOM
// rendering lives in app.js; this module owns only the stream lifecycle.
//
// SSE auto-reconnects when the server closes the connection — after `done`/
// `refused` we close() AND set a `finished` flag so the natural end-of-stream
// EOF (which surfaces as onerror) does NOT trigger a reconnect that would
// re-run brief generation.

export function streamBrief(ticker, { onSection, onDone, onRefused, onError } = {}) {
  const es = new EventSource(`/brief/${encodeURIComponent(ticker)}`);
  let finished = false;

  const stop = () => {
    finished = true;
    es.close();
  };

  es.addEventListener("section", (e) => {
    try {
      onSection?.(JSON.parse(e.data));
    } catch (err) {
      onError?.(err);
    }
  });
  es.addEventListener("done", (e) => {
    let data = null;
    try {
      data = JSON.parse(e.data);
    } catch (err) {
      onError?.(err);
    }
    stop();
    onDone?.(data);
  });
  es.addEventListener("refused", (e) => {
    let data = null;
    try {
      data = JSON.parse(e.data);
    } catch (err) {
      onError?.(err);
    }
    stop();
    onRefused?.(data);
  });
  es.onerror = () => {
    if (finished) return; // normal end-of-stream after done/refused — ignore
    stop();
    onError?.(new Error("brief stream failed"));
  };

  return es;
}
