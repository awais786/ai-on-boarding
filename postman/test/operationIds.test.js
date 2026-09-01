'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { schemaOperationIds, toSchemaPath, stampOperationIds } = require('../lib/operationIds');

test('schemaOperationIds indexes every operation by METHOD + path', () => {
  const schema = {
    paths: {
      '/api/signup/': { post: { operationId: 'signup_create' } },
      '/api/health/': { get: { operationId: 'health_retrieve' } },
    },
  };

  assert.deepEqual(schemaOperationIds(schema), {
    'POST /api/signup/': 'signup_create',
    'GET /api/health/': 'health_retrieve',
  });
});

test('toSchemaPath reassembles Postman path segments into an OpenAPI-style path', () => {
  assert.equal(toSchemaPath(['api', 'signup', '']), '/api/signup/');
  assert.equal(toSchemaPath(['api', 'password-reset', 'confirm', '']), '/api/password-reset/confirm/');
});

test('toSchemaPath converts a Postman path variable (:name) to OpenAPI style ({name})', () => {
  assert.equal(toSchemaPath(['api', 'accounts', ':id', '']), '/api/accounts/{id}/');
});

test('stampOperationIds sets operationId on a matching leaf item, including inside folders', () => {
  const items = [
    {
      item: [
        {
          name: 'signup create',
          request: { method: 'POST', url: { path: ['api', 'signup', ''] } },
        },
      ],
    },
  ];

  const unmatched = stampOperationIds(items, { 'POST /api/signup/': 'signup_create' });

  assert.deepEqual(unmatched, []);
  assert.equal(items[0].item[0].operationId, 'signup_create');
});

test('stampOperationIds reports an item with no matching schema operation as unmatched', () => {
  const items = [
    {
      name: 'mystery endpoint',
      request: { method: 'DELETE', url: { path: ['api', 'mystery', ''] } },
    },
  ];

  const unmatched = stampOperationIds(items, { 'POST /api/signup/': 'signup_create' });

  assert.equal(unmatched.length, 1);
  assert.match(unmatched[0], /DELETE \/api\/mystery\//);
});
