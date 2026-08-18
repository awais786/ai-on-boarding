"""Conformance checks for signin.

What a successful signin *returns* varies enormously between specifications — a token, a
session cookie, a user object, an empty 204. None of that is asserted. What does not vary is
which requests succeed and which are refused.

One check reports rather than judges: whether signin by username still works after the
email-signin change request is a backwards-compatibility decision the learner makes and
records in their specification. The suite observes it; the lead judges it against their spec.
"""

import uuid

import pytest

from conftest import post, replacing, without


def signin_body(template, fields, identifier, password):
    body = replacing(template, fields["identifier"], identifier)
    body[fields["password"]] = password
    return body


def test_signin_endpoint_exists(signin_url):
    response = post(signin_url, {})
    assert response.status_code != 404, (
        f"No signin endpoint at {signin_url}. If their specification chose a different path, "
        f"re-run with --signin-path."
    )


def test_correct_credentials_succeed(signin_url, signin_template, registered, fields):
    body = signin_body(
        signin_template, fields,
        registered[fields["username"]], registered[fields["password"]],
    )
    response = post(signin_url, body)
    assert 200 <= response.status_code < 300, (
        f"A registered user could not sign in with correct credentials: "
        f"{response.status_code} {response.text[:300]}"
    )


def test_wrong_password_is_rejected(signin_url, signin_template, registered, fields):
    body = signin_body(
        signin_template, fields, registered[fields["username"]], "not-the-right-password"
    )
    response = post(signin_url, body)
    assert 400 <= response.status_code < 500, (
        f"Signin with a wrong password returned {response.status_code}, expected a 4xx rejection."
    )


def test_unknown_identifier_is_rejected(signin_url, signin_template, registered, fields):
    unknown = f"nobody{uuid.uuid4().hex[:12]}"
    body = signin_body(signin_template, fields, unknown, registered[fields["password"]])
    response = post(signin_url, body)
    assert 400 <= response.status_code < 500, (
        f"Signin as a user who never registered returned {response.status_code}, "
        f"expected a 4xx rejection."
    )


def test_missing_identifier_is_rejected(signin_url, signin_template, registered, fields):
    body = signin_body(
        signin_template, fields,
        registered[fields["username"]], registered[fields["password"]],
    )
    response = post(signin_url, without(body, fields["identifier"]))
    assert 400 <= response.status_code < 500, (
        f"Signin without an identifier returned {response.status_code}, expected a 4xx rejection."
    )


def test_missing_password_is_rejected(signin_url, signin_template, registered, fields):
    body = signin_body(
        signin_template, fields,
        registered[fields["username"]], registered[fields["password"]],
    )
    response = post(signin_url, without(body, fields["password"]))
    assert 400 <= response.status_code < 500, (
        f"Signin without a password returned {response.status_code}, expected a 4xx rejection."
    )


def test_signin_by_email_succeeds(signin_url, signin_template, registered, fields):
    """Required by the email-signin change request, so universal once it is folded in.

    A failure here means either the change request was never implemented, or it was
    implemented for a different field name — check --identifier-field.
    """
    body = signin_body(
        signin_template, fields,
        registered[fields["email"]], registered[fields["password"]],
    )
    response = post(signin_url, body)
    assert 200 <= response.status_code < 300, (
        f"Signing in with an email address returned {response.status_code}. The change request "
        f"asked for signin by username OR email."
    )


def test_password_never_appears_in_a_response(signin_url, signin_template, registered, fields):
    secret = registered[fields["password"]]

    success = post(signin_url, signin_body(
        signin_template, fields, registered[fields["username"]], secret))
    assert secret not in success.text, (
        "The submitted password appears in the successful signin response body."
    )

    failure = post(signin_url, signin_body(
        signin_template, fields, registered[fields["username"]], "wrong-" + secret))
    assert "wrong-" + secret not in failure.text, (
        "The submitted password appears in the failed-signin error response body."
    )


def test_username_signin_is_reported_not_judged(signin_url, signin_template, registered, fields):
    """Whether username signin survives the change request is the learner's decision.

    Keeping it is backwards compatible. Dropping it in favour of a general identifier is a
    breaking change some learners will defend. Both can be right — so this records what
    happened and leaves the verdict to the lead, who has their specification.

    Shown in the summary when pytest runs with -rs.
    """
    body = signin_body(
        signin_template, fields,
        registered[fields["username"]], registered[fields["password"]],
    )
    status = post(signin_url, body).status_code
    works = "still works" if 200 <= status < 300 else "no longer works"
    pytest.skip(
        f"INFO — signin by username {works} (HTTP {status}) after the email-signin change "
        f"request. Check this against what their specification says about backwards "
        f"compatibility."
    )
