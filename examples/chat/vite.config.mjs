import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { handle } from './api/chat.mjs';

// The API route rides the dev server so `npm run dev` is the whole app. In
// production this is one route handler in whatever framework you deploy.
const api = {
  name: 'chat-api',
  configureServer(server) {
    server.middlewares.use('/api/chat', (req, res, next) => {
      if (req.method !== 'POST') return next();
      handle(req, res).catch((err) => { console.error(err); res.statusCode = 500; res.end(String(err)); });
    });
  },
};

export default defineConfig({
  plugins: [react(), api],
  server: { port: 5173, strictPort: true },
});
