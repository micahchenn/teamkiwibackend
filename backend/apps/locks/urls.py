from django.urls import path

from apps.locks import views

urlpatterns = [
    path("lock-codes/", views.LockCodeCreateView.as_view(), name="lock-code-create"),
    path("lock-codes/lookup/", views.LockCodeLookupView.as_view(), name="lock-code-lookup"),
    path("lock-codes/<str:pk>/", views.LockCodeDetailView.as_view(), name="lock-code-detail"),
]
