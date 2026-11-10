// Minimal QR Code encoder (ISO/IEC 18004): byte mode, versions 1-10, error correction L/M/Q/H.
// The setup screen needs a real, scannable QR for the Mac's Syncthing device ID without an external
// library or image service (CSP: same-origin only). Written from the specification; checked by decoding
// the rendered result with an independent decoder.
const LEVEL = {L: {format: 1, index: 0}, M: {format: 0, index: 1}, Q: {format: 3, index: 2}, H: {format: 2, index: 3}};
const ECC_PER_BLOCK = [
  [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18],
  [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26],
  [-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24],
  [-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28],
];
const BLOCKS = [
  [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4],
  [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5],
  [-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8],
  [-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8],
];

function rawModules(version) {
  let result = (16 * version + 128) * version + 64;
  if (version >= 2) {
    const align = Math.floor(version / 7) + 2;
    result -= (25 * align - 10) * align - 55;
    if (version >= 7) result -= 36;
  }
  return result;
}

const rawCodewords = (version) => Math.floor(rawModules(version) / 8);

function dataCodewords(version, level) {
  const {index} = LEVEL[level];
  return rawCodewords(version) - ECC_PER_BLOCK[index][version] * BLOCKS[index][version];
}

// ---- Reed-Solomon over GF(256), polynomial 0x11D
function gfMultiply(x, y) {
  let z = 0;
  for (let i = 7; i >= 0; i -= 1) {
    z = (z << 1) ^ ((z >>> 7) * 0x11D);
    z ^= ((y >>> i) & 1) * x;
  }
  return z;
}

function rsDivisor(degree) {
  const result = new Array(degree).fill(0);
  result[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i += 1) {
    for (let j = 0; j < result.length; j += 1) {
      result[j] = gfMultiply(result[j], root);
      if (j + 1 < result.length) result[j] ^= result[j + 1];
    }
    root = gfMultiply(root, 0x02);
  }
  return result;
}

function rsRemainder(data, divisor) {
  const result = divisor.map(() => 0);
  for (const byte of data) {
    const factor = byte ^ result.shift();
    result.push(0);
    divisor.forEach((coefficient, i) => { result[i] ^= gfMultiply(coefficient, factor); });
  }
  return result;
}

// ---- codewords
function encodeData(bytes, version, level) {
  const capacityBits = dataCodewords(version, level) * 8;
  const bits = [];
  const put = (value, length) => { for (let i = length - 1; i >= 0; i -= 1) bits.push((value >>> i) & 1); };
  put(0b0100, 4);
  put(bytes.length, version < 10 ? 8 : 16);
  for (const byte of bytes) put(byte, 8);
  put(0, Math.min(4, capacityBits - bits.length));
  put(0, (8 - (bits.length % 8)) % 8);
  for (let pad = 0xEC; bits.length < capacityBits; pad ^= 0xEC ^ 0x11) put(pad, 8);
  const codewords = [];
  for (let i = 0; i < bits.length; i += 8) codewords.push(parseInt(bits.slice(i, i + 8).join(''), 2));
  return codewords;
}

function interleave(data, version, level) {
  const {index} = LEVEL[level];
  const blocks = BLOCKS[index][version];
  const eccLength = ECC_PER_BLOCK[index][version];
  const raw = rawCodewords(version);
  const shortBlocks = blocks - (raw % blocks);
  const shortLength = Math.floor(raw / blocks);
  const divisor = rsDivisor(eccLength);
  const parts = [];
  for (let i = 0, k = 0; i < blocks; i += 1) {
    const length = shortLength - eccLength + (i < shortBlocks ? 0 : 1);
    const chunk = data.slice(k, k + length);
    k += length;
    parts.push({data: chunk, ecc: rsRemainder(chunk, divisor)});
  }
  const out = [];
  for (let i = 0; i < parts[parts.length - 1].data.length; i += 1) {
    for (const part of parts) if (i < part.data.length) out.push(part.data[i]);
  }
  for (let i = 0; i < eccLength; i += 1) parts.forEach((part) => out.push(part.ecc[i]));
  return out;
}

// ---- matrix
function alignmentPositions(version) {
  if (version === 1) return [];
  const count = Math.floor(version / 7) + 2;
  const size = version * 4 + 17;
  const step = version === 32 ? 26 : Math.ceil((version * 4 + 4) / (count * 2 - 2)) * 2;
  const result = [6];
  for (let pos = size - 7; result.length < count; pos -= step) result.splice(1, 0, pos);
  return result;
}

function bch(value, poly, topBit) {
  let rest = value;
  for (let i = 0; i < topBit; i += 1) rest = (rest << 1) ^ ((rest >>> (topBit - 1)) * poly);
  return rest;
}

function buildMatrix(codewords, version, level, mask) {
  const size = version * 4 + 17;
  const dark = Array.from({length: size}, () => new Array(size).fill(false));
  const reserved = Array.from({length: size}, () => new Array(size).fill(false));
  const set = (x, y, value) => { dark[y][x] = value; reserved[y][x] = true; };

  for (let i = 0; i < size; i += 1) {   // timing
    set(6, i, i % 2 === 0);
    set(i, 6, i % 2 === 0);
  }
  const finder = (cx, cy) => {
    for (let dy = -4; dy <= 4; dy += 1) {
      for (let dx = -4; dx <= 4; dx += 1) {
        const x = cx + dx, y = cy + dy;
        if (x < 0 || y < 0 || x >= size || y >= size) continue;
        const d = Math.max(Math.abs(dx), Math.abs(dy));
        set(x, y, d !== 2 && d !== 4);
      }
    }
  };
  finder(3, 3);
  finder(size - 4, 3);
  finder(3, size - 4);
  const positions = alignmentPositions(version);
  positions.forEach((cx, i) => positions.forEach((cy, j) => {
    if ((i === 0 && j === 0) || (i === 0 && j === positions.length - 1) || (i === positions.length - 1 && j === 0)) return;
    for (let dy = -2; dy <= 2; dy += 1) for (let dx = -2; dx <= 2; dx += 1) set(cx + dx, cy + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
  }));

  const drawFormat = (m) => {
    const data = (LEVEL[level].format << 3) | m;
    const bits = ((data << 10) | bch(data, 0x537, 10)) ^ 0x5412;
    const bit = (i) => ((bits >>> i) & 1) !== 0;
    for (let i = 0; i <= 5; i += 1) set(8, i, bit(i));
    set(8, 7, bit(6));
    set(8, 8, bit(7));
    set(7, 8, bit(8));
    for (let i = 9; i < 15; i += 1) set(14 - i, 8, bit(i));
    for (let i = 0; i < 8; i += 1) set(size - 1 - i, 8, bit(i));
    for (let i = 8; i < 15; i += 1) set(8, size - 15 + i, bit(i));
    set(8, size - 8, true);
  };
  drawFormat(0);   // reserve the areas; rewritten with the real mask below
  if (version >= 7) {
    const bits = (version << 12) | bch(version, 0x1F25, 12);
    for (let i = 0; i < 18; i += 1) {
      const a = size - 11 + (i % 3), b = Math.floor(i / 3);
      const value = ((bits >>> i) & 1) !== 0;
      set(a, b, value);
      set(b, a, value);
    }
  }

  // data, zigzag from the bottom right
  const bits = [];
  for (const byte of codewords) for (let i = 7; i >= 0; i -= 1) bits.push((byte >>> i) & 1);
  let k = 0;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vert = 0; vert < size; vert += 1) {
      for (let j = 0; j < 2; j += 1) {
        const x = right - j;
        const upward = ((right + 1) & 2) === 0;
        const y = upward ? size - 1 - vert : vert;
        if (!reserved[y][x] && k < bits.length) { dark[y][x] = bits[k] === 1; k += 1; }
      }
    }
  }
  const masks = [(x, y) => (x + y) % 2 === 0, (x, y) => y % 2 === 0, (x, y) => x % 3 === 0, (x, y) => (x + y) % 3 === 0,
    (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0, (x, y) => ((x * y) % 2) + ((x * y) % 3) === 0,
    (x, y) => (((x * y) % 2) + ((x * y) % 3)) % 2 === 0, (x, y) => (((x + y) % 2) + ((x * y) % 3)) % 2 === 0];
  for (let y = 0; y < size; y += 1) for (let x = 0; x < size; x += 1) if (!reserved[y][x] && masks[mask](x, y)) dark[y][x] = !dark[y][x];
  drawFormat(mask);
  return dark;
}

function penalty(dark) {
  const size = dark.length;
  let score = 0;
  const lineScore = (get) => {
    let run = 1;
    for (let i = 1; i < size; i += 1) {
      if (get(i) === get(i - 1)) { run += 1; if (run === 5) score += 3; else if (run > 5) score += 1; } else run = 1;
    }
  };
  for (let y = 0; y < size; y += 1) lineScore((x) => dark[y][x]);
  for (let x = 0; x < size; x += 1) lineScore((y) => dark[y][x]);
  for (let y = 0; y < size - 1; y += 1) for (let x = 0; x < size - 1; x += 1) {
    const c = dark[y][x];
    if (c === dark[y][x + 1] && c === dark[y + 1][x] && c === dark[y + 1][x + 1]) score += 3;
  }
  const pattern = [true, false, true, true, true, false, true, false, false, false, false];
  const hit = (get) => {
    for (let i = 0; i + 11 <= size; i += 1) {
      if (pattern.every((v, k) => get(i + k) === v) || pattern.every((v, k) => get(i + 10 - k) === v)) score += 40;
    }
  };
  for (let y = 0; y < size; y += 1) hit((x) => dark[y][x]);
  for (let x = 0; x < size; x += 1) hit((y) => dark[y][x]);
  const total = size * size;
  const count = dark.reduce((sum, row) => sum + row.filter(Boolean).length, 0);
  score += Math.floor(Math.abs(count * 20 - total * 10) / total) * 10;
  return score;
}

// Returns an array of rows of booleans (true = dark module).
export function qrMatrix(text, level = 'M') {
  const bytes = Array.from(new TextEncoder().encode(String(text)));
  for (let version = 1; version <= 10; version += 1) {
    const room = dataCodewords(version, level) * 8 - 4 - (version < 10 ? 8 : 16);
    if (bytes.length * 8 > room) continue;
    const codewords = interleave(encodeData(bytes, version, level), version, level);
    let best = null;
    for (let mask = 0; mask < 8; mask += 1) {
      const candidate = buildMatrix(codewords, version, level, mask);
      const score = penalty(candidate);
      if (!best || score < best.score) best = {score, candidate};
    }
    return best.candidate;
  }
  throw new Error('text too long for a version 10 QR code');
}

// An SVG element drawing the matrix with a 2-module quiet zone, built with createElementNS (no markup parsing).
export function qrSvg(text, level = 'M', label = '') {
  const matrix = qrMatrix(text, level);
  const border = 2, size = matrix.length + border * 2;
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
  svg.setAttribute('shape-rendering', 'crispEdges');
  svg.setAttribute('role', 'img');
  if (label) svg.setAttribute('aria-label', label);
  const back = document.createElementNS(NS, 'rect');
  back.setAttribute('width', String(size));
  back.setAttribute('height', String(size));
  back.setAttribute('fill', '#fff');
  const path = document.createElementNS(NS, 'path');
  let d = '';
  matrix.forEach((row, y) => row.forEach((cell, x) => { if (cell) d += `M${x + border} ${y + border}h1v1h-1z`; }));
  path.setAttribute('d', d);
  path.setAttribute('fill', '#000');
  svg.append(back, path);
  return svg;
}
