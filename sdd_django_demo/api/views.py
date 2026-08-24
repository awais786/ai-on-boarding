import logging
from collections.abc import Mapping

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import render
from django.views import View
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import generics
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from .models import PasswordResetCode
from .serializers import (
    AccountSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SignupSerializer,
    validate_password_strength,
)

logger = logging.getLogger(__name__)

# Returned for every reset request, registered or not, so the response cannot be
# used to discover which addresses have accounts.
#
# These are templates, not response bodies: `Response(...)` keeps whatever dict it
# is handed, so passing a constant itself would leave `response.data` referring to
# that same module-level dict, and any renderer or test that mutates it would
# corrupt the constant for the life of the process. Two requirements depend on
# these staying byte-identical, so each response gets its own copy.
RESET_REQUESTED_BODY = {
    'detail': 'If that email address has an account, a reset link has been sent to it.'
}

# The single refusal for a code that is unrecognised, expired, used, or superseded.
# One constant, one branch: the four cases cannot drift apart into distinguishable
# responses.
RESET_REFUSED_BODY = {'detail': 'That reset link is not valid.'}

RESET_COMPLETED_BODY = {'detail': 'Your password has been changed.'}

# Returned when the per-address limit refuses a request. Fixed on purpose: DRF's
# default appends the wait remaining, rounded up ("Expected available in 3595
# seconds."), so two refusals a second apart differ by one. *Limit how often a
# reset may be requested for one address* requires its refusals to be identical in
# status and body, so the countdown is dropped rather than tolerated.
#
# Unlike the constants above, this one is never handed to `Response`: the exception
# handler builds the 429 body itself, and only `detail` is read from here. A second
# key added to this dict would not appear in the response.
RESET_LIMITED_BODY = {'detail': 'Too many reset requests for that address. Try again later.'}

# The page equivalent of RESET_REFUSED_BODY: one wording for all four causes, so
# following a link cannot reveal which of them applies.
PAGE_REFUSAL = 'That reset link is not valid.'


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok'})


class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer

    @extend_schema(
        request=SignupSerializer,
        responses={
            200: OpenApiResponse(response=AccountSerializer, description='Account created.'),
            400: OpenApiResponse(description='Validation failed; body names the offending field.'),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AccountSerializer(user).data, status=200)


def flatten_messages(detail):
    """Render a DRF ValidationError detail as one line of text.

    `detail` is a list when the error was raised with a string, but a dict when it
    was raised keyed by field - which this codebase already does elsewhere. Joining
    the list form directly would silently print the field names instead of the
    messages if the validator is ever changed to name its field.

    Recursive rather than a nested loop, because DRF's ErrorDetail subclasses str:
    iterating a dict value that happens to be one yields single characters, and the
    page then rendered the message spaced out letter by letter.
    """
    if isinstance(detail, dict):
        return ' '.join(flatten_messages(value) for value in detail.values())
    if isinstance(detail, (list, tuple)):
        return ' '.join(flatten_messages(item) for item in detail)
    return str(detail)


def build_reset_link(code):
    return f"{settings.RESET_LINK_BASE_URL.rstrip('/')}/reset-password/{code}/"


def send_reset_link(user, code):
    link = build_reset_link(code)
    send_mail(
        subject='Reset your password',
        message=(
            'Follow this link within 30 minutes to choose a new password:\n\n'
            f'{link}\n\n'
            'If you did not ask for this, you can ignore this message.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def try_deliver_reset_link(user):
    """Issue a code and mail it, letting nothing escape to the caller.

    Everything here runs only for a registered address. If any of it could raise,
    a registered address would answer 500 where an unregistered one answers 200,
    which is an enumeration oracle against "Answer every reset request
    identically" - so the guard wraps the whole branch rather than any single
    call inside it. Failures are logged, so a broken configuration stays visible.
    """
    try:
        # One transaction: issuing retires the account's previous code, and that
        # happens before the send can succeed. Without the rollback, a mail outage
        # destroyed the link already in someone's inbox and supplied no
        # replacement - "Leave earlier codes usable when delivery fails".
        with transaction.atomic():
            send_reset_link(user, PasswordResetCode.issue_for(user))
    # Deliberately broad: the guarantee is that no failure of any kind on this
    # branch reaches the caller, so there is no exception type worth re-raising.
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            'Password reset could not be delivered to user %s.', user.pk, exc_info=True
        )


def complete_reset(code, new_password):
    """Spend a reset code and set the new password. False if the code was not usable.

    The one place the completion sequence lives. Both the API endpoint and the page
    served at the delivered link call it, so "Retire a reset code once it is used"
    and "Invalidate existing authentication tokens on reset" cannot hold for one
    entry point and quietly fail for the other.

    One transaction, so a failure part-way cannot leave the password changed while
    the code stays usable or the old tokens stay valid. `claim` is the gate:
    whoever wins it is the only caller that proceeds.
    """
    with transaction.atomic():
        record = PasswordResetCode.resolve(code)
        if record is None or not record.claim():
            return False
        user = record.user
        user.set_password(new_password)
        user.save(update_fields=['password'])
        Token.objects.filter(user=user).delete()
    return True


class PasswordResetPageView(View):
    """The page a person reaches by following the link in their reset mail.

    Deliberately a plain Django view, not a DRF one: it answers a browser with
    HTML, is not part of the API surface, and is kept out of the OpenAPI schema.
    It shares `complete_reset` with the API endpoint rather than repeating it.
    """

    template_name = 'api/password_reset.html'

    def refuse(self, request):
        """The one refusal page, so all four unusable causes render identically."""
        return render(
            request,
            self.template_name,
            {'usable': False, 'refusal': PAGE_REFUSAL},
            status=400,
        )

    def get(self, request, code):
        if PasswordResetCode.resolve(code) is None:
            return self.refuse(request)
        return render(request, self.template_name, {'usable': True})

    def post(self, request, code):
        # The link's state is decided first. Validating the password first would
        # let a dead link render a live form whenever the password was also weak,
        # against "An unusable link says so and offers no form".
        if PasswordResetCode.resolve(code) is None:
            return self.refuse(request)
        password = request.POST.get('password', '')
        try:
            validate_password_strength(password)
        except ValidationError as invalid:
            return render(
                request,
                self.template_name,
                {'usable': True, 'problem': flatten_messages(invalid.detail)},
                status=400,
            )
        # Still checked: the code can be spent by a racing request between the
        # resolve above and the claim inside complete_reset.
        if not complete_reset(code, password):
            return self.refuse(request)
        return render(request, self.template_name, {'completed': True})


class PasswordResetAddressThrottle(SimpleRateThrottle):
    """Cap reset requests per submitted email address.

    Keyed on the address rather than the caller because the harm is done to an
    account: every request supersedes that account's previous code, so anyone
    could keep somebody else from finishing a reset by requesting one repeatedly
    on their behalf. A per-caller limit would miss that entirely, and a
    distributed caller would walk through it.

    The key is the address as submitted, whether or not an account exists for it,
    so being limited reveals nothing about who has an account.
    """

    scope = 'password-reset'

    def get_cache_key(self, request, view):
        # A throttle runs in `initial()`, before any serializer has looked at the
        # body, so what arrives here is whatever the parser produced: a JSON list,
        # string or number reaches this line just as readily as an object. Only a
        # mapping can be asked for a key, and the rest carry no address to key on -
        # the serializer refuses them a moment later, which is where a malformed
        # body is supposed to be answered.
        data = request.data if isinstance(request.data, Mapping) else {}
        email = data.get('email')
        if not isinstance(email, str) or not email.strip():
            return None  # nothing to key on; the serializer will reject it anyway
        return self.cache_format % {'scope': self.scope, 'ident': email.strip().lower()}


class PasswordResetRequestView(generics.GenericAPIView):
    serializer_class = PasswordResetRequestSerializer
    throttle_classes = [PasswordResetAddressThrottle]

    def throttled(self, request, wait):
        # `wait=None` is the point: it stops DRF appending the countdown to the
        # detail, and stops the exception handler deriving a Retry-After header
        # from it. Both vary between two refusals of the same address, and the
        # requirement behind this limit asks for refusals that do not.
        raise Throttled(detail=RESET_LIMITED_BODY['detail'], wait=None)

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={
            200: OpenApiResponse(
                description=(
                    'Returned whether or not the address has an account, so the response '
                    'cannot be used to tell the two apart.'
                )
            ),
            400: OpenApiResponse(description='The email field was missing or malformed.'),
            429: OpenApiResponse(
                description=(
                    'Too many reset requests for that address. Nothing was issued or sent. '
                    'The body is fixed and carries no wait time.'
                )
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # `iexact`, not `exact`: signup lowercases what it stores, but accounts made
        # through createsuperuser, the admin, or a shell do not, and those holders
        # are still entitled to a reset.
        # Ordered, because `iexact` can match more than one account when they were
        # created outside signup: an unordered `first()` would pick a different
        # holder run to run, and the uniform response hides which one was chosen.
        user = (
            User.objects.filter(email__iexact=serializer.validated_data['email'])
            .order_by('pk')
            .first()
        )
        if user is not None:
            try_deliver_reset_link(user)
        return Response(dict(RESET_REQUESTED_BODY), status=200)


class PasswordResetConfirmView(generics.GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={
            200: OpenApiResponse(description='Password changed.'),
            400: OpenApiResponse(
                description='The code was not usable, or the new password was rejected.'
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        completed = complete_reset(
            serializer.validated_data['code'], serializer.validated_data['password']
        )
        if not completed:
            return Response(dict(RESET_REFUSED_BODY), status=400)
        return Response(dict(RESET_COMPLETED_BODY), status=200)
