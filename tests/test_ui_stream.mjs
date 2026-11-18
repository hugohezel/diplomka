import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../src/ui.js", import.meta.url), "utf8");

function streamReader() {
  const context = vm.createContext({
    document: {getElementById: () => ({value: "zenodo", addEventListener() {}})},
    fetch: () => new Promise(() => {}),
    TextDecoder,
  });
  vm.runInContext(source, context);
  return context.readEvaluationStream;
}

test("decodes split UTF-8 characters, split events, CRLF and a final line without a newline", async () => {
  const expected = [
    {event: "check_finished", check: {testId: "G2.2", message: "Priebežné výsledky — rieka"}},
    {event: "evaluation_finished", result: {}},
  ];
  const bytes = new TextEncoder().encode(`\r\n${expected.map((event) => JSON.stringify(event)).join("\r\n")}`);
  const body = new ReadableStream({
    start(controller) {
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
      controller.close();
    },
  });
  const actual = [];
  await streamReader()(new Response(body), (event) => actual.push(event));
  assert.equal(JSON.stringify(actual), JSON.stringify(expected));
});

test("delivers progress immediately, before the response finishes", async () => {
  let controller;
  const body = new ReadableStream({start(value) { controller = value; }});
  const events = [];
  let signalProgress;
  const progress = new Promise((resolve) => { signalProgress = resolve; });
  const reading = streamReader()(new Response(body), (event) => {
    events.push(event.event);
    signalProgress();
  });
  controller.enqueue(new TextEncoder().encode('{"event":"check_started","testId":"G2.2"}\n'));
  await progress;
  assert.deepEqual(events, ["check_started"]);
  controller.enqueue(new TextEncoder().encode('{"event":"evaluation_finished","result":{}}\n'));
  controller.close();
  await reading;
});

test("rejects an interrupted response instead of treating partial results as complete", async () => {
  await assert.rejects(
    streamReader()(new Response('{"event":"check_finished","check":{}}\n'), () => {}),
    /connection ended before all results arrived/,
  );
});

test("cancels the reader when the server reports an evaluation error", async () => {
  let cancelled = false;
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('{"event":"evaluation_error","error":"Upstream unavailable"}\n'));
    },
    cancel() { cancelled = true; },
  });
  await assert.rejects(streamReader()(new Response(body), (event) => {
    if (event.event === "evaluation_error") throw new Error(event.error);
  }), /Upstream unavailable/);
  assert.equal(cancelled, true);
});
