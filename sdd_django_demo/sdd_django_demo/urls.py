"""
URL configuration for sdd_django_demo project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from api.views import PasswordResetPageView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    # Not under api/: this is the human-facing address the reset mail carries, and
    # it must match RESET_LINK_BASE_URL + the path build_reset_link composes.
    path(
        'reset-password/<str:code>/',
        PasswordResetPageView.as_view(),
        name='password-reset-page',
    ),
]
