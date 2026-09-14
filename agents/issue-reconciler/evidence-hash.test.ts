import assert from 'node:assert/strict';
import { test } from 'node:test';

import { hashEvidence } from './evidence-hash.ts';
import type { Evidence } from './types.ts';

const BASE: Evidence = {
  issueNumber: 1,
  itemId: 'PVTI_1',
  currentStatus: 'Todo',
  hasIgnoreLabel: false,
  linkedPRs: [],
  openSpecProposals: [],
  lastStatusActor: null,
  lastStatusAt: null,
  transitionCount: 0,
};

test('is stable across object key insertion order', () => {
  const reordered: Evidence = {
    transitionCount: 0,
    issueNumber: 1,
    lastStatusAt: null,
    itemId: 'PVTI_1',
    hasIgnoreLabel: false,
    currentStatus: 'Todo',
    linkedPRs: [],
    lastStatusActor: null,
    openSpecProposals: [],
  };

  assert.equal(hashEvidence(BASE), hashEvidence(reordered));
});

test('changes when a meaningful field changes', () => {
  const changed: Evidence = { ...BASE, currentStatus: 'In Progress' };
  assert.notEqual(hashEvidence(BASE), hashEvidence(changed));
});

test('is sensitive to array element order', () => {
  const a: Evidence = { ...BASE, openSpecProposals: ['a', 'b'] };
  const b: Evidence = { ...BASE, openSpecProposals: ['b', 'a'] };
  assert.notEqual(hashEvidence(a), hashEvidence(b));
});
