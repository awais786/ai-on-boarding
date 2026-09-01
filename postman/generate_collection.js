'use strict';

// Converts the OpenAPI schema (postman/schema.json, written by `make schema` in
// sdd_django_demo/) into a Postman collection - see design.md, "Generate the schema
// with manage.py spectacular... Convert schema to a collection with openapi-to-postmanv2".
// This is the "what endpoints exist" half of the pipeline; it knows nothing about
// expected behaviour. merge_assertions.js attaches that separately, joining on the
// `operationId` stampOperationIds (lib/operationIds.js) stamps onto every request below.

const fs = require('fs');
const path = require('path');
const converter = require('openapi-to-postmanv2');
const { schemaOperationIds, stampOperationIds } = require('./lib/operationIds');

const schemaPath = process.argv[2] || path.join(__dirname, 'schema.json');
const outPath = process.argv[3] || path.join(__dirname, 'collection.generated.json');

const CONVERT_OPTIONS = {
  requestParametersResolution: 'Example',
  optionalParametersInclusion: 'Exclude',
  // 'raw' (JSON) rather than the default first-listed content-type, which this
  // API's schema resolves to application/x-www-form-urlencoded - a real client
  // exercising this API sends JSON, and assertions are easier to write against
  // JSON request bodies.
  preferredRequestBodyType: 'raw',
};

const schemaText = fs.readFileSync(schemaPath, 'utf8');
const schemaJson = JSON.parse(schemaText);

converter.convertV2({ type: 'string', data: schemaText }, CONVERT_OPTIONS, (err, conversionResult) => {
  if (err) {
    console.error('Conversion failed:', err);
    process.exit(1);
  }
  if (!conversionResult.result) {
    console.error('Conversion failed:', conversionResult.reason);
    process.exit(1);
  }

  const collection = conversionResult.output[0].data;
  const unmatched = stampOperationIds(collection.item, schemaOperationIds(schemaJson));

  if (unmatched.length > 0) {
    console.error(
      'Generated request(s) with no matching OpenAPI operationId (schema/converter drifted apart):'
    );
    unmatched.forEach((entry) => console.error(`  - ${entry}`));
    process.exit(1);
  }

  fs.writeFileSync(outPath, JSON.stringify(collection, null, 2));
  console.log(`Wrote ${outPath}`);
});
