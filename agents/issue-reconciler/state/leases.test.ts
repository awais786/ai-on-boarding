import assert from 'node:assert/strict';
import { test } from 'node:test';

import { acquireLease, isLeased, releaseLease } from './leases.ts';

const NOW = new Date('2026-09-14T12:00:00.000Z');
const TTL = 5 * 60 * 1000;

test('acquiring a lease on an unleased issue succeeds', () => {
  const result = acquireLease({}, 1, TTL, NOW);
  assert.ok(result);
  assert.ok(isLeased(result, 1, NOW));
});

test('acquiring a lease on an already-leased, unexpired issue fails', () => {
  const leased = acquireLease({}, 1, TTL, NOW)!;
  const result = acquireLease(leased, 1, TTL, NOW);
  assert.equal(result, null);
});

test('a lease can be reacquired once it has expired', () => {
  const leased = acquireLease({}, 1, TTL, NOW)!;
  const later = new Date(NOW.getTime() + TTL + 1000);
  assert.equal(isLeased(leased, 1, later), false);
  assert.ok(acquireLease(leased, 1, TTL, later));
});

test('releasing a lease removes it and does not affect other issues', () => {
  let state = acquireLease({}, 1, TTL, NOW)!;
  state = acquireLease(state, 2, TTL, NOW)!;

  const released = releaseLease(state, 1);

  assert.equal(isLeased(released, 1, NOW), false);
  assert.ok(isLeased(released, 2, NOW));
});
