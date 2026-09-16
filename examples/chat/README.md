# semfont chat

A chat page where the reply is set by semfont as it streams in. Vite, React,
the [AI SDK](https://ai-sdk.dev) for the stream, and any model that speaks the
OpenAI chat completions API. OpenRouter by default.

```bash
npm install
OPENROUTER_API_KEY=sk-or-... npm run dev      # http://localhost:5173
```

`LLM_MODEL` picks the model, default `openai/gpt-oss-120b`. `LLM_BASE_URL`
points the provider somewhere else, including the mock below.

## Without a key

`mock/server.mjs` is a model stand-in that speaks the same API, streaming
included, so the app runs through the same provider code and cannot tell the
difference:

```bash
npm run mock                                   # :8787
LLM_BASE_URL=http://localhost:8787/v1 npm run dev
```

## The three files that matter

- `api/chat.mjs` streams one model call back in the AI SDK's UI message
  protocol. It is one route handler in whatever you deploy on.
- `src/App.jsx` is `useChat` plus `SemanticText` around the text of each
  assistant message. Every chunk re-runs the engine on the message so far.
- `mock/server.mjs` is the stand-in model.

The page renders each reply twice, plain and set, so the difference is the
only thing on screen. A real app renders the right-hand column alone.
