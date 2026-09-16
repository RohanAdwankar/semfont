// The chat route. One model call per request, streamed back in the AI SDK's
// UI message protocol, which is what useChat on the client consumes.
//
// The provider is anything that speaks the OpenAI chat completions API.
// OpenRouter by default; point LLM_BASE_URL at mock/server.mjs to run the
// whole app with no key and no network.

import { streamText, convertToModelMessages } from 'ai';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

const provider = createOpenAICompatible({
  name: 'openrouter',
  baseURL: process.env.LLM_BASE_URL ?? 'https://openrouter.ai/api/v1',
  apiKey: process.env.OPENROUTER_API_KEY ?? 'mock',
});

const MODEL = process.env.LLM_MODEL ?? 'openai/gpt-oss-120b';

/** @param {import('ai').UIMessage[]} messages */
export async function chat(messages) {
  return streamText({
    model: provider(MODEL),
    messages: await convertToModelMessages(messages),
  });
}

/** Node adapter: read the JSON body, stream the reply into the response. */
export async function handle(req, res) {
  let body = '';
  for await (const chunk of req) body += chunk;
  const { messages } = JSON.parse(body);
  const result = await chat(messages);
  await result.pipeUIMessageStreamToResponse(res);
}
