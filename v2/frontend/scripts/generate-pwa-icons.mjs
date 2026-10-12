/** Generate installable PNG icons with Node built-ins (no extra dependencies). */
import { deflateSync, inflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';

const iconsDir = resolve(dirname(fileURLToPath(import.meta.url)), '../public/icons');
mkdirSync(iconsDir, { recursive: true });
const COLORS = {
  background: [13, 47, 31],
  green: [145, 227, 177],
  cream: [188, 233, 205],
  gold: [225, 186, 120],
};

// Side-profile jaguar selected for PantheraLAB. Indexed source, 160px, deflated.
// No external asset URL: icons regenerate deterministically when Vite starts.
const SOURCE_SIZE = 160;
const PALETTE = [[13,47,31],[249,239,217],[217,171,95],[130,140,117],[231,219,196]];
const compressedArtwork = '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';
const artwork = inflateSync(Buffer.from(compressedArtwork, 'base64'));
if (artwork.length !== SOURCE_SIZE * SOURCE_SIZE) throw new Error('Ícono base incompleto.');

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

  // Rasterize artwork in the available Android/iOS PWA sizes.
  // Maskable version shrinks the figure into the launcher-safe zone.
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = (x + 0.5) / size;
      const v = (y + 0.5) / size;
      const sx = ((u - 0.5) / factor + 0.5) * (SOURCE_SIZE - 1);
      const sy = ((v - 0.5) / factor + 0.5) * (SOURCE_SIZE - 1);
      if (sx < 0 || sy < 0 || sx > SOURCE_SIZE - 1 || sy > SOURCE_SIZE - 1) continue;
      const x0 = Math.floor(sx), y0 = Math.floor(sy);
      const x1 = Math.min(SOURCE_SIZE - 1, x0 + 1);
      const y1 = Math.min(SOURCE_SIZE - 1, y0 + 1);
      const fx = sx - x0, fy = sy - y0;
      const a = PALETTE[artwork[y0 * SOURCE_SIZE + x0]];
      const b = PALETTE[artwork[y0 * SOURCE_SIZE + x1]];
      const c = PALETTE[artwork[y1 * SOURCE_SIZE + x0]];
      const d = PALETTE[artwork[y1 * SOURCE_SIZE + x1]];
      const color = [0,1,2].map(k => Math.round(
        (a[k] * (1 - fx) + b[k] * fx) * (1 - fy) +
        (c[k] * (1 - fx) + d[k] * fx) * fy));
      setPixel(x, y, color);
    }
  }

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
