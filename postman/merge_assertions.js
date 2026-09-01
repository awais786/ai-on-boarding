#!/usr/bin/env node
// Attaches behavioural assertions (sourced from the OpenSpec specs, see assertions/*.json) to
// the collection generated purely from the OpenAPI schema (see generate_collection.js).
//
// This is the one place the two independent inputs - "what endpoints exist" (OpenAPI) and "how
// they should behave" (specs, via the assertions library) - are combined. The join key is the
// OpenAPI `operationId`, never a hand-picked endpoint list: an assertions entry whose
// operationId has no matching request in the generated collection is simply never attached (and
// is left for the Claude evaluation step to notice as a mismatch), and a generated request with
// no assertions entries at all still gets a default check so nothing is silently unchecked. See
// README.md. The actual merge logic lives in lib/merge.js so it can be unit tested (see
// test/merge.test.js) without touching the filesystem - this file is just the CLI wrapper.
'use strict';

const fs = require('fs');
const path = require('path');
const { mergeAssertions } = require('./lib/merge');

const SCHEMA_PATH = path.join(__dirname, 'schema.json');
const COLLECTION_PATH = path.join(__dirname, 'collection.generated.json');
const ASSERTIONS_DIR = path.join(__dirname, 'assertions');
const REQUESTS_DIR = path.join(ASSERTIONS_DIR, 'requests');
const OUTPUT_PATH = path.join(__dirname, 'collection.merged.json');

for (const p of [SCHEMA_PATH, COLLECTION_PATH]) {
  if (!fs.existsSync(p)) {
    console.error(`${p} not found. Run "npm run generate" first (after "make schema").`);
    process.exit(1);
  }
}

function loadJsonFilesIn(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .flatMap((f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')));
}

const schema = JSON.parse(fs.readFileSync(SCHEMA_PATH, 'utf8'));
const collection = JSON.parse(fs.readFileSync(COLLECTION_PATH, 'utf8'));
const fragments = loadJsonFilesIn(REQUESTS_DIR);

// out_of_scope.json documents deliberately-excluded requirements for the Claude evaluation step
// (see README.md) - it carries no operationId/entries and is not itself an assertions file.
const assertionDocs = fs
  .readdirSync(ASSERTIONS_DIR)
  .filter((f) => f.endsWith('.json') && f !== 'out_of_scope.json')
  .map((f) => JSON.parse(fs.readFileSync(path.join(ASSERTIONS_DIR, f), 'utf8')));

const { collection: merged, stats } = mergeAssertions(schema, collection, assertionDocs, fragments);

fs.writeFileSync(OUTPUT_PATH, JSON.stringify(merged, null, 2));

console.log(`Wrote ${OUTPUT_PATH}`);
console.log(`  assertions attached: ${stats.attached}`);
console.log(`  assertions unmatched (no corresponding request): ${stats.unmatched}`);
console.log(`  requests with only the default status check: ${stats.defaultChecks}`);
