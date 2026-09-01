'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { mergeAssertions } = require('../lib/merge');

function fakeSchema() {
  return {
    paths: {
      '/api/widget/': { post: { operationId: 'widget_create' } },
      '/api/gadget/': { get: { operationId: 'gadget_retrieve' } },
    },
  };
}

function fakeCollection() {
  return {
    item: [
      {
        id: 'base-widget',
        name: 'widget create',
        event: [],
        request: {
          method: 'POST',
          url: { path: ['api', 'widget', ''] },
          header: [{ key: 'Content-Type', value: 'application/xml' }],
          body: { mode: 'raw', raw: '{"placeholder": true}' },
        },
      },
      {
        id: 'base-gadget',
        name: 'gadget retrieve',
        event: [],
        request: {
          method: 'GET',
          url: { path: ['api', 'gadget', ''] },
          header: [],
        },
      },
    ],
  };
}

let idCounter = 0;
function idGenerator() {
  idCounter += 1;
  return `generated-id-${idCounter}`;
}

test('an operation with an assertions entry (no variant) gets that entry\'s script attached to the base request', () => {
  const assertionDocs = [
    {
      capability: 'widget',
      operationId: 'widget_create',
      entries: [
        { requirement: 'Widgets exist', script: "pm.test('exists', function () {});" },
      ],
    },
  ];

  const { collection, stats } = mergeAssertions(fakeSchema(), fakeCollection(), assertionDocs, [], idGenerator);

  const widgetItem = collection.item.find((i) => i.id === 'base-widget');
  const testEvents = widgetItem.event.filter((e) => e.listen === 'test');
  assert.equal(testEvents.length, 1);
  assert.match(testEvents[0].script.exec.join('\n'), /Requirement \(widget\): Widgets exist/);
  assert.match(testEvents[0].script.exec.join('\n'), /pm\.test\('exists'/);
  assert.equal(stats.attached, 1);
  assert.equal(stats.unmatched, 0);
});

test('a request with no assertions library entry gets only the default (no-server-error) check', () => {
  const { collection, stats } = mergeAssertions(fakeSchema(), fakeCollection(), [], [], idGenerator);

  for (const item of collection.item) {
    const testEvents = item.event.filter((e) => e.listen === 'test');
    assert.equal(testEvents.length, 1, `${item.name} should have exactly one (default) test event`);
    assert.match(testEvents[0].script.exec.join('\n'), /no server error/);
    assert.match(testEvents[0].script.exec.join('\n'), /to\.be\.below\(500\)/);
  }
  assert.equal(stats.defaultChecks, 2);
  assert.equal(stats.attached, 0);
});

test('a variant-scoped entry attaches to its cloned request fragment, not the base request', () => {
  const fragments = [
    {
      operationId: 'widget_create',
      variant: 'missing_name',
      name: 'widget create - missing name',
      body: { other_field: 'x' },
    },
  ];
  const assertionDocs = [
    {
      capability: 'widget',
      operationId: 'widget_create',
      entries: [
        { requirement: 'Reject a missing name', variant: 'missing_name', script: "pm.test('rejects', function () {});" },
      ],
    },
  ];

  const { collection, stats } = mergeAssertions(fakeSchema(), fakeCollection(), assertionDocs, fragments, idGenerator);

  const baseWidget = collection.item.find((i) => i.id === 'base-widget');
  const clone = collection.item.find((i) => i.name === 'widget create - missing name');

  assert.ok(clone, 'the fragment should have been inserted into the collection');
  assert.equal(clone.request.body.raw, JSON.stringify({ other_field: 'x' }, null, 2));
  assert.equal(
    clone.request.header.filter((h) => h.key.toLowerCase() === 'content-type').length,
    1,
    'the fragment should have exactly one Content-Type header, replacing any inherited from the base request'
  );
  assert.equal(clone.request.header.find((h) => h.key === 'Content-Type').value, 'application/json');

  // The base request got no entries targeting it, so it falls back to the default check.
  const baseTestEvents = baseWidget.event.filter((e) => e.listen === 'test');
  assert.equal(baseTestEvents.length, 1);
  assert.match(baseTestEvents[0].script.exec.join('\n'), /no server error/);

  const cloneTestEvents = clone.event.filter((e) => e.listen === 'test');
  assert.equal(cloneTestEvents.length, 1);
  assert.match(cloneTestEvents[0].script.exec.join('\n'), /Reject a missing name/);

  assert.equal(stats.attached, 1);
  assert.equal(stats.unmatched, 0);
  // Base widget (default) + gadget (default) = 2; the fragment clone got a real entry, not a default.
  assert.equal(stats.defaultChecks, 2);
});

test('an assertions entry whose operationId/variant matches no request is counted as unmatched, not silently dropped', () => {
  const assertionDocs = [
    {
      capability: 'widget',
      operationId: 'widget_create',
      entries: [
        { requirement: 'Orphaned requirement', variant: 'nonexistent_variant', script: "pm.test('x', function () {});" },
      ],
    },
  ];

  const { stats } = mergeAssertions(fakeSchema(), fakeCollection(), assertionDocs, [], idGenerator);

  assert.equal(stats.unmatched, 1);
  assert.equal(stats.attached, 0);
});
