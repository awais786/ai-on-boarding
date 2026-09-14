import assert from 'node:assert/strict';
import { test } from 'node:test';

import { appendEntry, findLatestForIssue, type RunLogEntry } from './runlog.ts';

function entry(overrides: Partial<RunLogEntry>): RunLogEntry {
  return {
    runId: 'run-1',
    issueNumber: 1,
    decision: 'noop',
    reason: 'no evidence',
    evidenceHash: 'abc',
    timestamp: '2026-09-14T00:00:00.000Z',
    ...overrides,
  };
}

test('findLatestForIssue returns null when the issue has no entries', () => {
  assert.equal(findLatestForIssue([], 1), null);
});

test('findLatestForIssue returns the most recent entry for that issue only', () => {
  let log = appendEntry([], entry({ issueNumber: 1, evidenceHash: 'first' }));
  log = appendEntry(log, entry({ issueNumber: 2, evidenceHash: 'other-issue' }));
  log = appendEntry(log, entry({ issueNumber: 1, evidenceHash: 'second' }));

  const latest = findLatestForIssue(log, 1);

  assert.equal(latest?.evidenceHash, 'second');
});

test('appendEntry does not mutate the original log', () => {
  const original: RunLogEntry[] = [];
  const updated = appendEntry(original, entry({}));

  assert.equal(original.length, 0);
  assert.equal(updated.length, 1);
});
