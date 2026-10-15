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
