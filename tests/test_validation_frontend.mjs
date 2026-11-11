import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

import {
  instanceOfValidationError,
  ValidationErrorFromJSON,
  ValidationErrorToJSON,
} from '../sdk/typescript/models/ValidationError.ts';

test('validation model accepts real field and index locations and round trips', () => {
  const error = {
    loc: ['body', 'items', 0, 'name'],
    msg: 'Field required',
    type: 'missing',
    input: null,
    ctx: { limit: 3 },
  };
  assert.equal(instanceOfValidationError(error), true);
  assert.deepEqual(ValidationErrorToJSON(ValidationErrorFromJSON(error)), error);
  for (const invalid of [null, {}, { ...error, loc: ['body', true] },
    { ...error, loc: ['body', 1.5] }, { ...error, ctx: [] },
    { ...error, msg: 42 }]) {
    assert.equal(instanceOfValidationError(invalid), false);
    assert.throws(() => ValidationErrorFromJSON(invalid), TypeError);
  }
});

test('unified browser client reports structured and plain validation errors', async () => {
  const script = await readFile(new URL('../frontend/aether_client.js', import.meta.url), 'utf8');
  let result;
  const window = {};
  vm.runInNewContext(script, {
    window,
    fetch: async () => ({ ok: false, status: 422, json: async () => result }),
    console,
  });
  result = { detail: [{ loc: ['body', 'items', 0, 'name'], msg: 'Field required',
    type: 'missing', input: 'private value' }] };
  await assert.rejects(window.AetherClient.dispatchUnified({ node: 'A', event: 'B' }),
    (error) => error.status === 422 &&
      error.message === 'body.items.0.name: Field required' &&
      !error.message.includes('private value'));
  result = { detail: 'Prompt cannot be blank.' };
  await assert.rejects(window.AetherClient.dispatchUnified({ node: 'A', event: 'B' }),
    (error) => error.message === 'Prompt cannot be blank.');
  result = { detail: [{ loc: [true], msg: 'bad' }] };
  await assert.rejects(window.AetherClient.dispatchUnified({ node: 'A', event: 'B' }),
    (error) => error.message === 'Unified dispatch HTTP 422');
});
