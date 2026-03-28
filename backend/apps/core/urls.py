from django.urls import path

from apps.core import views

urlpatterns = [
    path("", views.health_live, name="health-live"),
    path("ready/", views.health_ready, name="health-ready"),
]
