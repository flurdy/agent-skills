import { spawn, execFile } from 'node:child_process';
import { access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const collector = fileURLToPath(new URL('../scripts/next-bd', import.meta.url));
const runFile = promisify(execFile);
const MAX_ROOTS = 32;
const COVERAGE = 'Advisory cooperating local Pi occupancy in this process runtime namespace only; not a reservation, source authority, or proof that other harnesses/machines are idle. Completeness is declared, not inferred.';

export function collectCandidates(cwd, signal, timeoutMs = 60000) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new Error('Selection collection aborted')); return; }
    const grouped = process.platform !== 'win32';
    const child = spawn(collector, ['--safe-json'], {
      cwd, detached: grouped, stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = '';
    let bytes = 0;
    let failure;
    let settled = false;
    const kill = () => {
      if (!child.pid) return;
      try { grouped ? process.kill(-child.pid, 'SIGKILL') : child.kill('SIGKILL'); } catch {}
    };
    const stop = reason => { failure ??= new Error(reason); kill(); };
    const abort = () => stop('Selection collection aborted');
    const timer = setTimeout(() => stop('Selection collection timed out'), timeoutMs);
    signal?.addEventListener('abort', abort, { once: true });
    const finish = error => {
      if (settled) return;
      settled = true;
      kill();
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      if (failure || error) reject(failure ?? error);
      else {
        try { resolve(JSON.parse(output)); } catch { reject(new Error('Invalid selection JSON')); }
      }
    };
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', chunk => {
      bytes += Buffer.byteLength(chunk);
      if (bytes > 2 * 1024 * 1024) stop('Selection output exceeds 2 MiB; narrow the workspace');
      else if (!failure) output += chunk;
    });
    child.stderr.resume();
    child.once('error', () => finish(new Error('Selection collector unavailable')));
    child.once('close', code => finish(code === 0 ? undefined : new Error('Selection collector failed')));
    if (signal?.aborted) abort();
  });
}

function validatePacket(packet) {
  if (!packet || packet.version !== 1 || !Array.isArray(packet.candidates) || packet.candidates.length > 1000 ||
      !Array.isArray(packet.in_progress) || !Array.isArray(packet.diagnostics)) throw new Error('Invalid or oversized selection packet');
  for (const row of [...packet.candidates, ...packet.in_progress]) {
    if (!row || typeof row !== 'object' || !Array.isArray(row.labels ?? []) ||
        (row.labels ?? []).some(label => typeof label !== 'string')) throw new Error('Invalid tracker labels');
  }
  if (packet.candidates.some(row => typeof row.id !== 'string' || typeof row.selector !== 'string' ||
      !row.source_scope || !['declared', 'partial', 'unknown', 'invalid', 'unavailable'].includes(row.source_scope.state) ||
      !Array.isArray(row.source_scope.roots) || row.source_scope.roots.length > MAX_ROOTS ||
      row.source_scope.roots.some(root => typeof root !== 'string' || !root.startsWith('/')) ||
      (['declared', 'partial'].includes(row.source_scope.state) && row.source_scope.roots.length === 0))) {
    throw new Error('Invalid source-scope packet');
  }
  if (new Set(packet.candidates.map(row => row.selector)).size !== packet.candidates.length) throw new Error('Duplicate candidate selectors');
}

export async function classifyCandidates(packet, observer, signal) {
  validatePacket(packet);
  const roots = [...new Set(packet.candidates.flatMap(row => row.source_scope.roots))];
  let observations;
  let reason = 'no in-process Pi observer';
  if (roots.length > MAX_ROOTS) reason = 'more than 32 unique roots; recheck a single qualified selector';
  else if (typeof observer === 'function' && roots.length > 0) {
    const deadline = AbortSignal.timeout(4000);
    const bounded = signal ? AbortSignal.any([signal, deadline]) : deadline;
    let onAbort;
    try {
      bounded.throwIfAborted();
      const cancelled = new Promise((_, reject) => {
        onAbort = () => reject(new Error('Observation cancelled'));
        bounded.addEventListener('abort', onAbort, { once: true });
      });
      observations = await Promise.race([observer(roots, { timeoutMs: 2000, signal: bounded }), cancelled]);
      if (bounded.aborted) throw new Error('Observation cancelled');
      if (!Array.isArray(observations) || observations.length !== roots.length) throw new Error('Invalid observation count');
      observations = observations.map((row, index) => {
        if (row && ['free', 'held'].includes(row.kind) && row.root === roots[index]) return row;
        return { kind: 'unavailable', reason: row?.kind === 'unavailable' ? 'observer unavailable' : 'invalid observation or declared path is not an exact canonical Git root' };
      });
    } catch {
      reason = 'observer failed, cancelled or returned malformed results';
      observations = undefined;
    } finally {
      if (onAbort) bounded.removeEventListener('abort', onAbort);
    }
  }
  const byRoot = new Map(roots.map((root, index) => [root, observations?.[index] ?? { kind: 'unavailable', reason }]));
  const result = {
    version: 1, observedAt: new Date().toISOString(), coverage: COVERAGE,
    eligible: [], occupied: [], unknown: [], unavailable: [], tracker_conflicts: [],
    diagnostics: packet.diagnostics,
  };
  for (const candidate of packet.candidates) {
    const scope = candidate.source_scope;
    const occupancy = scope.roots.map(root => ({ root, ...byRoot.get(root) }));
    const conflicts = packet.in_progress.filter(row =>
      (row.repository ?? 'local') === (candidate.repository ?? 'local') &&
      (row.labels ?? []).some(label => (candidate.labels ?? []).includes(label)),
    ).map(row => row.id);
    const row = {
      selector: candidate.selector, id: candidate.id, repository: candidate.repository ?? 'local',
      priority: candidate.priority, issue_type: candidate.issue_type, title: candidate.title,
      labels: candidate.labels ?? [], source_scope: scope, occupancy, tracker_overlap: conflicts,
    };
    const queue = occupancy.some(item => item.kind === 'held') ? 'occupied'
      : ['unknown', 'partial', 'invalid'].includes(scope.state) ? 'unknown'
      : scope.state === 'unavailable' || occupancy.some(item => item.kind !== 'free') ? 'unavailable'
      : conflicts.length ? 'tracker_conflicts' : 'eligible';
    result[queue].push(row);
  }
  return result;
}

export async function inspectCandidates(cwd, { selector, signal, loadObserver } = {}) {
  const packet = await collectCandidates(cwd, signal);
  validatePacket(packet);
  if (selector !== undefined) {
    packet.candidates = packet.candidates.filter(row => row.selector === selector);
    if (packet.candidates.length !== 1) throw new Error('Selector is no longer ready or its owning source is unavailable; list again');
  }
  let observer;
  const diagnostics = [...packet.diagnostics];
  try {
    if (process.platform !== 'linux') throw new Error('Linux process evidence required');
    await access('/proc/self/stat');
    await runFile('lslocks', ['--version'], { timeout: 1000, signal, maxBuffer: 4096 });
    observer = await loadObserver?.();
    if (typeof observer !== 'function') throw new Error('Observer missing');
  } catch {
    diagnostics.push('Pi observer/runtime unavailable: require Linux process evidence, lslocks and the matching public observer package');
  }
  packet.diagnostics = diagnostics;
  return classifyCandidates(packet, observer, signal);
}
