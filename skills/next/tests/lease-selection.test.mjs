import assert from 'node:assert/strict';
import test from 'node:test';
import { classifyCandidates, renderSafeList } from '../pi/lease-selection.mjs';

const candidate = (id, roots = ['/api'], state = 'declared', labels = []) => ({
  id, selector: `workspace:${id}`, repository: 'workspace', title: id, priority: 2, issue_type: 'task', labels,
  source_scope: { state, roots, reason: 'fixture declaration' },
});
const packet = (candidates, in_progress = []) => ({ version: 1, workspace: true, candidates, in_progress, diagnostics: [] });

test('keeps proven free unlabelled work eligible, separates held, unknown and tracker conflicts', async () => {
  const seen = [];
  const observer = async (roots, options) => {
    seen.push(roots);
    assert.equal(options.runtimeDir, undefined);
    assert.equal(options.selfPid, undefined);
    return roots.map(root => ({ root, kind: root === '/busy' ? 'held' : 'free' }));
  };
  const result = await classifyCandidates(packet([
    candidate('free'), candidate('multi', ['/api', '/busy']), candidate('unknown', [], 'unknown'),
    candidate('partial', ['/api'], 'partial'), candidate('claimed', ['/api'], 'declared', ['web']),
  ], [{ repository: 'workspace', labels: ['web'] }]), observer);
  assert.deepEqual(result.eligible.map(row => row.id), ['free']);
  assert.deepEqual(result.occupied.map(row => row.id), ['multi']);
  assert.deepEqual(result.unknown.map(row => row.id), ['unknown', 'partial']);
  assert.deepEqual(result.tracker_conflicts.map(row => row.id), ['claimed']);
  assert.equal(seen.length, 1);
  assert.deepEqual(seen[0], ['/api', '/busy']);
  assert.match(result.coverage, /not a reservation/);
});

test('safe display keeps the familiar ranking with explicit lease checks, no empty diagnostics', async () => {
  const unknown = candidate('unknown', [], 'unknown');
  const free = candidate('free');
  const unavailable = candidate('unavailable', ['/missing']);
  const overlap = candidate('overlap', [], 'unknown', ['web']);
  const held = candidate('held', ['/busy'], 'declared', ['web']);
  const data = packet([unknown, free, unavailable, overlap, held], [{ id: 'active', repository: 'workspace', labels: ['web'] }]);
  const result = await classifyCandidates(data, async roots => roots.map(root => root === '/missing'
    ? { kind: 'unavailable', reason: 'no observation' } : { kind: root === '/busy' ? 'held' : 'free', root }));
  const output = renderSafeList(result);
  assert.match(output, /## Ready to review \(3 beads\)/);
  assert.match(output, /\| # \| Repo \| ID \| Pri \| Type \| Labels \| Title \| Lease check \|/);
  assert.match(output, /\| 1 \| workspace \| unknown \| P2 \| task \| - \| unknown \| Not checked: scope unknown \|/);
  assert.match(output, /\| 2 \| workspace \| free .*Checked free/);
  assert.match(output, /\| 3 \| workspace \| unavailable .*Not checked: unavailable/);
  const main = output.split('## Occupied')[0];
  assert.doesNotMatch(main, /\| held \||\| overlap \|/);
  assert.match(output, /## Occupied \(1 bead\)/);
  assert.match(output, /## Tracker label overlap \(1 bead\)/);
  assert.match(output, /overlap.*active/);
  assert.doesNotMatch(output, /Eligible under observed|## Unknown|## Observation unavailable|_None\._/);
  assert.match(output, /Numbers are for review/);
  assert.match(output, /Selector = Repo:ID/);
  assert.match(output, /no observation|observer unavailable/);
});

test('local unknown-only display does not pretend no work or expose selector boilerplate in each row', async () => {
  const data = packet([candidate('a', [], 'unknown'), candidate('b', [], 'partial')]);
  data.workspace = false;
  data.candidates[1].source_scope.roots = ['/partial'];
  for (const row of data.candidates) { row.repository = 'local'; row.selector = `local:${row.id}`; }
  const result = await classifyCandidates(data);
  const output = renderSafeList(result);
  assert.match(output, /\| # \| ID \| Pri \| Type \| Labels \| Title \| Lease check \|/);
  assert.match(output, /\| 1 \| a .*Not checked: scope unknown/);
  assert.match(output, /\| 2 \| b .*Not checked: scope incomplete/);
  assert.doesNotMatch(output, /\| local:a \||None eligible|## Occupied/);
  assert.match(output, /local:ID/);
  assert.match(output, /Unknown does not mean occupied/);
});

test('rendering escapes tracker text and preserves typed unknown queues', async () => {
  const row = candidate('a', [], 'unknown');
  row.title = 'a|b\n\u001b[31m';
  const result = await classifyCandidates(packet([row]));
  assert.deepEqual(result.unknown.map(r => r.id), ['a']);
  assert.deepEqual(result.eligible, []);
  const output = renderSafeList(result);
  assert.match(output, /a&#124;b/);
  assert.doesNotMatch(output, /\u001b/);
});

test('malformed, missing, partial and wrong-root observations cannot certify safety', async () => {
  for (const observer of [undefined, async () => [], async () => [{ kind: 'free', root: '/parent' }],
    async () => [{ kind: 'unavailable', reason: 'no lslocks' }], async () => { throw Error('failure'); }]) {
    const result = await classifyCandidates(packet([candidate('a')]), observer);
    assert.equal(result.eligible.length, 0);
    assert.equal(result.unavailable.length, 1);
  }
});

test('an occupied root still excludes work when another observation is unavailable', async () => {
  const result = await classifyCandidates(packet([candidate('a', ['/one', '/two'])]), async () => [
    { kind: 'unavailable', reason: 'unknown' }, { kind: 'held', root: '/two' },
  ]);
  assert.equal(result.occupied.length, 1);
  assert.equal(result.eligible.length, 0);
});

test('batch overflow remains inspectable, never silently truncates or launches extra scans', async () => {
  let calls = 0;
  const result = await classifyCandidates(packet(Array.from({ length: 33 }, (_, i) => candidate(String(i), [`/r${i}`]))), async () => { calls++; return []; });
  assert.equal(calls, 0);
  assert.equal(result.unavailable.length, 33);
  assert.equal(result.eligible.length, 0);
});

test('cancellation bounds an observer that never resolves', async () => {
  const controller = new AbortController();
  const pending = classifyCandidates(packet([candidate('a')]), async () => new Promise(() => {}), controller.signal);
  controller.abort();
  const result = await pending;
  assert.equal(result.eligible.length, 0);
  assert.equal(result.unavailable.length, 1);
});

test('malformed scope packets and repeated identities fail rather than becoming eligible', async () => {
  for (const data of [packet([candidate('a', [])]), packet([candidate('a'), candidate('a')]), packet([candidate('a', ['relative'])])]) {
    await assert.rejects(classifyCandidates(data, async roots => roots.map(root => ({ kind: 'free', root }))));
  }
});

test('a fresh selected observation can reject work which was previously free', async () => {
  let held = false;
  const observer = async roots => roots.map(root => ({ root, kind: held ? 'held' : 'free' }));
  const data = packet([candidate('a')]);
  assert.equal((await classifyCandidates(data, observer)).eligible.length, 1);
  held = true;
  assert.equal((await classifyCandidates(data, observer)).occupied.length, 1);
});
