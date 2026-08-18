"""Conformance checks for signup.

Every assertion holds for ANY defensible signup specification. Where learners legitimately
differ — exact status codes, password minimums, extra fields added by change requests — this
suite asserts only the class of response (2xx / 4xx) and derives request bodies from the
payload the facilitator supplied.

Do not tighten an assertion to an exact status code. You would be encoding one learner's
choices and would start failing correct work from another.
"""

from conftest import post, replacing, without


def test_signup_endpoint_exists(signup_url):
    response = post(signup_url, {})
    assert response.status_code != 404, (
        f"No signup endpoint at {signup_url}. If their specification chose a different path, "
        f"re-run with --signup-path."
    )


def test_valid_signup_succeeds(signup_url, fresh_signup):
    response = post(signup_url, fresh_signup)
    assert 200 <= response.status_code < 300, (
        f"A valid signup was rejected with {response.status_code}: {response.text[:400]}\n"
        f"If their spec requires a field this payload lacks — a change request may have added "
        f"one — pass a complete --signup-payload."
    )


def test_duplicate_email_is_rejected(signup_url, fresh_signup, fields):
    """No defensible specification allows the same address to register twice."""
    first = post(signup_url, fresh_signup)
    assert 200 <= first.status_code < 300, (
        f"Setup failed — first signup rejected: {first.status_code} {first.text[:200]}"
    )

    # Same email, different username, so only the email collides.
    duplicate = replacing(fresh_signup, fields["username"], fresh_signup[fields["username"]] + "x")
    second = post(signup_url, duplicate)

    assert 400 <= second.status_code < 500, (
        f"The same email registered twice. Second attempt returned {second.status_code}, "
        f"expected a 4xx rejection."
    )


def test_duplicate_username_is_rejected(signup_url, fresh_signup, fields):
    """Signup takes a username, so it has to mean something."""
    first = post(signup_url, fresh_signup)
    assert 200 <= first.status_code < 300, (
        f"Setup failed — first signup rejected: {first.status_code} {first.text[:200]}"
    )

    # Same username, different email, so only the username collides.
    duplicate = replacing(
        fresh_signup, fields["email"], "other-" + fresh_signup[fields["email"]]
    )
    second = post(signup_url, duplicate)

    assert 400 <= second.status_code < 500, (
        f"The same username registered twice. Second attempt returned {second.status_code}, "
        f"expected a 4xx rejection."
    )


def test_missing_username_is_rejected(signup_url, fresh_signup, fields):
    response = post(signup_url, without(fresh_signup, fields["username"]))
    assert 400 <= response.status_code < 500, (
        f"Signup without a username returned {response.status_code}, expected a 4xx rejection. "
        f"The seed requirement names a username; a signup that ignores it is not built to spec."
    )


def test_missing_email_is_rejected(signup_url, fresh_signup, fields):
    response = post(signup_url, without(fresh_signup, fields["email"]))
    assert 400 <= response.status_code < 500, (
        f"Signup without an email returned {response.status_code}, expected a 4xx rejection."
    )


def test_missing_password_is_rejected(signup_url, fresh_signup, fields):
    response = post(signup_url, without(fresh_signup, fields["password"]))
    assert 400 <= response.status_code < 500, (
        f"Signup without a password returned {response.status_code}, expected a 4xx rejection."
    )


def test_malformed_email_is_rejected(signup_url, fresh_signup, fields):
    response = post(signup_url, replacing(fresh_signup, fields["email"], "not-an-email"))
    assert 400 <= response.status_code < 500, (
        f"Signup with 'not-an-email' returned {response.status_code}, expected a 4xx rejection."
    )


def test_one_character_password_is_rejected(signup_url, fresh_signup, fields):
    """One character is below every plausible minimum, whatever they specified."""
    response = post(signup_url, replacing(fresh_signup, fields["password"], "a"))
    assert 400 <= response.status_code < 500, (
        f"A one-character password was accepted ({response.status_code}). That is below any "
        f"defensible minimum."
    )


def test_password_never_appears_in_a_response(signup_url, fresh_signup, fields):
    """Checked on the success path and the failure path.

    A serializer that echoes input back in an error body leaks just as effectively as one
    that returns it on success.
    """
    secret = fresh_signup[fields["password"]]

    success = post(signup_url, fresh_signup)
    assert secret not in success.text, (
        "The submitted password appears in the successful signup response body."
    )

    duplicate = post(signup_url, fresh_signup)
    assert secret not in duplicate.text, (
        "The submitted password appears in the duplicate-signup error response body."
    )
