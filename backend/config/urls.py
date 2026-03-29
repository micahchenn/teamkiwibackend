from django.contrib import admin
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    path("", core_views.api_root),
    path("admin/", admin.site.urls),
    path("api/health/", include("apps.core.urls")),
    path("api/operations/", include("apps.operations.urls")),
    path("api/", include("apps.payments.urls")),
    path("api/", include("apps.locks.urls")),
]
