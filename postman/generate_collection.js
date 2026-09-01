#!/usr/bin/env node
// Derives a Postman collection from the Django project's OpenAPI schema (postman/schema.json,
// produced by `make schema` in sdd_django_demo/). This is the ONLY source of what endpoints/
// requests exist in the collection - see README.md for the responsibility split. Nothing here
// hand-lists an endpoint.
'use strict';

const fs = require('fs');
const path = require('path');
const Converter = require('openapi-to-postmanv2');

const SCHEMA_PATH = path.join(__dirname, 'schema.json');
const OUTPUT_PATH = path.join(__dirname, 'collection.generated.json');

if (!fs.existsSync(SCHEMA_PATH)) {
  console.error(
    `${SCHEMA_PATH} not found. Run "make schema" in sdd_django_demo/ first.`
  );
  process.exit(1);
}

const schema = fs.readFileSync(SCHEMA_PATH, 'utf8');

Converter.convert(
  { type: 'string', data: schema },
  { requestParametersResolution: 'Example' },
  (err, result) => {
    if (err) {
      console.error('Conversion failed:', err);
      process.exit(1);
    }
    if (!result.result) {
      console.error('Conversion reported failure:', result.reason);
      process.exit(1);
    }

    const collection = result.output[0].data;
    fs.writeFileSync(OUTPUT_PATH, JSON.stringify(collection, null, 2));

    const requestCount = countRequests(collection.item || []);
    console.log(`Wrote ${OUTPUT_PATH} (${requestCount} request(s)).`);
  }
);

function countRequests(items) {
  let count = 0;
  for (const item of items) {
    if (item.item) {
      count += countRequests(item.item);
    } else if (item.request) {
      count += 1;
    }
  }
  return count;
}
