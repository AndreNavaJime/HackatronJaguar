/** Generate installable PNG icons with Node built-ins (no extra dependencies). */
import { deflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';

const iconsDir = resolve(dirname(fileURLToPath(import.meta.url)), '../public/icons');
mkdirSync(iconsDir, { recursive: true });
const COLORS = {
  background: [16, 37, 30],
  green: [145, 227, 177],
  cream: [188, 233, 205],
  gold: [225, 186, 120],
};

const makeIcon = (size, maskable = false) => {
  const pixels = new Uint8Array(size * size * 3);
  const setPixel = (x, y, color) => {
    if (x < 0 || y < 0 || x >= size || y >= size) return;
    const index = (y * size + x) * 3;
    pixels[index] = color[0];
    pixels[index + 1] = color[1];
    pixels[index + 2] = color[2];
  };
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) setPixel(x, y, COLORS.background);
  }
  // Safe zone for Android launchers that crop maskable icons.
  const factor = maskable ? 0.76 : 1;
  const X = u => (.5 + (u - .5) * factor) * size;
  const Y = v => (.5 + (v - .5) * factor) * size;
  const S = v => v * factor * size;
  const dot = (u, v, rad, color) => {
    const cx = X(u), cy = Y(v), radius = S(rad), rsq = radius * radius;
    for (let y = Math.max(0, Math.floor(cy - radius)); y <= Math.min(size - 1, Math.ceil(cy + radius)); y++) {
      for (let x = Math.max(0, Math.floor(cx - radius)); x <= Math.min(size - 1, Math.ceil(cx + radius)); x++) {
        if ((x - cx) ** 2 + (y - cy) ** 2 <= rsq) setPixel(x, y, color);
      }
    }
  };
  const line = (a, b, width, color) => {
    const [ax, ay] = [X(a[0]), Y(a[1])];
    const [bx, by] = [X(b[0]), Y(b[1])];
    const radius = S(width) / 2;
    const lengthSq = (bx - ax) ** 2 + (by - ay) ** 2 || 1;
    for (let y = Math.max(0, Math.floor(Math.min(ay, by) - radius)); y <= Math.min(size - 1, Math.ceil(Math.max(ay, by) + radius)); y++) {
      for (let x = Math.max(0, Math.floor(Math.min(ax, bx) - radius)); x <= Math.min(size - 1, Math.ceil(Math.max(ax, bx) + radius)); x++) {
        const t = Math.max(0, Math.min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / lengthSq));
        if ((x - ax - t * (bx - ax)) ** 2 + (y - ay - t * (by - ay)) ** 2 <= radius ** 2) setPixel(x, y, color);
      }
    }
  };
  const path = (points, width, color) => {
    for (let i = 1; i < points.length; i++) line(points[i-1], points[i], width, color);
  };
  const ring = (u, v, rad, width, color) => {
    const cx = X(u), cy = Y(v), r = S(rad), half = S(width) / 2;
    const lower = (r - half) ** 2, upper = (r + half) ** 2;
    for (let y = Math.max(0, Math.floor(cy - r - half)); y <= Math.min(size - 1, Math.ceil(cy + r + half)); y++) {
      for (let x = Math.max(0, Math.floor(cx - r - half)); x <= Math.min(size - 1, Math.ceil(cx + r + half)); x++) {
        const dsq = (x - cx) ** 2 + (y - cy) ** 2;
        if (dsq >= lower && dsq <= upper) setPixel(x, y, color);
      }
    }
  };
  const triangle = (points, color) => {
    const vertices = points.map(([x,y]) => [X(x), Y(y)]);
    const xs = vertices.map(q => q[0]), ys = vertices.map(q => q[1]);
    const [a,b,c] = vertices;
    const cross = (p, q, r) => (r[0]-p[0]) * (q[1]-p[1]) - (r[1]-p[1]) * (q[0]-p[0]);
    for (let y = Math.max(0, Math.floor(Math.min(...ys))); y <= Math.min(size - 1, Math.ceil(Math.max(...ys))); y++) {
      for (let x = Math.max(0, Math.floor(Math.min(...xs))); x <= Math.min(size - 1, Math.ceil(Math.max(...xs))); x++) {
        const p = [x, y];
        const v1 = cross(a,b,p), v2 = cross(b,c,p), v3 = cross(c,a,p);
        if (!((v1 < 0 || v2 < 0 || v3 < 0) && (v1 > 0 || v2 > 0 || v3 > 0))) setPixel(x, y, color);
      }
    }
  };

  ring(.5,.5,.345,.024,COLORS.green);
  path([[.29,.43],[.24,.28],[.34,.32],[.39,.27],[.5,.26],[.61,.27],[.66,.32],[.76,.28],[.71,.43]],.028,COLORS.green);
  path([[.29,.43],[.27,.56],[.34,.65],[.44,.71],[.5,.73],[.56,.71],[.66,.65],[.73,.56],[.71,.43]],.03,COLORS.green);
  path([[.32,.38],[.29,.33],[.37,.37]],.016,COLORS.gold);
  path([[.68,.38],[.71,.33],[.63,.37]],.016,COLORS.gold);
  path([[.42,.36],[.44,.40]],.014,COLORS.gold);
  path([[.58,.36],[.56,.40]],.014,COLORS.gold);
  path([[.35,.47],[.42,.46],[.46,.50]],.024,COLORS.cream);
  path([[.65,.47],[.58,.46],[.54,.50]],.024,COLORS.cream);
  dot(.415,.477,.01,COLORS.gold);
  dot(.585,.477,.01,COLORS.gold);
  triangle([[.46,.58],[.54,.58],[.5,.62]],COLORS.gold);
  path([[.5,.62],[.5,.65],[.47,.67]],.015,COLORS.cream);
  path([[.5,.65],[.53,.67]],.015,COLORS.cream);
  for (const [x,y] of [[.36,.55],[.39,.60],[.64,.55],[.61,.60]]) dot(x,y,.011,COLORS.gold);

  // Write PNG (8-bit RGB) compressed via Node's zlib.
  const scanline = Buffer.alloc(size * (1 + size * 3));
  for (let y = 0; y < size; y++) {
    const off = y * (1 + size * 3);
    scanline[off] = 0;
    scanline.set(pixels.subarray(y * size * 3, (y + 1) * size * 3), off + 1);
  }
  const crcTable = Array.from({length: 256}, (_, i) => {
    let c = i;
    for (let n = 0; n < 8; n++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    return c >>> 0;
  });
  const chunk = (kind, bytes) => {
    const type = Buffer.from(kind, 'ascii');
    const len = Buffer.alloc(4); len.writeUInt32BE(bytes.length, 0);
    const body = Buffer.concat([type, bytes]);
    let c = 0xffffffff;
    for (const byte of body) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
    const crc = Buffer.alloc(4); crc.writeUInt32BE((c ^ 0xffffffff) >>> 0, 0);
    return Buffer.concat([len, body, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; ihdr[9] = 2; // 8 bits per channel, truecolor
  const output = Buffer.concat([
    Buffer.from([137,80,78,71,13,10,26,10]),
    chunk('IHDR', ihdr), chunk('IDAT', deflateSync(scanline, {level: 9})),
    chunk('IEND', Buffer.alloc(0)),
  ]);
  const name = maskable ? 'maskable-512.png' : `icon-${size}.png`;
  writeFileSync(resolve(iconsDir, name), output);
  console.log('Ícono PWA:', name, `(${(output.length / 1024).toFixed(1)} KiB)`);
};

makeIcon(180);
makeIcon(192);
makeIcon(512);
makeIcon(512, true);
