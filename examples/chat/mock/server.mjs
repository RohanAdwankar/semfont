// A stand-in for the model. It speaks the OpenAI chat completions API,
// streaming included, so the app talks to it through the same provider it
// uses for OpenRouter and cannot tell the difference. No key, no network.
//
//   node mock/server.mjs                  # listens on :8787
//   LLM_BASE_URL=http://localhost:8787/v1 npm run dev

import { createServer } from 'node:http';

const PORT = Number(process.env.PORT ?? 8787);
const DELAY_MS = Number(process.env.MOCK_DELAY_MS ?? 45);

const ANSWERS = [
  [/deploy|outage|fail/i,
   'The deploy failed because the migration dropped the sessions index before the new one existed. Traffic looked healthy for two minutes, then every login timed out and the error rate spiked. The rollback made it worse, since it replayed the same migration. What fixed it was recreating the index by hand. The staging run probably never exercised the login path, so the check passed and caught nothing.'],
  [/review|feedback/i,
   'The draft is clear and the argument holds. Two things are wrong: the benchmark table quotes the median where the text says mean, and the second figure has no axis labels. The conclusion is probably too strong for the sample size, but the core result is solid and worth publishing.'],
  [/.*/,
   'Short answer: yes, with one caveat. The approach works and is faster than the alternative, but it fails silently when the input is empty, so guard that case first. Everything else looked correct.'],
];

const sse = (res, obj) => res.write(`data: ${JSON.stringify(obj)}\n\n`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

createServer(async (req, res) => {
  if (req.method !== 'POST' || !req.url.endsWith('/chat/completions')) {
    res.writeHead(404).end();
    return;
  }
  let body = '';
  for await (const chunk of req) body += chunk;
  const { messages = [], stream = false, model = 'mock' } = JSON.parse(body || '{}');
  const last = [...messages].reverse().find((m) => m.role === 'user');
  const asked = typeof last?.content === 'string' ? last.content : last?.content?.map((c) => c.text ?? '').join('') ?? '';
  const answer = ANSWERS.find(([re]) => re.test(asked))[1];
  const id = 'chatcmpl-mock-' + Date.now();
  const created = Math.floor(Date.now() / 1000);

  if (!stream) {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ id, object: 'chat.completion', created, model, choices: [{ index: 0, message: { role: 'assistant', content: answer }, finish_reason: 'stop' }], usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 } }));
    return;
  }

  res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive' });
  const base = { id, object: 'chat.completion.chunk', created, model };
  sse(res, { ...base, choices: [{ index: 0, delta: { role: 'assistant', content: '' }, finish_reason: null }] });
  // Two words a chunk, roughly the cadence of a hosted model.
  const words = answer.split(/(?<=\s)/);
  for (let i = 0; i < words.length; i += 2) {
    await sleep(DELAY_MS);
    sse(res, { ...base, choices: [{ index: 0, delta: { content: words.slice(i, i + 2).join('') }, finish_reason: null }] });
  }
  sse(res, { ...base, choices: [{ index: 0, delta: {}, finish_reason: 'stop' }], usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 } });
  res.write('data: [DONE]\n\n');
  res.end();
}).listen(PORT, () => console.log(`mock model on http://localhost:${PORT}/v1`));
