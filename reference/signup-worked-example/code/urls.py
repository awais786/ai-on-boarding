from django.urls import path

from .views import health, signup

urlpatterns = [
    path("health/", health, name="health"),
    path("auth/signup/", signup, name="signup"),
]
