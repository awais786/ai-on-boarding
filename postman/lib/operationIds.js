'use strict';

// Stamps operationId onto each generated Postman collection item by matching it
// against the OpenAPI schema's own paths - see generate_collection.js for why this
// is necessary (openapi-to-postmanv2 has no native operationId field on an item).
// Kept separate from generate_collection.js (the CLI/file I/O wrapper) so it can be
// unit tested directly - see test/operationIds.test.js.

function schemaOperationIds(schemaJson) {
  const byMethodAndPath = {};
  for (const [schemaPathTemplate, operations] of Object.entries(schemaJson.paths || {})) {
    for (const [method, operation] of Object.entries(operations)) {
      if (!operation || typeof operation !== 'object' || !operation.operationId) {
        continue;
      }
      const key = `${method.toUpperCase()} ${schemaPathTemplate}`;
      byMethodAndPath[key] = operation.operationId;
    }
  }
  return byMethodAndPath;
}

// Postman represents a path as segments (e.g. ['api', 'signup', '']) and a path
// variable as ':name'; OpenAPI represents the same path as '/api/signup/' with
// variables as '{name}'. Reassembling to OpenAPI's form is what makes the lookup
// above work regardless of which style either side happens to use.
function toSchemaPath(urlPath) {
  return '/' + urlPath.map((segment) => segment.replace(/^:(.+)/, '{$1}')).join('/');
}

function stampOperationIds(items, operationIdsByMethodAndPath) {
  const unmatched = [];
  const walk = (nodes) => {
    for (const item of nodes) {
      if (item.item) {
        walk(item.item);
        continue;
      }
      const method = item.request.method.toUpperCase();
      const schemaPathForItem = toSchemaPath(item.request.url.path);
      const operationId = operationIdsByMethodAndPath[`${method} ${schemaPathForItem}`];
      if (operationId) {
        item.operationId = operationId;
      } else {
        unmatched.push(`${method} ${schemaPathForItem} ("${item.name}")`);
      }
    }
  };
  walk(items);
  return unmatched;
}

module.exports = { schemaOperationIds, toSchemaPath, stampOperationIds };
