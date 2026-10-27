import assert from 'node:assert/strict';
import test from 'node:test';
import { classifyCandidates, renderSafeList } from '../pi/lease-selection.ts';

const candidate = (id, roots = ['/api'], state = 'declared', labels = [], services = labels) => ({
  id, selector: `workspace:${id}`, repository: 'workspace', title: id, priority: 2, issue_type: 'task', labels, services,
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
    candidate('topical', ['/api'], 'declared', ['marketing'], []),
  ], [{ id: 'active', repository: 'workspace', labels: ['web', 'marketing'], services: ['web'] }]), observer);
  assert.deepEqual(result.eligible.map(row => row.id), ['free', 'topical']);
  assert.deepEqual(result.occupied.map(row => row.id), ['multi']);
  assert.deepEqual(result.unknown.map(row => row.id), ['unknown', 'partial']);
  assert.deepEqual(result.tracker_conflicts.map(row => row.id), ['claimed']);
  assert.deepEqual(result.tracker_conflicts[0].shared_services, ['web']);
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
  const data = packet([unknown, free, unavailable, overlap, held], [{ id: 'active', repository: 'workspace', labels: ['web'], services: ['web'] }]);
  const result = await classifyCandidates(data, async roots => roots.map(root => root === '/missing'
    ? { kind: 'unavailable', reason: 'no observation' } : { kind: root === '/busy' ? 'held' : 'free', root }));
  const output = renderSafeList(result);
  assert.match(output, /## Ready to review \(3 beads\)/);
  assert.match(output, /\| # \| Repo \| ID \| Pri \| Type \| Labels \| Title \| Lease check \|/);
  assert.match(output, /\| 1 \| workspace \| unknown \| P2 \| task \| - \| unknown \| unknown \|/);
  assert.match(output, /\| 2 \| workspace \| free .*\| free \|/);
  assert.match(output, /\| 3 \| workspace \| unavailable .*\| n\/a \|/);
  const main = output.split('## Occupied')[0];
  assert.doesNotMatch(main, /\| held \||\| overlap \|/);
  assert.match(output, /## Occupied — source held by another Pi session \(1 bead\)/);
  assert.match(output, /## Held back — same service as in-progress work \(1 bead\)/);
  assert.match(output, /labels only, not lease evidence/);
  assert.match(output, /\| Lease check \| Shared service \|/);
  assert.match(output, /\| overlap \|.*\| web \(active\) \|/);
  assert.match(output, /## Claimed — in progress \(1; not selectable\)/);
  assert.doesNotMatch(output, /Tracker label overlap/);
  assert.doesNotMatch(output, /Eligible under observed|## Unknown|## Observation unavailable|_None\._/);
  assert.match(output, /Numbers are for review/);
  assert.match(output, /picking a not-checked row starts ordinary, not lease-checked, work/);
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
  assert.match(output, /\| 1 \| a .*\| unknown \|/);
  assert.match(output, /\| 2 \| b .*\| partial \|/);
  assert.doesNotMatch(output, /\| local:a \||None eligible|## Occupied/);
  assert.match(output, /local:ID/);
  assert.match(output, /unknown = no source_scope declaration/);
});

const downStore = { repository: 'down', reason: 'ready: Dolt server unreachable', hint: 'Dolt server not running. Start it manually: `bd -C /down dolt start`, then rerun /next.' };

test('all-unavailable safe view leads with the store notice instead of an empty backlog', async () => {
  const data = { ...packet([]), unavailable_stores: [downStore] };
  const result = await classifyCandidates(data);
  assert.deepEqual(result.unavailable_stores, [downStore]);
  for (const queue of ['eligible', 'occupied', 'unknown', 'unavailable', 'tracker_conflicts']) assert.deepEqual(result[queue], []);
  const output = renderSafeList(result);
  assert.ok(output.startsWith('## ⚠️ Beads store unavailable (1)'), output);
  assert.match(output, /not an empty backlog/);
  assert.match(output, /- \*\*down\*\* — Dolt server not running\. Start it manually: `bd -C \/down dolt start`/);
  assert.match(output, /Ready work unknown/);
  assert.doesNotMatch(output, /_No candidates without|Lease check: 0 free, 0 not checked/);
});

test('partial store failure keeps healthy rows and flags only the failed store', async () => {
  const broken = { repository: 'broken', reason: 'blocked: simulated a|b failure\u001b', hint: null };
  const result = await classifyCandidates({ ...packet([candidate('healthy', [], 'unknown')]), unavailable_stores: [downStore, broken] });
  const output = renderSafeList(result);
  const [notice, rest] = output.split('## Ready to review (1 beads)');
  assert.match(notice, /## ⚠️ Beads store unavailable \(2\)/);
  assert.match(notice, /\*\*broken\*\* — blocked: simulated a\|b failure /);
  assert.doesNotMatch(notice, /\u001b|&#124;/);
  assert.doesNotMatch(notice, /healthy/);
  assert.match(rest, /\| 1 \| workspace \| healthy .*\| unknown \|/);
  assert.match(rest, /Lease check: 0 free, 1 not checked/);
  assert.doesNotMatch(renderSafeList(await classifyCandidates(packet([candidate('ok', [], 'unknown')]))), /Beads store unavailable/);
});

test('malformed unavailable-store entries are rejected and legacy packets default to none', async () => {
  for (const stores of [{}, [null], [{ repository: 1, reason: 'x' }], [{ repository: 'a', reason: 'x', hint: 3 }]]) {
    await assert.rejects(classifyCandidates({ ...packet([]), unavailable_stores: stores }), /Invalid unavailable-store packet/);
  }
  assert.deepEqual((await classifyCandidates(packet([]))).unavailable_stores, []);
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

test('a held service-label root demotes undeclared work; other label observations never change it', async () => {
  const labelled = (id, serviceRoots) => ({ ...candidate(id, [], 'unknown', ['svc'], ['svc']), service_roots: serviceRoots });
  const declared = { ...candidate('declared', ['/api'], 'declared', ['svc'], ['svc']), service_roots: ['/free-svc'] };
  const data = packet([labelled('busy', ['/held-svc']), labelled('quiet', ['/free-svc']), labelled('odd', ['/plain-dir']), declared]);
  const seen = [];
  const result = await classifyCandidates(data, async roots => {
    seen.push(roots);
    return roots.map(root => root === '/plain-dir' ? { kind: 'unavailable', reason: 'not a Git root' }
      : { root, kind: root === '/held-svc' ? 'held' : 'free' });
  });
  assert.deepEqual(seen, [['/api', '/held-svc', '/free-svc', '/plain-dir']]);
  assert.deepEqual(result.occupied.map(row => row.id), ['busy']);
  assert.deepEqual(result.occupied[0].label_occupancy, [{ root: '/held-svc', kind: 'held', service: 'svc' }]);
  assert.deepEqual(result.unknown.map(row => row.id), ['quiet', 'odd']);
  assert.deepEqual(result.eligible.map(row => row.id), ['declared']);
  const output = renderSafeList(result);
  assert.match(output, /## Occupied — source held by another Pi session \(1 bead\)/);
  assert.match(output, /\| busy \|.*\| held \(label\) \| svc \|/);
  assert.doesNotMatch(output, /plain-dir|not a Git root/);
});

test('mismatched service labels and roots are rejected', async () => {
  const bad = { ...candidate('bad', [], 'unknown', ['a'], ['a']), service_roots: ['/a', '/b'] };
  await assert.rejects(classifyCandidates(packet([bad])), /Invalid source-scope packet/);
});

test('other-machine rows remain visible but never enter occupancy or eligible queues', async () => {
  const other = { ...candidate('remote', ['/remote']),
    machine_eligibility: { eligible: false, state: 'mismatch', reason: 'requires leonidas' } };
  const machine = { id: 'rivelino', source: '/home/test/.agents/AGENTS.local.md', state: 'ok', reason: 'user local context' };
  const data = { ...packet([candidate('here')]), machine, other_machines: [other] };
  const seen = [];
  const result = await classifyCandidates(data, async roots => {
    seen.push(...roots);
    return roots.map(root => ({ root, kind: 'free' }));
  });
  assert.deepEqual(seen, ['/api']);
  assert.deepEqual(result.eligible.map(row => row.id), ['here']);
  assert.equal(result.other_machines[0].id, 'remote');
  const text = renderSafeList(result);
  assert.match(text, /Machine: rivelino/);
  const [foreign, ready] = text.split('## Ready to review');
  assert.match(foreign, /## Other machines/);
  assert.match(foreign, /requires leonidas/);
  assert.doesNotMatch(foreign, /\| # \||\| free \|/);
  assert.doesNotMatch(ready, /remote/);
  await assert.rejects(classifyCandidates({ ...data, machine: { id: 'rivelino' } }), /machine identity/);
  await assert.rejects(classifyCandidates({ ...data, other_machines: [{ ...other, labels: 'broken' }] }), /other-machine/);
  await assert.rejects(classifyCandidates({ ...packet([other]), machine }), /source-scope/);
  await assert.rejects(classifyCandidates({ ...data, other_machines: [{ ...other, selector: 'workspace:here' }] }), /Duplicate/);
});

test('elapsed wake dates are marked in the deferred table without touching ready rows', async () => {
  const deferred = (id, defer_until, defer_elapsed) => ({ id, repository: 'workspace', title: id, priority: 3, issue_type: 'task', labels: [], defer_until, defer_elapsed });
  const free = async roots => roots.map(root => ({ root, kind: 'free' }));
  const data = { ...packet([candidate('ready')]), deferred: [
    deferred('elapsed', '2000-01-01T00:00:00Z', true), deferred('future', '2999-12-31T23:59:59Z', false),
    deferred('icebox', null, null), deferred('text', 'soon', null), deferred('spoofed', '2000-01-01T00:00:00Z', 'true'),
  ] };
  const output = renderSafeList(await classifyCandidates(data, free));
  const [before, rest] = output.split('## Later — deferred (5; not selectable)');
  const [later, ready] = rest.split('## Ready to review (1 beads)');
  assert.doesNotMatch(before, /elapsed|⏰/);
  assert.match(ready, /\| 1 \| workspace \| ready .*\| free \|/);
  assert.doesNotMatch(ready, /elapsed|⏰/);
  assert.match(later, /^\n\n⏰ 1 elapsed wake date: still stored deferred, not ready\. Read-only listing never wakes work; review the awaited event before undeferring\.\n\n\| Repo \|/);
  assert.match(later, /\| workspace \| elapsed \| P3 \| task \| - \| elapsed \| 2000-01-01T00:00:00Z ⏰ elapsed \|/);
  assert.match(later, /\| future \| 2999-12-31T23:59:59Z \|/);
  assert.match(later, /\| icebox \| — \|/);
  assert.match(later, /\| text \| soon \|/);
  assert.match(later, /\| spoofed \| 2000-01-01T00:00:00Z \|/);
  assert.equal((later.match(/⏰ elapsed/g) ?? []).length, 1);
  const pending = renderSafeList(await classifyCandidates({ ...data, deferred: data.deferred.slice(1) }, free));
  assert.match(pending, /## Later — deferred \(4; not selectable\)\n\n\| Repo \|/);
  assert.doesNotMatch(pending, /elapsed|⏰/);
});

test('safe view renders ready work last, directly above the review footer', async () => {
  const other = { ...candidate('remote', ['/remote']), machine_eligibility: { eligible: false, state: 'mismatch', reason: 'requires leonidas' } };
  const extra = (id, fields) => ({ id, repository: 'workspace', title: id, priority: 2, issue_type: 'task', labels: [], ...fields });
  const data = {
    ...packet([candidate('free'), candidate('held', ['/busy']), candidate('overlap', [], 'unknown', ['web'])],
      [extra('active', { labels: ['web'], services: ['web'] })]),
    blocked: [extra('blocked', { blocked_by: ['dep'] })], deferred: [extra('later', { defer_until: null, defer_elapsed: null })],
    other_machines: [other], unavailable_stores: [downStore], diagnostics: ['fixture diagnostic'],
    machine: { id: 'rivelino', source: '/home/test/.agents/AGENTS.local.md', state: 'ok', reason: 'user local context' },
  };
  const output = renderSafeList(await classifyCandidates(data, async roots => roots.map(root => ({ root, kind: root === '/busy' ? 'held' : 'free' }))));
  const headings = [...output.matchAll(/^##+ [^(\n]*/gm)].map(match => match[0].trimEnd());
  assert.deepEqual(headings, ['## ⚠️ Beads store unavailable', '## Claimed — in progress', '## Waiting — blocked', '## Later — deferred',
    '### Check details', '## Other machines', '## Occupied — source held by another Pi session', '## Held back — same service as in-progress work', '## Ready to review']);
  const tail = output.split('## Ready to review (1 beads)')[1];
  assert.deepEqual(tail.trim().split('\n\n').map(block => block.split('\n')[0].slice(0, 12)), ['| # | Repo |', 'Lease check:', 'Numbers are ']);
  assert.match(tail, /\| 1 \| workspace \| free \| P2 \| task \| - \| free \| free \|/);
});

test('declared roots keep observer priority; label overflow is reported, not treated as free', async () => {
  const declaredRoots = Array.from({ length: 31 }, (_, index) => `/d${index}`);
  const data = packet([
    { ...candidate('declared', declaredRoots), service_roots: [] },
    { ...candidate('labelled', [], 'unknown', ['a', 'b'], ['a', 'b']), service_roots: ['/a', '/b'] },
  ]);
  const seen = [];
  const result = await classifyCandidates(data, async roots => { seen.push(roots); return roots.map(root => ({ root, kind: 'free' })); });
  assert.deepEqual(seen[0], [...declaredRoots, '/a']);
  assert.deepEqual(result.eligible.map(row => row.id), ['declared']);
  assert.match(result.diagnostics.join('\n'), /1 service-label root not observed/);
});
