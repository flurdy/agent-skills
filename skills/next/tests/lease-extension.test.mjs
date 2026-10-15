import assert from 'node:assert/strict';
import { resolve, join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const host = process.env.NEXT_TEST_PI_PACKAGE_DIR;

test('installed Pi loader registers only the read-only next_safe tool', {
  skip: !host && 'set NEXT_TEST_PI_PACKAGE_DIR for host-loader compatibility coverage',
}, async () => {
  const { loadExtensions } = await import(pathToFileURL(resolve(host, 'dist/core/extensions/loader.js')).href);
  const extension = fileURLToPath(new URL('../pi/index.ts', import.meta.url));
  const loaded = await loadExtensions([extension], process.cwd());
  assert.deepEqual(loaded.errors, []);
  assert.equal(loaded.extensions.length, 1);
  const tools = loaded.extensions[0].tools;
  assert.deepEqual([...tools.keys()], ['next_safe']);
  const tool = tools.get('next_safe').definition;
  assert.equal(tool.annotations.readOnlyHint, true);
  assert.equal(tool.parameters.additionalProperties, false);
  assert.deepEqual(Object.keys(tool.parameters.properties), ['action', 'selector']);
  await assert.rejects(tool.execute('fixture', { action: 'recheck' }, undefined, undefined, {}), /qualified selector/);
  await assert.rejects(tool.execute('fixture', { action: 'list', selector: 'local:a' }, undefined, undefined, {}), /qualified selector/);
});

for (const legacyMjs of [false, true]) test(`warm Pi reload refreshes production helper exports (${legacyMjs ? 'mjs migration' : 'same suffix'})`, {
  skip: !host && 'set NEXT_TEST_PI_PACKAGE_DIR for warm-reload regression coverage',
}, async () => {
  const { loadExtensions } = await import(pathToFileURL(resolve(host, 'dist/core/extensions/loader.js')).href);
  const sourceEntry = fileURLToPath(new URL('../pi/index.ts', import.meta.url));
  const entrySource = await readFile(sourceEntry, 'utf8');
  const helperName = entrySource.match(/from "\.\/(lease-selection\.(?:mjs|ts))"/)?.[1];
  assert.ok(helperName, 'use the actual production import suffix');
  const helperSource = await readFile(new URL(`../pi/${helperName}`, import.meta.url), 'utf8');
  assert.ok(helperSource.includes('export function renderSafeList'));
  const fixture = await mkdtemp(join(tmpdir(), 'next-warm-reload-'));
  try {
    await mkdir(join(fixture, 'pi'));
    await mkdir(join(fixture, 'scripts'));
    const entry = join(fixture, 'pi', 'index.ts');
    const wrapper = join(fixture, 'next-safe.ts');
    const helper = join(fixture, 'pi', helperName);
    const initialHelper = legacyMjs ? 'lease-selection.mjs' : helperName;
    await writeFile(wrapper, 'import { registerNextSafe } from "./pi/index.ts";\nexport default pi => registerNextSafe(pi, async () => undefined);\n');
    await writeFile(entry, entrySource.replace(helperName, initialHelper));
    await writeFile(join(fixture, 'pi', initialHelper), helperSource.replace('export function renderSafeList', 'function renderSafeList'));
    const packet = { version: 1, workspace: false, candidates: [{
      id: 'warm', selector: 'local:warm', title: 'Warm reload', priority: 2, issue_type: 'task', labels: [],
      source_scope: { state: 'unknown', roots: [], reason: 'undeclared fixture' },
    }], in_progress: [], diagnostics: [] };
    await writeFile(join(fixture, 'scripts', 'next-bd'), `#!/usr/bin/env node\nconsole.log(${JSON.stringify(JSON.stringify(packet))});\n`, { mode: 0o755 });
    const ctx = { cwd: fixture, sessionManager: { getSessionId: () => 'warm-reload-fixture' } };
    const first = await loadExtensions([wrapper], fixture);
    assert.deepEqual(first.errors, []);
    const prior = await first.extensions[0].tools.get('next_safe').definition.execute('before', { action: 'recheck', selector: 'local:warm' }, undefined, undefined, ctx);
    assert.equal(JSON.parse(prior.content[0].text).unknown[0].id, 'warm');
    await writeFile(helper, helperSource);
    await writeFile(entry, entrySource);
    const second = await loadExtensions([wrapper], fixture);
    assert.deepEqual(second.errors, []);
    const after = await second.extensions[0].tools.get('next_safe').definition.execute('after', { action: 'list' }, undefined, undefined, ctx);
    assert.match(after.content[0].text, /## Ready to review/);
    assert.match(after.content[0].text, /Warm reload/);
    assert.deepEqual(after.details.eligible, []);
    assert.equal(after.details.unknown[0].selector, 'local:warm');
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

test('Pi list returns the compact table but recheck retains exact machine eligibility', {
  skip: !host && 'set NEXT_TEST_PI_PACKAGE_DIR for native tool content coverage',
}, async () => {
  const { loadExtensions } = await import(pathToFileURL(resolve(host, 'dist/core/extensions/loader.js')).href);
  const loaded = await loadExtensions([fileURLToPath(new URL('../pi/index.ts', import.meta.url))], process.cwd());
  assert.deepEqual(loaded.errors, []);
  const tool = loaded.extensions[0].tools.get('next_safe').definition;
  const cwd = await mkdtemp(join(tmpdir(), 'next-safe-display-'));
  const previousPath = process.env.PATH;
  try {
    execFileSync('git', ['init', '-q', cwd]);
    await mkdir(join(cwd, '.beads'));
    await mkdir(join(cwd, 'bin'));
    await writeFile(join(cwd, 'bin', 'bd'), `#!/usr/bin/env node\nimport {appendFileSync} from 'node:fs';\nappendFileSync(${JSON.stringify(join(cwd, 'calls'))},process.argv.slice(2).join(' ')+'\\n');\nconsole.log(JSON.stringify(process.argv.includes('--ready') ? [{id:'review-me',title:'Review me',priority:2,issue_type:'task',labels:[],created_at:'2026-01-01'}] : []));\n`, { mode: 0o755 });
    process.env.PATH = `${join(cwd, 'bin')}:${previousPath ?? ''}`;
    const ctx = { cwd, sessionManager: { getSessionId: () => 'display-fixture' } };
    const list = await tool.execute('list-fixture', { action: 'list' }, undefined, undefined, ctx);
    assert.match(list.content[0].text, /## Ready to review \(1 beads\)/);
    assert.match(list.content[0].text, /\| 1 \| review-me .*Not checked: scope unknown/);
    assert.doesNotMatch(list.content[0].text, /## Unknown|Eligible under observed/);
    assert.equal(list.details.unknown[0].selector, 'local:review-me');
    const recheck = await tool.execute('recheck-fixture', { action: 'recheck', selector: 'local:review-me' }, undefined, undefined, ctx);
    const result = JSON.parse(recheck.content[0].text);
    assert.deepEqual(result.eligible, []);
    assert.equal(result.unknown[0].selector, 'local:review-me');
    const calls = (await readFile(join(cwd, 'calls'), 'utf8')).trim().split('\n');
    assert.ok(calls.length >= 8);
    assert.ok(calls.every(call => call.includes('--readonly')));
    assert.ok(calls.every(call => !call.includes('update') && !call.includes('comments')));
  } finally {
    if (previousPath === undefined) delete process.env.PATH;
    else process.env.PATH = previousPath;
    await rm(cwd, { recursive: true, force: true });
  }
});
