'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { mergeAssertions, DEFAULT_TEST } = require('../lib/merge');

function baseCollection(items) {
  return { info: { name: 'test' }, item: items };
}

function baseItem(operationId, overrides) {
  return Object.assign(
    {
      id: `generated-${operationId}`,
      name: operationId.replace(/_/g, ' '),
      operationId,
      request: {
        method: 'POST',
        url: { path: ['api', operationId, ''], host: ['{{baseUrl}}'], query: [], variable: [] },
        body: { mode: 'raw', raw: '{}', options: { raw: { language: 'json' } } },
      },
      response: [],
    },
    overrides
  );
}

test('a request with no assertions-library entry gets the default fallback test', () => {
  const { collection, orphaned } = mergeAssertions({
    generatedCollection: baseCollection([baseItem('health_retrieve')]),
    entries: [],
    fragments: [],
    operationOrder: [],
  });

  assert.equal(orphaned.length, 0);
  const [item] = collection.item;
  const testEvent = item.event.find((event) => event.listen === 'test');
  assert.deepEqual(testEvent.script.exec, DEFAULT_TEST);
});

test("an entry's test script attaches to the correct request by operationId", () => {
  const { collection, orphaned } = mergeAssertions({
    generatedCollection: baseCollection([baseItem('signup_create'), baseItem('signin_create')]),
    entries: [
      {
        operationId: 'signup_create',
        requirement: 'Accept a signup submission',
        test: ["pm.test('x', function () {});"],
      },
    ],
    fragments: [],
    operationOrder: [],
  });

  assert.equal(orphaned.length, 0);
  const signup = collection.item.find((item) => item.operationId === 'signup_create');
  const signin = collection.item.find((item) => item.operationId === 'signin_create');
  const signupTest = signup.event.find((event) => event.listen === 'test');
  const signinTest = signin.event.find((event) => event.listen === 'test');

  assert.deepEqual(signupTest.script.exec, ["pm.test('x', function () {});", '']);
  assert.deepEqual(signinTest.script.exec, DEFAULT_TEST);
});

test('a variant fragment is inserted as its own request with its own body', () => {
  const { collection, orphaned } = mergeAssertions({
    generatedCollection: baseCollection([baseItem('signup_create')]),
    entries: [
      {
        operationId: 'signup_create',
        variant: 'missing_email',
        requirement: 'Reject a missing email',
        test: ["pm.test('reject', function () {});"],
      },
    ],
    fragments: [
      {
        operationId: 'signup_create',
        variant: 'missing_email',
        name: 'signup - missing email',
        body: { password: 'x' },
      },
    ],
    operationOrder: [],
  });

  assert.equal(orphaned.length, 0);
  assert.equal(collection.item.length, 2);

  const [base, variant] = collection.item;
  assert.equal(base.operationId, 'signup_create');
  assert.equal(variant.name, 'signup - missing email');
  assert.deepEqual(JSON.parse(variant.request.body.raw), { password: 'x' });
  assert.notEqual(variant.id, base.id, 'variant item must not reuse the base item id');

  const variantTest = variant.event.find((event) => event.listen === 'test');
  assert.deepEqual(variantTest.script.exec, ["pm.test('reject', function () {});", '']);
});

test('an assertions-library entry with no matching operationId/variant is reported as orphaned', () => {
  const { orphaned } = mergeAssertions({
    generatedCollection: baseCollection([baseItem('signup_create')]),
    entries: [
      {
        operationId: 'signup_create',
        variant: 'a_variant_with_no_fragment',
        requirement: 'Does not exist',
        test: ["pm.test('x', function () {});"],
      },
      {
        operationId: 'an_operation_id_that_does_not_exist',
        requirement: 'Also does not exist',
        test: ["pm.test('x', function () {});"],
      },
    ],
    fragments: [],
    operationOrder: [],
  });

  assert.equal(orphaned.length, 2);
  assert.ok(orphaned.some((entry) => entry.variant === 'a_variant_with_no_fragment'));
  assert.ok(orphaned.some((entry) => entry.operationId === 'an_operation_id_that_does_not_exist'));
});

test('two fragments sharing the same operationId+variant are reported as orphaned, not silently downgraded', () => {
  const { collection, orphaned } = mergeAssertions({
    generatedCollection: baseCollection([baseItem('signup_create')]),
    entries: [
      {
        operationId: 'signup_create',
        variant: 'missing_email',
        requirement: 'Reject a missing email',
        test: ["pm.test('reject', function () {});"],
      },
    ],
    fragments: [
      { operationId: 'signup_create', variant: 'missing_email', name: 'first copy', body: { a: 1 } },
      { operationId: 'signup_create', variant: 'missing_email', name: 'accidental duplicate', body: { a: 2 } },
    ],
    operationOrder: [],
  });

  assert.equal(orphaned.length, 1);
  assert.equal(orphaned[0].type, 'duplicate_fragment');
  assert.equal(orphaned[0].name, 'accidental duplicate');
  // The first fragment still gets its assertion - only the second, colliding one is rejected.
  assert.equal(collection.item.length, 2);
  const variantTest = collection.item[1].event.find((event) => event.listen === 'test');
  assert.deepEqual(variantTest.script.exec, ["pm.test('reject', function () {});", '']);
});

test('an entry with no variant attaches to the base item even when a variant is literally named "base"', () => {
  const { collection, orphaned } = mergeAssertions({
    generatedCollection: baseCollection([baseItem('signup_create')]),
    entries: [
      { operationId: 'signup_create', requirement: 'Base requirement', test: ["pm.test('base', function () {});"] },
      {
        operationId: 'signup_create',
        variant: 'base',
        requirement: 'Variant literally named base',
        test: ["pm.test('variant-named-base', function () {});"],
      },
    ],
    fragments: [{ operationId: 'signup_create', variant: 'base', name: 'signup - variant literally named base', body: {} }],
    operationOrder: [],
  });

  assert.equal(orphaned.length, 0, JSON.stringify(orphaned));
  const [base, variant] = collection.item;
  const baseTest = base.event.find((event) => event.listen === 'test');
  const variantTest = variant.event.find((event) => event.listen === 'test');
  assert.deepEqual(baseTest.script.exec, ["pm.test('base', function () {});", '']);
  assert.deepEqual(variantTest.script.exec, ["pm.test('variant-named-base', function () {});", '']);
});

test('two base items sharing the same operationId are reported as orphaned, not silently collapsed', () => {
  const { collection, orphaned } = mergeAssertions({
    generatedCollection: baseCollection([baseItem('signup_create'), baseItem('signup_create')]),
    entries: [],
    fragments: [],
    operationOrder: [],
  });

  assert.equal(collection.item.length, 1, 'only one of the two duplicates should survive into the run');
  assert.equal(orphaned.length, 1);
  assert.equal(orphaned[0].type, 'duplicate_base_operation_id');
  assert.equal(orphaned[0].operationId, 'signup_create');
});

test('operationOrder controls the final request order; unlisted operations are appended', () => {
  const { collection } = mergeAssertions({
    generatedCollection: baseCollection([baseItem('b_op'), baseItem('a_op'), baseItem('c_op')]),
    entries: [],
    fragments: [],
    operationOrder: ['a_op', 'b_op'],
  });

  assert.deepEqual(
    collection.item.map((item) => item.operationId),
    ['a_op', 'b_op', 'c_op']
  );
});

test('a duplicate id in operationOrder is used only at its first occurrence, never duplicating output', () => {
  const { collection } = mergeAssertions({
    generatedCollection: baseCollection([baseItem('a_op'), baseItem('b_op')]),
    entries: [],
    fragments: [],
    operationOrder: ['a_op', 'b_op', 'a_op'],
  });

  assert.deepEqual(
    collection.item.map((item) => item.operationId),
    ['a_op', 'b_op']
  );
});
