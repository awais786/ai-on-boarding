'use strict';

// Reads the generated collection (endpoint coverage) and the assertions library
// (behavioural checks, from openspec/specs/ - see assertions/*.json and
// assertions/requests/*.json), combines them via lib/merge.js, and writes
// collection.merged.json - the file Newman actually runs. See design.md, "Assertions
// live in a committed library... a merge step combines them at run time."

const fs = require('fs');
const path = require('path');
const { mergeAssertions } = require('./lib/merge');

const ASSERTIONS_DIR = path.join(__dirname, 'assertions');
const REQUESTS_DIR = path.join(ASSERTIONS_DIR, 'requests');
const GENERATED_PATH = process.argv[2] || path.join(__dirname, 'collection.generated.json');
const OUT_PATH = process.argv[3] || path.join(__dirname, 'collection.merged.json');

// Fixtures created for one capability are consumed by another (the shared signup
// fixture account signin and password-reset both sign in with), so operation order
// matters and can't be left to the generated collection's own (alphabetical-by-path)
// order - see design.md and postman/README.md.
const OPERATION_ORDER = [
  'signup_create',
  'signin_create',
  'password_reset_create',
  'password_reset_confirm_create',
  'health_retrieve',
];

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function loadEntries() {
  return fs
    .readdirSync(ASSERTIONS_DIR)
    .filter((name) => name.endsWith('.json') && name !== 'out_of_scope.json')
    .flatMap((name) => readJson(path.join(ASSERTIONS_DIR, name)).entries);
}

function loadFragments() {
  if (!fs.existsSync(REQUESTS_DIR)) {
    return [];
  }
  return fs
    .readdirSync(REQUESTS_DIR)
    .filter((name) => name.endsWith('.json'))
    .flatMap((name) => readJson(path.join(REQUESTS_DIR, name)).fragments);
}

const generatedCollection = readJson(GENERATED_PATH);
const entries = loadEntries();
const fragments = loadFragments();

const { collection, orphaned, operationIds } = mergeAssertions({
  generatedCollection,
  entries,
  fragments,
  operationOrder: OPERATION_ORDER,
});

if (orphaned.length > 0) {
  console.error('Orphaned assertion(s)/fragment(s) - operationId or variant matched nothing:');
  orphaned.forEach((entry) => console.error(`  - ${JSON.stringify(entry)}`));
  process.exit(1);
}

// OPERATION_ORDER is a hand-maintained constant, not data validated elsewhere - a
// typo'd operationId in it is otherwise silently dropped (see design.md's noted
// operationId-drift risk), quietly breaking the cross-capability fixture ordering
// the comment above depends on. Not fatal on its own (the id might just be for an
// operation that's since been removed), but worth a loud warning either way.
const unknownOrderIds = OPERATION_ORDER.filter((id) => !operationIds.includes(id));
if (unknownOrderIds.length > 0) {
  console.warn(`OPERATION_ORDER lists operationId(s) not present in this run: ${unknownOrderIds.join(', ')}`);
}

fs.writeFileSync(OUT_PATH, JSON.stringify(collection, null, 2));
console.log(`Wrote ${OUT_PATH} (${collection.item.length} requests)`);
