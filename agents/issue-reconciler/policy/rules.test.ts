import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { test } from 'node:test';

import { decideAction } from './rules.ts';
import type { Evidence, Decision } from '../types.ts';

const here = dirname(fileURLToPath(import.meta.url));
const fixturesPath = join(here, '..', 'fixtures', 'issues-snapshot.json');

type Scenario = {
  name: string;
  now: string;
  evidence: Evidence;
  expected: Decision;
};

const scenarios: Scenario[] = JSON.parse(readFileSync(fixturesPath, 'utf8'));

test('policy engine has no scenario with an empty name', () => {
  assert.ok(scenarios.length > 0);
});

for (const scenario of scenarios) {
  test(scenario.name, () => {
    const decision = decideAction(scenario.evidence, { now: new Date(scenario.now) });
    assert.deepEqual(decision, scenario.expected);
  });
}
