// Optional installed-runtime check. Reads Orca's Unicode 11 range data; never evaluates its bundle.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const [piModule, orcaBundle] = process.argv.slice(2);
assert(piModule && orcaBundle, 'usage: node tests/check_table_glyph_widths.mjs <pi-tui/dist/index.js> <Orca renderer bundle>');
const { Markdown, visibleWidth, stripTerminalSequences } = await import(pathToFileURL(resolve(piModule)).href);
const source = readFileSync(orcaBundle, 'utf8');
const version = source.search(/this\.version=[`"']11[`"']/);
assert(version >= 0, 'Unicode 11 provider not found; do not substitute another width model');
const end = source.indexOf('charProperties(', version);
assert(end > version && end - version < 3000, 'unexpected provider layout');
const provider = source.slice(version, end);
const ident = '[A-Za-z_$][A-Za-z0-9_$]*';
const bmpZero = provider.match(new RegExp(`\\.fill\\(0,(${ident})\\[`));
const bmpWide = provider.match(new RegExp(`\\.fill\\(2,(${ident})\\[`));
const astral = provider.match(new RegExp(`:(${ident})\\([^,]+,(${ident})\\)\\?0:\\1\\([^,]+,(${ident})\\)\\?2:1`));
assert(bmpZero && bmpWide && astral, 'Unicode 11 range references changed; inspect before updating this check');
function ranges(name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = source.match(new RegExp(`(?:^|[,; ])${escaped}=(\\[\\[[0-9,\\[\\]]+\\]\\])`));
  assert(match, `range data missing: ${name}`);
  const rows = JSON.parse(match[1]);
  assert(rows.every(([a, b]) => Number.isInteger(a) && Number.isInteger(b) && a <= b));
  return rows;
}
const zero = [...ranges(bmpZero[1]), ...ranges(astral[2])];
const wide = [...ranges(bmpWide[1]), ...ranges(astral[3])];
function wcwidth(cp) {
  if (cp < 32 || (cp >= 127 && cp < 160)) return 0;
  if (zero.some(([a, b]) => a <= cp && cp <= b)) return 0;
  return wide.some(([a, b]) => a <= cp && cp <= b) ? 2 : 1;
}
function xtermWidth(text) {
  // Fixtures contain no ZWJ sequences; Orca's ZWJ-only wrapper delegates these widths unchanged.
  assert(!text.includes('\u200d'));
  return [...text].reduce((sum, char) => sum + wcwidth(char.codePointAt(0)), 0);
}
for (const old of ['⚠\ufe0f', '✂\ufe0f', '🗄\ufe0f']) {
  assert.equal(visibleWidth(old), 2, 'negative control: Pi must expose the original discrepancy');
  assert.equal(xtermWidth(old), 1, 'negative control: xterm must expose the original discrepancy');
}
const fixture = readFileSync(new URL('./fixtures/table-glyphs.md', import.meta.url), 'utf8');
assert(!/[\ufe0e\ufe0f]/u.test(fixture));
const identity = text => text;
const theme = Object.fromEntries(['heading', 'link', 'linkUrl', 'code', 'codeBlock', 'codeBlockBorder',
  'quote', 'quoteBorder', 'hr', 'listBullet', 'bold', 'italic', 'strikethrough', 'underline'].map(k => [k, identity]));
let count = 0;
for (const columns of [60, 100, 180]) {
  const lines = new Markdown(fixture, 0, 0, theme).render(columns).map(stripTerminalSequences);
  let borders = 0;
  for (const line of lines) {
    assert.equal(visibleWidth(line), xtermWidth(line), `row width differs at ${columns} columns`);
    for (let i = 0; i < line.length; i++) {
      if ('│┃|'.includes(line[i])) {
        assert.equal(visibleWidth(line.slice(0, i)), xtermWidth(line.slice(0, i)), 'border shifted');
        borders++;
      }
    }
  }
  assert(borders > 20, 'expected a representative rendered table, not plain text');
  count += borders;
}
console.log(JSON.stringify({status: 'pass', borderComparisons: count, widths: [60, 100, 180],
  negativeControls: 3, orcaBundleSha256: createHash('sha256').update(source).digest('hex'),
  limitation: 'Pi renderer versus installed Orca Unicode 11 range data; not a Claude Code visual check.'}));
