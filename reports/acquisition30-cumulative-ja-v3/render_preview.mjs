import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import crypto from 'node:crypto';

const base=path.dirname(fileURLToPath(import.meta.url));
const option=k=>{const i=process.argv.indexOf(k);return i<0?undefined:process.argv[i+1];};
const modules=option('--modules');const require=createRequire(import.meta.url);
const load=async name=>import(pathToFileURL(require.resolve(name,{paths:modules?[modules,base]:[base]})).href);
const {marked}=await load('marked');const {default:{chromium}}=await load('playwright');
const source=await fs.readFile(path.join(base,'report.md'),'utf8');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const body=marked.parse(source,{gfm:true}).replaceAll('<table>','<div class="table-scroll"><table>').replaceAll('</table>','</table></div>');
const css=`:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f2f5f7;color:#203441;font-family:"Yu Gothic",Meiryo,sans-serif;font-size:16px;line-height:1.95}main{max-width:1000px;margin:0 auto;background:#fff;padding:50px 56px 80px}h1{font-size:32px;line-height:1.5;margin:0 0 24px;letter-spacing:.02em}h2{font-size:26px;margin:68px 0 24px;padding-bottom:10px;border-bottom:2px solid #dce6ec;line-height:1.6}h3{font-size:21px;margin:42px 0 18px;line-height:1.6}p{margin:22px 0}a{color:#00699e;text-underline-offset:3px}strong{font-weight:700}img{display:block;width:100%;height:auto;margin:34px 0 12px}.table-scroll{overflow:auto;margin:26px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.75}th{background:#eaf1f5;text-align:left}th,td{border:1px solid #d5e0e7;padding:10px 12px;vertical-align:top}code{font-family:Consolas,monospace;font-size:.9em;background:#edf2f5;padding:2px 4px;border-radius:3px;overflow-wrap:anywhere}li{margin:8px 0}pre{overflow:auto;background:#edf2f5;padding:16px}pre code{padding:0}blockquote{border-left:3px solid #a1b5c0;margin:24px 0;padding-left:20px}@media(max-width:750px){main{padding:28px 20px 56px}body{font-size:15px}h1{font-size:26px}h2{font-size:23px}h3{font-size:19px}table{font-size:12px}th,td{padding:7px 8px}}@media print{main{max-width:none;padding:0}body{background:white;font-size:11pt}h2{break-before:page}img,table{break-inside:avoid}}`;
const html=`<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>仕様書の不整合は、AI実装の何に現れるか｜normal 30・anti 30</title><style>${css}</style></head><body><main>${body}</main></body></html>`;
const target=path.join(base,'report.html');await fs.writeFile(target,html);
const checks=path.join(base,'checks');await fs.mkdir(path.join(checks,'screenshots'),{recursive:true});
const browser=await chromium.launch({headless:true,channel:option('--channel')||'msedge'});
try{
  const page=await browser.newPage({viewport:{width:1200,height:960},deviceScaleFactor:1});const remote=[];
  await page.route('**/*',route=>{const url=route.request().url();if(/^https?:/i.test(url)){remote.push(url);return route.abort();}return route.continue();});
  await page.goto(pathToFileURL(target).href,{waitUntil:'load'});await page.evaluate(()=>document.fonts.ready);
  const state=await page.evaluate(()=>({title:document.querySelector('h1').textContent,headings:[...document.querySelectorAll('h2')].map(x=>x.textContent),
    images:[...document.images].map(x=>({src:x.getAttribute('src'),loaded:x.complete&&x.naturalWidth>0})),tables:document.querySelectorAll('table').length,horizontalOverflow:document.documentElement.scrollWidth>innerWidth}));
  if(state.images.length!==6||state.images.some(x=>!x.loaded)||state.horizontalOverflow||remote.length)throw new Error(JSON.stringify({state,remote}));
  await page.screenshot({path:path.join(checks,'screenshots/01-opening.png')});
  await page.locator('table').nth(1).screenshot({path:path.join(checks,'screenshots/02-condition-statistics.png')});
  for(let i=0;i<6;i++)await page.locator('img').nth(i).screenshot({path:path.join(checks,`screenshots/figure-${i+1}.png`)});
  for(const section of [4,5,6]){await page.locator('h2').nth(section-1).evaluate(x=>scrollTo(0,x.getBoundingClientRect().top+scrollY-20));await page.screenshot({path:path.join(checks,`screenshots/section-${section}.png`)});}
  await page.setViewportSize({width:800,height:960});const narrow=await page.evaluate(()=>({width:innerWidth,horizontalOverflow:document.documentElement.scrollWidth>innerWidth}));
  if(narrow.horizontalOverflow)throw new Error('Horizontal overflow at 800px');
  await fs.writeFile(path.join(checks,'browser-render.json'),JSON.stringify({report_sha256:sha(source),html_sha256:sha(html),renderer:'marked + local Chromium',browser:browser.version(),state,narrow,remote_requests:remote,study_app_runs:0,evaluator_runs:0},null,2)+'\n');
  process.stdout.write(JSON.stringify({images:state.images.length,tables:state.tables,headings:state.headings.length,horizontalOverflow:false,output:target})+'\n');
}finally{await browser.close();}
