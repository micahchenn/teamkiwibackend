from django.urls import path

from apps.payments import views

urlpatterns = [
    path("square/config/", views.SquareConfigView.as_view(), name="square-config"),
    path("square/config", views.SquareConfigView.as_view(), name="square-config-noslash"),
    path("square/payments/", views.SquarePaymentView.as_view(), name="square-payments"),
    path("square/payments", views.SquarePaymentView.as_view(), name="square-payments-noslash"),
]
