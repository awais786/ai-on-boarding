#!/usr/bin/env python3
"""Evaluates the api-behavior-verification pipeline's output against the OpenSpec specs.

Reads the merged Postman collection (what was checked and why - see merge_assertions.js), the
Newman result report (what actually happened when it ran against a live instance), the OpenSpec
capability specs (the source of truth for behaviour), and the documented list of deliberately
out-of-scope requirements (postman/assertions/out_of_scope.json) - then asks a Claude model to
judge: did anything the live API did violate a requirement, and is the assertions library's
coverage of the specs good enough. See README.md for the full pipeline and the responsibility
split between OpenAPI, the specs, Postman, Claude, and CI.

Exit code is the pass/fail signal GitHub Actions acts on: 0 if the verdict is `ready: true` and
no finding is blocking, 1 otherwise (including any failure to obtain or parse a verdict at all -
this step must never pass silently just because Claude couldn't be reached).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

POSTMAN_DIR = Path(__file__).resolve().parent
REPO_ROOT = POSTMAN_DIR.parent
DEFAULT_MODEL = os.environ.get('CLAUDE_REVIEW_MODEL', 'claude-sonnet-5')

SYSTEM_PROMPT = """\
You are reviewing the output of an automated API-behavior-verification pipeline for a Django \
REST project built through spec-driven development (OpenSpec). Apply the same blocking/non-\
blocking contract this project's own /code-review process uses (see openspec/config.yaml):

- A finding blocks only if it cites a specific OpenSpec requirement name, a specific failing \
assertion, or a documented convention. Anything else is a nit - report it, but do not mark it \
blocking.
- Check, at minimum: (1) requirements in the specs with no corresponding assertion in the merged \
collection and no matching entry in the documented out-of-scope list, (2) assertions whose \
script checks something other than what their cited requirement actually states, (3) endpoints \
whose spec defines behaviour beyond a successful response but whose checks assert only a status \
code, and (4) any Newman result showing a checked requirement's assertion failed against the \
live API.
- A requirement listed in the out-of-scope document is NOT a coverage gap - it is a deliberate, \
documented exclusion. Do not flag it as missing coverage; you may still note it as a nit if its \
stated rationale looks wrong.
- A failing assertion whose test name contains "KNOWN DRIFT" already documents a known, \
previously-discovered spec/implementation mismatch (see design.md's "Risks / Trade-offs"). Still \
report it as blocking - the requirement is still being violated, and "Fail the run on an \
assertion failure" applies unconditionally, with no carve-out for drift that predates a given \
change - but do not treat discovering it as a new insight distinct from what the test name \
already says.

Reply with ONLY a single JSON object, no prose before or after it, matching exactly this shape:
{"findings": [{"requirement": "<name or endpoint>", "detail": "<what's wrong>", "blocking": \
true|false}], "ready": true|false}
`ready` is true only if there are zero blocking findings. An empty pipeline run (nothing checked \
at all) is not evidence of correctness - treat total absence of coverage for a capability as a \
blocking finding citing that capability.
"""


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def collect_spec_texts() -> str:
    specs_dir = REPO_ROOT / 'openspec' / 'specs'
    parts = []
    for spec_path in sorted(specs_dir.glob('*/spec.md')):
        parts.append(f'--- {spec_path.relative_to(REPO_ROOT)} ---\n{read_text(spec_path)}')
    return '\n\n'.join(parts)


def collect_out_of_scope() -> str:
    path = POSTMAN_DIR / 'assertions' / 'out_of_scope.json'
    if not path.exists():
        return '[]'
    return read_text(path)


def summarise_collection(collection: dict) -> list[dict]:
    """Extracts, per request, its name and the requirement each attached test cites.

    Only what the review needs - not the full collection (headers, auth, IDs) - to keep the
    prompt focused and small.
    """
    summary = []

    def walk(items):
        for item in items:
            if 'item' in item:
                walk(item['item'])
                continue
            if 'request' not in item:
                continue
            tests = []
            for event in item.get('event', []):
                if event.get('listen') != 'test':
                    continue
                exec_lines = event.get('script', {}).get('exec', [])
                text = '\n'.join(exec_lines)
                match = re.search(r'// Requirement \(([^)]+)\): (.+)', text)
                if match:
                    tests.append({'capability': match.group(1), 'requirement': match.group(2)})
                else:
                    tests.append({'capability': None, 'requirement': '(default check, no library entry)'})
            summary.append({
                'name': item['name'],
                'method': item['request']['method'],
                'tests': tests,
            })

    walk(collection.get('item', []))
    return summary


def summarise_results(result: dict) -> list[dict]:
    """Extracts, per executed request, each assertion's name and pass/fail."""
    summary = []
    executions = result.get('run', {}).get('executions', [])
    for execution in executions:
        item_name = execution.get('item', {}).get('name')
        assertions = []
        for assertion in execution.get('assertions', []) or []:
            assertions.append({
                'name': assertion.get('assertion'),
                'passed': 'error' not in assertion,
                'error': (assertion.get('error') or {}).get('message'),
            })
        response = execution.get('response') or {}
        summary.append({
            'name': item_name,
            'status': response.get('code'),
            'assertions': assertions,
        })
    return summary


def build_user_prompt(collection: dict, result: dict) -> str:
    return f"""\
## OpenSpec capability specs (source of truth for behaviour)

{collect_spec_texts()}

## Deliberately out-of-scope requirements (postman/assertions/out_of_scope.json)

{collect_out_of_scope()}

## What the merged Postman collection checks (request name -> requirement(s) its attached test(s) cite)

{json.dumps(summarise_collection(collection), indent=2)}

## What happened when it ran against a live instance (postman/result.json, summarised)

{json.dumps(summarise_results(result), indent=2)}
"""


def call_claude(system_prompt: str, user_prompt: str, model: str) -> str:
    import anthropic  # imported lazily so --dry-run doesn't need the package installed

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{'role': 'user', 'content': user_prompt}],
    )
    return ''.join(block.text for block in response.content if block.type == 'text')


def parse_verdict(raw_text: str) -> dict:
    text = raw_text.strip()
    fence_match = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    verdict = json.loads(text)
    if 'findings' not in verdict or 'ready' not in verdict:
        raise ValueError(f'Verdict JSON missing required keys: {verdict!r}')
    return verdict


def print_verdict(verdict: dict) -> None:
    findings = verdict.get('findings', [])
    if not findings:
        print('No findings.')
    for finding in findings:
        tag = 'BLOCKING' if finding.get('blocking') else 'nit'
        print(f"[{tag}] {finding.get('requirement')}: {finding.get('detail')}")
    print(f"ready: {verdict.get('ready')}")


def exit_code_for(verdict: dict) -> int:
    if not verdict.get('ready', False):
        return 1
    if any(f.get('blocking') for f in verdict.get('findings', [])):
        return 1
    return 0


def main(argv: list[str]) -> int:
    dry_run = '--dry-run' in argv

    collection_path = POSTMAN_DIR / 'collection.merged.json'
    result_path = POSTMAN_DIR / 'result.json'
    for path in (collection_path, result_path):
        if not path.exists():
            print(f'{path} not found. Run "npm run merge" and "npm run newman" first.', file=sys.stderr)
            return 1

    collection = json.loads(read_text(collection_path))
    result = json.loads(read_text(result_path))
    user_prompt = build_user_prompt(collection, result)

    if dry_run:
        print(f'--dry-run: would send a {len(user_prompt)}-character prompt to {DEFAULT_MODEL}.')
        print('First 500 characters:')
        print(user_prompt[:500])
        return 0

    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('ANTHROPIC_API_KEY is not set - cannot run the Claude evaluation.', file=sys.stderr)
        return 1

    try:
        raw_text = call_claude(SYSTEM_PROMPT, user_prompt, DEFAULT_MODEL)
        verdict = parse_verdict(raw_text)
    except Exception as exc:  # noqa: BLE001 - any failure here must fail the run, not pass it
        print(f'Claude evaluation failed: {exc}', file=sys.stderr)
        return 1

    print_verdict(verdict)
    return exit_code_for(verdict)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
