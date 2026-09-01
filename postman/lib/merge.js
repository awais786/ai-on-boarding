// Pure merge logic, factored out of merge_assertions.js so it's testable without touching the
// filesystem (see test/merge.test.js). merge_assertions.js is the thin CLI wrapper: it reads
// schema.json/collection.generated.json/assertions/*, calls mergeAssertions(), and writes
// collection.merged.json.
'use strict';

const crypto = require('crypto');

function buildOperationIdByPathMethod(schema) {
  const map = {};
  for (const [urlPath, methods] of Object.entries(schema.paths || {})) {
    for (const [method, operation] of Object.entries(methods)) {
      if (operation && operation.operationId) {
        map[`${method.toUpperCase()} ${urlPath}`] = operation.operationId;
      }
    }
  }
  return map;
}

function requestPath(item) {
  const url = item.request.url;
  const segments = Array.isArray(url.path) ? url.path : [];
  return '/' + segments.join('/');
}

function operationIdForItem(item, operationIdByPathMethod) {
  const key = `${item.request.method.toUpperCase()} ${requestPath(item)}`;
  return operationIdByPathMethod[key];
}

function parentArrayOf(items, target) {
  for (const item of items) {
    if (item === target) return items;
    if (item.item) {
      const found = parentArrayOf(item.item, target);
      if (found) return found;
    }
  }
  return null;
}

function defaultCheckEvent() {
  return {
    listen: 'test',
    script: {
      type: 'text/javascript',
      exec: [
        '// No assertions library entry for this request - default check only (see README.md).',
        "pm.test('no server error (default check - no assertions library entry)', function () {",
        "  pm.expect(pm.response.code, 'expected no unhandled server error (5xx)').to.be.below(500);",
        '});',
      ],
    },
  };
}

/**
 * @param {object} schema - parsed OpenAPI schema.json
 * @param {object} collection - parsed collection.generated.json (mutated and returned)
 * @param {object[]} assertionDocs - parsed assertions/*.json (excluding out_of_scope.json), each
 *   `{capability, operationId, entries: [{requirement, variant, script}]}`
 * @param {object[]} fragments - parsed assertions/requests/*.json entries, each
 *   `{operationId, variant, name, body?, pre_request_script?}`
 * @param {() => string} [idGenerator] - overridable for deterministic tests
 * @returns {{collection: object, stats: {attached: number, unmatched: number, defaultChecks: number}}}
 */
function mergeAssertions(schema, collection, assertionDocs, fragments, idGenerator) {
  const newId = idGenerator || (() => crypto.randomUUID());
  const operationIdByPathMethod = buildOperationIdByPathMethod(schema);

  const baseItemsByOperationId = {};
  (function indexBaseItems(items) {
    items.forEach((item) => {
      if (item.item) {
        indexBaseItems(item.item);
        return;
      }
      if (!item.request) return;
      const operationId = operationIdForItem(item, operationIdByPathMethod);
      if (!operationId || baseItemsByOperationId[operationId]) return;
      baseItemsByOperationId[operationId] = item;
    });
  })(collection.item || []);

  const fragmentItemsByOperationVariant = {};
  const insertionCursor = {};

  for (const fragment of fragments || []) {
    const baseItem = baseItemsByOperationId[fragment.operationId];
    if (!baseItem) continue;

    const clone = JSON.parse(JSON.stringify(baseItem));
    clone.id = newId();
    clone.name = fragment.name;
    clone.event = [];

    if (fragment.body !== undefined) {
      clone.request.body = {
        mode: 'raw',
        raw: JSON.stringify(fragment.body, null, 2),
        options: { raw: { language: 'json' } },
      };
      clone.request.header = (clone.request.header || []).filter(
        (h) => h.key.toLowerCase() !== 'content-type'
      );
      clone.request.header.push({ key: 'Content-Type', value: 'application/json' });
    }

    if (fragment.pre_request_script) {
      clone.event.push({
        listen: 'prerequest',
        script: { type: 'text/javascript', exec: fragment.pre_request_script.split('\n') },
      });
    }

    const parent = parentArrayOf(collection.item, baseItem);
    const cursorKey = fragment.operationId;
    const cursor = insertionCursor[cursorKey] !== undefined ? insertionCursor[cursorKey] : parent.indexOf(baseItem);
    parent.splice(cursor + 1, 0, clone);
    insertionCursor[cursorKey] = cursor + 1;

    fragmentItemsByOperationVariant[`${fragment.operationId}::${fragment.variant}`] = clone;
  }

  let attached = 0;
  let unmatched = 0;

  for (const doc of assertionDocs || []) {
    for (const entry of doc.entries || []) {
      const target =
        !entry.variant || entry.variant === 'base'
          ? baseItemsByOperationId[doc.operationId]
          : fragmentItemsByOperationVariant[`${doc.operationId}::${entry.variant}`];

      if (!target) {
        unmatched += 1;
        continue;
      }

      target.event = target.event || [];
      target.event.push({
        listen: 'test',
        script: {
          type: 'text/javascript',
          exec: [
            `// Requirement (${doc.capability}): ${entry.requirement}`,
            ...entry.script.split('\n'),
          ],
        },
      });
      attached += 1;
    }
  }

  let defaultChecks = 0;
  (function applyDefaultChecks(items) {
    items.forEach((item) => {
      if (item.item) {
        applyDefaultChecks(item.item);
        return;
      }
      if (!item.request) return;
      const hasTest = (item.event || []).some((e) => e.listen === 'test');
      if (!hasTest) {
        item.event = item.event || [];
        item.event.push(defaultCheckEvent());
        defaultChecks += 1;
      }
    });
  })(collection.item || []);

  return { collection, stats: { attached, unmatched, defaultChecks } };
}

module.exports = { mergeAssertions, buildOperationIdByPathMethod, operationIdForItem };
