"""Unit tests for review_with_claude.py's verdict parsing and pass/fail decision.

Mocks the Anthropic API call entirely (call_claude) so these run offline, with no network access
and no API key - see postman/README.md for how to exercise the real API call locally.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import review_with_claude as rwc  # noqa: E402


MINIMAL_COLLECTION = {
    'item': [
        {
            'name': 'widget create',
            'request': {'method': 'POST'},
            'event': [
                {
                    'listen': 'test',
                    'script': {
                        'exec': [
                            '// Requirement (widget): Widgets exist',
                            "pm.test('exists', function () {});",
                        ]
                    },
                }
            ],
        }
    ]
}

MINIMAL_RESULT = {
    'run': {
        'executions': [
            {
                'item': {'name': 'widget create'},
                'response': {'code': 200},
                'assertions': [{'assertion': 'exists'}],
            }
        ]
    }
}


class FixtureDirMixin:
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        (tmp_path / 'collection.merged.json').write_text(json.dumps(MINIMAL_COLLECTION))
        (tmp_path / 'result.json').write_text(json.dumps(MINIMAL_RESULT))
        self._patcher = patch.object(rwc, 'POSTMAN_DIR', tmp_path)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(self._tmpdir.cleanup)


class TestParseVerdict(unittest.TestCase):
    def test_parses_plain_json(self):
        verdict = rwc.parse_verdict('{"findings": [], "ready": true}')
        self.assertEqual(verdict, {'findings': [], 'ready': True})

    def test_parses_fenced_json(self):
        verdict = rwc.parse_verdict('```json\n{"findings": [], "ready": true}\n```')
        self.assertEqual(verdict, {'findings': [], 'ready': True})

    def test_raises_on_missing_keys(self):
        with self.assertRaises(ValueError):
            rwc.parse_verdict('{"findings": []}')


class TestExitCodeFor(unittest.TestCase):
    def test_ready_true_no_findings_is_zero(self):
        self.assertEqual(rwc.exit_code_for({'findings': [], 'ready': True}), 0)

    def test_ready_false_is_nonzero(self):
        self.assertEqual(rwc.exit_code_for({'findings': [], 'ready': False}), 1)

    def test_blocking_finding_is_nonzero_even_if_ready_true(self):
        verdict = {
            'findings': [{'requirement': 'X', 'detail': 'y', 'blocking': True}],
            'ready': True,
        }
        self.assertEqual(rwc.exit_code_for(verdict), 1)

    def test_nonblocking_finding_with_ready_true_is_zero(self):
        verdict = {
            'findings': [{'requirement': 'X', 'detail': 'nit', 'blocking': False}],
            'ready': True,
        }
        self.assertEqual(rwc.exit_code_for(verdict), 0)


class TestMainExitCode(FixtureDirMixin, unittest.TestCase):
    """Exercises main() end to end with call_claude mocked - the exact scenarios task 9.3 asks
    for: a ready:false verdict, a verdict with a blocking finding, and an all-clear verdict."""

    def test_ready_false_verdict_produces_nonzero_exit(self):
        with patch.object(rwc, 'call_claude', return_value='{"findings": [], "ready": false}'):
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
                self.assertNotEqual(rwc.main([]), 0)

    def test_blocking_finding_produces_nonzero_exit(self):
        response = json.dumps({
            'findings': [{'requirement': 'Widgets exist', 'detail': 'missing coverage', 'blocking': True}],
            'ready': False,
        })
        with patch.object(rwc, 'call_claude', return_value=response):
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
                self.assertNotEqual(rwc.main([]), 0)

    def test_all_clear_verdict_produces_zero_exit(self):
        with patch.object(rwc, 'call_claude', return_value='{"findings": [], "ready": true}'):
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
                self.assertEqual(rwc.main([]), 0)

    def test_missing_api_key_fails_closed(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertNotEqual(rwc.main([]), 0)

    def test_unparseable_response_fails_closed(self):
        with patch.object(rwc, 'call_claude', return_value='not json at all'):
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
                self.assertNotEqual(rwc.main([]), 0)


if __name__ == '__main__':
    unittest.main()
