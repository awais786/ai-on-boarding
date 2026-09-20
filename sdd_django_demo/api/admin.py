from django.contrib import admin

from .models import Organization, PasswordResetCode, SigninAttempt


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    # The digest is left out: an operator has no use for it, and the join code itself
    # is only ever shown by the management commands.
    exclude = ('join_code_digest',)
    readonly_fields = ('created_at', 'updated_at')
    list_display = ('slug', 'name', 'is_active')


admin.site.register(PasswordResetCode)
admin.site.register(SigninAttempt)
