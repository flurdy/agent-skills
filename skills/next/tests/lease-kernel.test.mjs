import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';
import { classifyCandidates } from '../pi/lease-selection.ts';

const packageDir = process.env.NEXT_TEST_SESSION_MODE_DIR;

test('public observer excludes self; a later foreign acquisition defeats an earlier free observation', {
  skip: !packageDir && 'set NEXT_TEST_SESSION_MODE_DIR to the reviewed session-mode checkout for real-kernel coverage',
}, async () => {
  const manifest = JSON.parse(await readFile(join(packageDir, 'package.json'), 'utf8'));
  assert.equal(manifest.name, '@flurdy/pi-session-mode');
  const moduleUrl = pathToFileURL(resolve(packageDir, 'lease.ts')).href;
  const { acquireWorktreeLease } = await import(moduleUrl);
  const { probeWorktreeLeaseOccupancies } = await import(pathToFileURL(resolve(packageDir, 'lease-observer.ts')).href);
  const temp = await mkdtemp(join(tmpdir(), 'next-lease-kernel-'));
  const root = join(temp, 'repo');
  const runtimeDir = join(temp, 'runtime');
  let own;
  let foreign;
  try {
    await mkdir(root);
    execFileSync('git', ['init', '-q', root]);
    const data = {
      version: 1, diagnostics: [], in_progress: [],
      candidates: [{ id: 'a', selector: 'local:a', labels: [], source_scope: { state: 'declared', roots: [root] } }],
    };
    const observer = (roots, options) => probeWorktreeLeaseOccupancies(roots, { ...options, runtimeDir });
    own = await acquireWorktreeLease(root, { runtimeDir });
    assert.equal(own.kind, 'held');
    assert.equal((await classifyCandidates(data, observer)).eligible.length, 1);
    await own.release();
    own = undefined;
    assert.equal((await classifyCandidates(data, observer)).eligible.length, 1);
    foreign = spawn(process.execPath, ['--input-type=module', '-e', `
      import { acquireWorktreeLease } from ${JSON.stringify(moduleUrl)};
      const result = await acquireWorktreeLease(${JSON.stringify(root)}, { runtimeDir: ${JSON.stringify(runtimeDir)} });
      console.log(result.kind);
      if (result.kind !== 'held') process.exit(1);
      process.stdin.resume();
      process.stdin.on('end', async () => { await result.release(); process.exit(0); });
    `], { stdio: ['pipe', 'pipe', 'pipe'] });
    let output = '';
    foreign.stdout.setEncoding('utf8');
    foreign.stdout.on('data', chunk => { output += chunk; });
    const deadline = Date.now() + 10000;
    while (!output.includes('\n')) {
      if (foreign.exitCode !== null || Date.now() > deadline) throw Error('Foreign fixture did not acquire');
      await new Promise(r => setTimeout(r, 20));
    }
    assert.equal(output.trim(), 'held');
    const attempted = await acquireWorktreeLease(root, { runtimeDir });
    assert.equal(attempted.kind, 'contended');
    assert.equal((await classifyCandidates(data, observer)).occupied.length, 1);
    const nested = join(root, 'nested');
    await mkdir(nested);
    data.candidates[0].source_scope.roots = [nested];
    assert.equal((await classifyCandidates(data, observer)).unavailable.length, 1);
    execFileSync('git', ['init', '-q', nested]);
    assert.equal((await classifyCandidates(data, observer)).eligible.length, 1);
  } finally {
    if (own?.kind === 'held') await own.release();
    if (foreign && foreign.exitCode === null) {
      foreign.stdin.end();
      const exited = once(foreign, 'exit');
      const killTimer = setTimeout(() => foreign.kill('SIGKILL'), 2000);
      await exited;
      clearTimeout(killTimer);
    }
    await rm(temp, { recursive: true, force: true });
  }
});
