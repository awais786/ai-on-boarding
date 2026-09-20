from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class TenantTokenAuthentication(TokenAuthentication):
    """Token authentication that also requires a live organization.

    Runs on every request and caches nothing, so deactivating a user or an organization
    takes effect on the very next call - including for tokens issued earlier. Every
    refusal carries the same message so it cannot tell a caller which check failed.
    """

    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            token = model.objects.select_related('user__membership__organization').get(key=key)
        except model.DoesNotExist:
            raise AuthenticationFailed('Invalid token.') from None
        user = token.user
        # A reverse one-to-one with no row raises an AttributeError subclass, which
        # getattr's default absorbs: an account outside every organization is refused.
        membership = getattr(user, 'membership', None)
        if not user.is_active or membership is None or not membership.organization.is_active:
            raise AuthenticationFailed('Invalid token.')
        return (user, token)
