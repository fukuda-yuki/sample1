// Render this local Markdown report and inspect it in a headless browser.
// No HTTP server, remote page or external asset is used.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';
import crypto from 'node:crypto';

const base = path.dirname(fileURLToPath(import.meta.url));
const option = name => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
};
const require = createRequire(import.meta.url);
const modules = option('--modules');
const load = async name => import(pathToFileURL(require.resolve(name, {paths: modules ? [modules, base] : [base]})).href);
const {marked} = await load('marked');
const playwrightModule = await load('playwright');
const {chromium} = playwrightModule.default;
const markdown = await fs.readFile(path.join(base, 'report.md'), 'utf8');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const css = `:root{color-scheme:light}body{margin:0;background:#f4f6f8;color:#203341;font-family:"Yu Gothic",Meiryo,sans-serif;font-size:16px;line-height:1.95}main{max-width:900px;margin:0 auto;background:white;padding:44px 48px 72px}h1{font-size:29px;line-height:1.5;margin:0 0 22px}h2{font-size:25px;line-height:1.6;margin-top:66px;padding-bottom:9px;border-bottom:2px solid #d6e2e9}h3{font-size:20px;line-height:1.65;margin-top:36px}p{margin:20px 0}a{color:#26648e;text-underline-offset:3px}strong{font-weight:700}table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.7;margin:22px 0}th{background:#edf3f7}td,th{padding:10px 12px;border:1px solid #d6e0e7;vertical-align:top}img{display:block;width:100%;height:auto;margin:30px 0 12px}code{background:#eff3f5;padding:1px 4px;border-radius:3px;font-size:.9em}@media(max-width:700px){main{padding:25px 17px}h1{font-size:24px}h2{font-size:22px}table{font-size:12px}td,th{padding:7px 6px}}`;
const html = `<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>仕様書内の不整合とAI実装：累計60予定枠の追加取得分析</title><style>${css}</style></head><body><main>${marked.parse(markdown, {gfm: true})}</main></body></html>`;
const preview = path.join(base, 'report.html');
await fs.writeFile(preview, html);
const checks = path.join(base, 'checks');
await fs.mkdir(path.join(checks, 'screenshots'), {recursive: true});
const browser = await chromium.launch({headless: true, channel: option('--channel') || 'msedge'});
const page = await browser.newPage({viewport: {width: 1100, height: 900}, deviceScaleFactor: 1});
const requests = [];
await page.route('**/*', route => {
  const url = route.request().url();
  if (/^https?:/i.test(url)) {requests.push(url); return route.abort();}
  return route.continue();
});
try {
  await page.goto(pathToFileURL(preview).href, {waitUntil: 'load'});
  await page.evaluate(() => document.fonts.ready);
  const state = await page.evaluate(() => ({
    title: document.querySelector('h1')?.textContent,
    h2: [...document.querySelectorAll('h2')].map(e => e.textContent),
    tables: document.querySelectorAll('table').length,
    images: [...document.images].map(e => ({alt:e.alt,loaded:e.complete && e.naturalWidth>0,width:e.clientWidth,naturalWidth:e.naturalWidth})),
    horizontalOverflow: document.documentElement.scrollWidth > innerWidth
  }));
  if (state.images.length !== 6 || state.images.some(e => !e.loaded) || state.horizontalOverflow || requests.length) {
    throw new Error(JSON.stringify({state,blockedRemoteRequests:requests}));
  }
  await page.screenshot({path:path.join(checks,'screenshots','01-opening.png')});
  await page.locator('table').nth(3).screenshot({path:path.join(checks,'screenshots','condition-statistics.png')});
  for (let i = 0; i < 6; i++) {
    await page.locator('img').nth(i).screenshot({path:path.join(checks,'screenshots',`figure-${i+1}-in-report.png`)});
  }
  for (const section of [2,4,5]) {
    await page.locator('h2').nth(section-1).evaluate(e => scrollTo(0,e.getBoundingClientRect().top+scrollY-24));
    await page.screenshot({path:path.join(checks,'screenshots',`section-${section}.png`)});
  }
  await page.setViewportSize({width:800,height:900});
  const narrow = await page.evaluate(() => ({width:innerWidth,horizontalOverflow:document.documentElement.scrollWidth>innerWidth,images:[...document.images].map(e=>e.clientWidth)}));
  if(narrow.horizontalOverflow) throw new Error('Horizontal overflow at 800px');
  await fs.writeFile(path.join(checks,'browser-render.json'),JSON.stringify({report_sha256:sha(markdown),preview_sha256:sha(html),renderer:'marked + Chromium (Playwright)',browser_version:browser.version(),state,narrow,remoteRequests:requests,scope:'Rendering this report only; no study app or evaluator was run.'},null,2)+'\n');
  process.stdout.write(JSON.stringify({images:state.images.length,tables:state.tables,headings:state.h2.length,horizontalOverflow:false,preview})+'\n');
} finally { await browser.close(); }

