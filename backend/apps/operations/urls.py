from django.urls import path

from apps.operations import views

urlpatterns = [
    path("summary/", views.OperationsSummaryView.as_view(), name="operations-summary"),
]
