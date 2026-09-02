from django.contrib import admin

from .models import PasswordResetCode, SigninAttempt

admin.site.register(PasswordResetCode)
admin.site.register(SigninAttempt)
