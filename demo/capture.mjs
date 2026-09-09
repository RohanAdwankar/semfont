#!/usr/bin/env node
//
// Record demo/demo.gif and demo/demo.mp4 from demo/capture.html.
//
//   node demo/capture.mjs gif
//   node demo/capture.mjs video
//
// The stage holds one state per frame and exposes seek(i) with no timers in
// it, so this walks the frame indices, screenshots each one, and encodes the
// sequence. Nothing is captured in real time and nothing waits on a clock,
// which is what makes a second run produce the same bytes as the first.
//
// Needs Playwright and a Chromium build, plus an ffmpeg with libx264 and the
// gif encoder. Both are resolved below from whatever the machine has.

import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const DEMO = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(DEMO);
const FONT_DIR = path.join(DEMO, '.fonts');
const FONT_FILE = path.join(FONT_DIR, 'robotoflex.woff2');
const PORT = 8731;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.woff2': 'font/woff2',
};

/* ------------------------------------------------------------ the font */

// Roboto Flex, the same variable face demo/index.html loads. The recording
// browser runs without a route to fonts.gstatic.com, so the file is fetched
// once here and served from disk. demo/.fonts/ is ignored by git: it is a
// build input, not a source file, and the licence for redistributing the
// face is not this repository's to grant.
const FONT_CSS =
  'https://fonts.googleapis.com/css2?family=Roboto+Flex:opsz,slnt,wght@8..144,-10..0,100..1000';
const FONT_UA =
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

async function ensureFont() {
  try {
    const stat = await fs.stat(FONT_FILE);
    if (stat.size > 10_000) return;
  } catch { /* not cached yet */ }

  process.stderr.write('fetching Roboto Flex (cached in demo/.fonts/)\n');
  const css = await (await fetch(FONT_CSS, { headers: { 'user-agent': FONT_UA } })).text();

  // The stylesheet is one @font-face per unicode subset. The latin block is
  // the one that covers this copy, and it is the only one worth 60 KB.
  const latin = css
    .split('@font-face')
    .slice(1)
    .find((block) => /unicode-range:[^;]*U\+0000-00FF/.test(block));
  if (!latin) throw new Error('no latin subset in the Google Fonts response');

  const url = latin.match(/url\((https:[^)]+)\)/)?.[1];
  if (!url) throw new Error('no woff2 url in the latin @font-face block');

  const body = Buffer.from(await (await fetch(url, { headers: { 'user-agent': FONT_UA } })).arrayBuffer());
  await fs.mkdir(FONT_DIR, { recursive: true });
  await fs.writeFile(FONT_FILE, body);
}

/* ----------------------------------------------------------- the tools */

/**
 * Find Playwright, whether it is a dependency of this repo or installed
 * globally. Node does not search the global root, so a globally installed
 * copy has to be pointed at by path.
 */
function resolvePlaywright() {
  const require = createRequire(import.meta.url);
  const names = ['playwright', 'playwright-core', '@playwright/test'];

  for (const id of names) {
    try { return require.resolve(id); } catch { /* not local */ }
  }

  const globalRoots = [
    path.join(path.dirname(process.execPath), '..', 'lib', 'node_modules'),
    ...(process.env.NODE_PATH ?? '').split(path.delimiter).filter(Boolean),
  ];
  for (const root of globalRoots) {
    for (const id of names) {
      const entry = path.join(root, id, 'index.mjs');
      if (existsSync(entry)) return pathToFileURL(entry).href;
    }
  }

  throw new Error('Playwright not found. npm i -D playwright, or install it globally.');
}

async function resolveFfmpeg() {
  if (process.env.FFMPEG) return process.env.FFMPEG;
  try {
    const mod = await import('ffmpeg-static');
    if (mod.default) return mod.default;
  } catch { /* not installed; fall back to whatever is on PATH */ }
  return 'ffmpeg';
}

function run(bin, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(bin, args, { stdio: ['ignore', 'ignore', 'pipe'] });
    let err = '';
    child.stderr.on('data', (d) => { err += d; });
    child.on('error', reject);
    child.on('close', (code) => (code === 0 ? resolve() : reject(new Error(err.slice(-2000)))));
  });
}

/* ---------------------------------------------------------- the capture */

async function serve() {
  const server = createServer(async (req, res) => {
    const url = decodeURIComponent(req.url.split('?')[0]);
    const file = url === '/__font/robotoflex.woff2'
      ? FONT_FILE
      : path.join(ROOT, path.normalize(url).replace(/^(\.\.[/\\])+/, ''));
    try {
      const body = await fs.readFile(file);
      res.writeHead(200, {
        'content-type': MIME[path.extname(file)] ?? 'application/octet-stream',
        'cache-control': 'no-store',
      });
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end();
    }
  });
  await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
  return server;
}

async function capture(mode, framesDir) {
  const { chromium } = await import(resolvePlaywright());
  const server = await serve();
  const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--font-render-hinting=none'] });

  try {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 720 },
      deviceScaleFactor: 2,
      colorScheme: 'light',
      reducedMotion: 'reduce',
    });
    // A throw inside the stage would otherwise show up as a frame that quietly
    // stopped changing, which is very hard to spot in 2,000 stills.
    let pageError = null;
    page.on('pageerror', (e) => { pageError ??= e; });

    await page.goto(`http://127.0.0.1:${PORT}/demo/capture.html?mode=${mode}`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.READY === true, null, { timeout: 30_000 });

    const stage = await page.evaluate(() => window.STAGE);
    const frames = await page.evaluate(() => window.FRAMES);
    await page.setViewportSize({ width: stage.width, height: stage.height });

    const clip = { x: 0, y: 0, width: stage.width, height: stage.height };
    for (let i = 0; i < frames; i += 1) {
      await page.evaluate((n) => window.seek(n), i);
      await page.screenshot({
        path: path.join(framesDir, `f${String(i).padStart(5, '0')}.png`),
        clip,
        animations: 'disabled',
      });
      if (pageError) throw pageError;
      if (i % 60 === 0) process.stderr.write(`  frame ${i}/${frames}\r`);
    }
    process.stderr.write(`  ${frames} frames                 \n`);
    return { ...stage, frames };
  } finally {
    await browser.close();
    server.close();
  }
}

/* ----------------------------------------------------------- the encode */

async function encodeGif(ffmpeg, framesDir, stage, out) {
  const palette = path.join(framesDir, 'palette.png');
  const input = ['-framerate', String(stage.fps), '-i', path.join(framesDir, 'f%05d.png')];

  // Two passes. A palette generated across the whole clip rather than per
  // frame is what keeps the accent colours from shifting between scenes,
  // and it is a large part of why the file is small.
  await run(ffmpeg, [
    '-y', '-loglevel', 'error', ...input,
    '-vf', `scale=${stage.width}:-1:flags=lanczos,palettegen=max_colors=128:stats_mode=diff`,
    palette,
  ]);
  await run(ffmpeg, [
    '-y', '-loglevel', 'error', ...input, '-i', palette,
    '-lavfi', `scale=${stage.width}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle`,
    '-loop', '0', out,
  ]);
}

async function encodeVideo(ffmpeg, framesDir, stage, out) {
  await run(ffmpeg, [
    '-y', '-loglevel', 'error',
    '-framerate', String(stage.fps),
    '-i', path.join(framesDir, 'f%05d.png'),
    // A silent track, because several upload paths reject or mangle a file
    // that has no audio stream at all. There is no narration.
    '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
    '-shortest',
    // Frames are grabbed at 2x and resolved down here, which is the cheapest
    // antialiasing available and matters a lot for type this small.
    '-vf', `scale=${stage.width}:${stage.height}:flags=lanczos`,
    '-c:v', 'libx264', '-preset', 'veryslow', '-crf', '20',
    '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-level', '4.0',
    '-c:a', 'aac', '-b:a', '64k',
    '-movflags', '+faststart',
    out,
  ]);
}

/* -------------------------------------------------------------- the run */

const mode = process.argv[2];
if (mode !== 'gif' && mode !== 'video') {
  process.stderr.write('usage: node demo/capture.mjs gif|video\n');
  process.exit(2);
}

const out = path.join(DEMO, mode === 'gif' ? 'demo.gif' : 'demo.mp4');
const framesDir = await fs.mkdtemp(path.join(DEMO, '.frames-'));

try {
  await ensureFont();
  process.stderr.write(`capturing ${mode}\n`);
  const stage = await capture(mode, framesDir);
  const ffmpeg = await resolveFfmpeg();
  process.stderr.write('encoding\n');
  if (mode === 'gif') await encodeGif(ffmpeg, framesDir, stage, out);
  else await encodeVideo(ffmpeg, framesDir, stage, out);

  const { size } = await fs.stat(out);
  const seconds = (stage.frames / stage.fps).toFixed(1);
  process.stderr.write(
    `${path.relative(ROOT, out)}  ${stage.width}x${stage.height}  ${seconds}s  ${(size / 1024).toFixed(0)} KB\n`,
  );
} finally {
  await fs.rm(framesDir, { recursive: true, force: true });
}
