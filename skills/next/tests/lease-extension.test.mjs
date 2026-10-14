import assert from 'node:assert/strict';
import { resolve } from 'node:path';
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
