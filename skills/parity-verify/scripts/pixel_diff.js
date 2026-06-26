#!/usr/bin/env node
/*
 * pixel_diff.js — deterministic pixel lane for parity-verify.
 *
 * Compares legacy.png vs react.png (captured at the SAME viewport with the SAME fixture data),
 * and emits:
 *   --out-diff diff.png            pixelmatch diff (changed pixels in red, AA ignored)
 *   --out-sxs side-by-side.png     [ legacy | react | diff ] for human review
 *   --out-regions regions.json     mismatch ratio + located changed-regions (bounding boxes)
 *
 * The regions are what make a pixel failure ACTIONABLE: verify_screen.py maps each region to the
 * React element under it, so the report says "differs near <TableHeader>" instead of a raw count.
 *
 * Deps (pulled from GitHub, MIT): pixelmatch (github.com/mapbox/pixelmatch), pngjs.
 *   npm i -D pixelmatch pngjs
 * Works with pixelmatch v5 (CJS) and v6 (ESM) via the loader below.
 */
const fs = require('fs');
let PNG = null, pngError = null;
try { PNG = require('pngjs').PNG; }
catch (e) { pngError = e; }   // reported gracefully by --self-check instead of crashing at load

async function loadPixelmatch() {
  try { return require('pixelmatch'); }
  catch (e) { const m = await import('pixelmatch'); return m.default; }
}

function crop(src, w, h) {
  if (src.width === w && src.height === h) return src;
  const out = new PNG({ width: w, height: h });
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const si = (src.width * y + x) << 2;
      const di = (w * y + x) << 2;
      out.data[di] = src.data[si]; out.data[di + 1] = src.data[si + 1];
      out.data[di + 2] = src.data[si + 2]; out.data[di + 3] = src.data[si + 3];
    }
  }
  return out;
}

function regionsFromDiff(diff, w, h, cell) {
  const gw = Math.ceil(w / cell), gh = Math.ceil(h / cell);
  const counts = new Int32Array(gw * gh);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (w * y + x) << 2;
      // pixelmatch marks changed pixels red (diffColor default [255,0,0]); AA excluded.
      if (diff.data[i] > 200 && diff.data[i + 1] < 80 && diff.data[i + 2] < 80) {
        counts[(Math.floor(y / cell)) * gw + (Math.floor(x / cell))]++;
      }
    }
  }
  const minCell = Math.max(4, Math.floor(cell * cell * 0.02)); // cell "hot" if >2% changed
  const hot = new Uint8Array(gw * gh);
  for (let i = 0; i < counts.length; i++) hot[i] = counts[i] >= minCell ? 1 : 0;
  // flood-fill adjacent hot cells into bounding boxes
  const seen = new Uint8Array(gw * gh);
  const regions = [];
  for (let gy = 0; gy < gh; gy++) {
    for (let gx = 0; gx < gw; gx++) {
      const s = gy * gw + gx;
      if (!hot[s] || seen[s]) continue;
      let minx = gx, miny = gy, maxx = gx, maxy = gy, changed = 0;
      const stack = [s];
      seen[s] = 1;
      while (stack.length) {
        const c = stack.pop(); const cx = c % gw, cy = (c - cx) / gw;
        changed += counts[c];
        if (cx < minx) minx = cx; if (cx > maxx) maxx = cx;
        if (cy < miny) miny = cy; if (cy > maxy) maxy = cy;
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          const nx = cx + dx, ny = cy + dy;
          if (nx < 0 || ny < 0 || nx >= gw || ny >= gh) continue;
          const ni = ny * gw + nx;
          if (hot[ni] && !seen[ni]) { seen[ni] = 1; stack.push(ni); }
        }
      }
      regions.push({
        x: minx * cell, y: miny * cell,
        w: (maxx - minx + 1) * cell, h: (maxy - miny + 1) * cell,
        changedPixels: changed,
      });
    }
  }
  regions.sort((a, b) => b.changedPixels - a.changedPixels);
  return regions.slice(0, 50);
}

function sideBySide(a, b, d) {
  const gap = 8, h = Math.max(a.height, b.height, d.height);
  const w = a.width + b.width + d.width + gap * 2;
  const out = new PNG({ width: w, height: h, fill: true });
  for (let i = 0; i < out.data.length; i += 4) { out.data[i] = out.data[i + 1] = out.data[i + 2] = 240; out.data[i + 3] = 255; }
  const blit = (src, ox) => {
    for (let y = 0; y < src.height; y++) for (let x = 0; x < src.width; x++) {
      const si = (src.width * y + x) << 2, di = (w * y + (x + ox)) << 2;
      out.data[di] = src.data[si]; out.data[di + 1] = src.data[si + 1];
      out.data[di + 2] = src.data[si + 2]; out.data[di + 3] = src.data[si + 3];
    }
  };
  blit(a, 0); blit(b, a.width + gap); blit(d, a.width + b.width + gap * 2);
  return out;
}

function parseArgs(argv) {
  const a = {};
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--self-check') { a.selfCheck = true; continue; }
    a[k.replace(/^--/, '')] = argv[++i];
  }
  return a;
}

async function main() {
  const a = parseArgs(process.argv);
  const threshold = a.threshold ? parseFloat(a.threshold) : 0.1;
  const cell = a.cell ? parseInt(a.cell) : 16;

  if (a.selfCheck) {
    // Gracefully report missing deps instead of crashing with a require() stack trace.
    let pixelmatch = null;
    try { pixelmatch = await loadPixelmatch(); } catch (e) { /* report below */ }
    if (pngError || !pixelmatch) {
      console.log(JSON.stringify({ self_check: 'deps-missing', pngjs: !pngError, pixelmatch: !!pixelmatch,
        fix: 'cd <skills>/parity-verify && npm install   (installs pixelmatch + pngjs from package.json)' }));
      process.exit(1);
    }
    const img = new PNG({ width: 20, height: 20, fill: true });
    for (let i = 0; i < img.data.length; i += 4) { img.data[i] = 10; img.data[i + 1] = 20; img.data[i + 2] = 30; img.data[i + 3] = 255; }
    const diff = new PNG({ width: 20, height: 20 });
    const n = pixelmatch(img.data, img.data, diff.data, 20, 20, { threshold, includeAA: false });
    console.log(JSON.stringify({ self_check: 'ok', identical_diff_pixels: n })); // expect 0
    return;
  }

  const pixelmatch = await loadPixelmatch();
  let img1 = PNG.sync.read(fs.readFileSync(a.legacy));
  let img2 = PNG.sync.read(fs.readFileSync(a.react));
  const dimMismatch = (img1.width !== img2.width || img1.height !== img2.height)
    ? { legacy: [img1.width, img1.height], react: [img2.width, img2.height] } : null;
  const w = Math.min(img1.width, img2.width), h = Math.min(img1.height, img2.height);
  img1 = crop(img1, w, h); img2 = crop(img2, w, h);

  const diff = new PNG({ width: w, height: h });
  const numDiff = pixelmatch(img1.data, img2.data, diff.data, w, h, { threshold, includeAA: false });
  const ratio = numDiff / (w * h);

  if (a['out-diff']) fs.writeFileSync(a['out-diff'], PNG.sync.write(diff));
  if (a['out-sxs']) fs.writeFileSync(a['out-sxs'], PNG.sync.write(sideBySide(img1, img2, diff)));
  const regions = regionsFromDiff(diff, w, h, cell);
  const result = { width: w, height: h, diffPixels: numDiff, ratio, dimMismatch, threshold, regions };
  if (a['out-regions']) fs.writeFileSync(a['out-regions'], JSON.stringify(result, null, 1));
  console.log(JSON.stringify({ ok: true, ratio: +ratio.toFixed(5), diffPixels: numDiff,
    regions: regions.length, dimMismatch }, null, 1));
}

main().catch(e => { console.error(e.stack || String(e)); process.exit(1); });
