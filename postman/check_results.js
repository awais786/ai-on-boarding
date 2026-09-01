'use strict';

// The actual pass/fail gate for this pipeline - see postman/README.md, "Known drift".
//
// Newman itself is run with --suppress-exit-code (see package.json's `newman` script)
// because two assertions are *expected* to fail forever until the drift they document
// is fixed elsewhere (see postman/README.md, "Known drift"); if Newman's raw exit code
// gated the workflow, it could never go green and a real regression would be
// indistinguishable from the two accepted failures - see design.md's "Fail the run
// when a live endpoint violates a requirement" requirement and the note under
// "Risks / Trade-offs" about drift findings needing to "surface... rather than being
// indistinguishable from a regression."
//
// This script reads Newman's own result.json and fails only on a failure whose
// assertion name is NOT tagged KNOWN DRIFT - i.e. it re-implements "fail the run on
// an unexpected assertion failure", not "fail the run on any assertion failure".
//
// Reads result.run.failures (Newman's own flat, canonical failure list), not
// result.run.executions[].assertions - a script error thrown *outside* a pm.test(...)
// wrapper (e.g. a helper line ahead of a pm.test call, which throws if a response
// body isn't valid JSON) aborts that item's whole script and fires Newman's 'script'
// event instead of an 'assertion' event: it lands in result.run.failures with no
// per-execution assertions entry at all. Walking executions[].assertions alone would
// silently miss it - confirmed by reproducing it locally (a deliberate script-level
// throw showed up in run.failures with error.test === undefined and no corresponding
// executions[].assertions entry whatsoever). A failure with no named assertion
// (error.test is undefined) can never legitimately be tagged KNOWN DRIFT, so it is
// always treated as unexpected - the startsWith check below handles that naturally.

const fs = require('fs');
const path = require('path');

const resultPath = process.argv[2] || path.join(__dirname, 'result.json');
const result = JSON.parse(fs.readFileSync(resultPath, 'utf8'));

if (!result.run || !Array.isArray(result.run.executions) || result.run.executions.length === 0) {
  console.error('result.json has no executions - the collection did not run as expected.');
  process.exit(1);
}

const unexpectedFailures = [];
const knownDriftFailures = [];

for (const failure of result.run.failures || []) {
  const assertionName = failure.error && failure.error.test;
  const itemName = failure.source && failure.source.name;
  const entry = { item: itemName, assertion: assertionName || '(script/request error, no named assertion)', message: failure.error && failure.error.message };
  const target = assertionName && assertionName.startsWith('KNOWN DRIFT') ? knownDriftFailures : unexpectedFailures;
  target.push(entry);
}

if (knownDriftFailures.length > 0) {
  console.log(`${knownDriftFailures.length} documented KNOWN DRIFT failure(s) (expected, see postman/README.md):`);
  knownDriftFailures.forEach((f) => console.log(`  - ${f.assertion} (${f.item})`));
}

if (unexpectedFailures.length > 0) {
  console.error(`${unexpectedFailures.length} unexpected failure(s):`);
  unexpectedFailures.forEach((f) => console.error(`  - ${f.assertion} (${f.item}): ${f.message}`));
  process.exit(1);
}

console.log('No unexpected failures.');
