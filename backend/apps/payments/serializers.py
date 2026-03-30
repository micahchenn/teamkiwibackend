from __future__ import annotations

from typing import Any

from rest_framework import serializers


class BookingPayloadSerializer(serializers.Serializer):
    product = serializers.CharField(required=False, allow_blank=True, default="")
    visitStart = serializers.DateField(required=False, allow_null=True)
    visitEnd = serializers.DateField(required=False, allow_null=True)
    dayCount = serializers.IntegerField(required=False, min_value=1)
    adults = serializers.IntegerField(required=False, min_value=0)
    children = serializers.IntegerField(required=False, min_value=0)
    people = serializers.IntegerField(required=False, min_value=1)
    dayPassCents = serializers.IntegerField(required=False, min_value=0)
    totalCents = serializers.IntegerField(required=True, min_value=1)
    # Extra recipients for confirmation + door code (deduped with customerEmail). Optional.
    guestEmails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        allow_empty=True,
        default=list,
    )


class SquarePaymentRequestSerializer(serializers.Serializer):
    sourceId = serializers.CharField(required=True)
    amountCents = serializers.IntegerField(required=True, min_value=1)
    currency = serializers.CharField(default="USD", max_length=3)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    referenceId = serializers.UUIDField(required=True)
    customerName = serializers.CharField(required=False, allow_blank=True, default="")
    customerEmail = serializers.EmailField(required=False, allow_blank=True, default="")
    customerPhone = serializers.CharField(required=False, allow_blank=True, default="", max_length=32)
    # Extra confirmation recipients (same as booking.guestEmails). Many clients send these at top level.
    guestEmails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        allow_empty=True,
        default=list,
    )
    booking = BookingPayloadSerializer(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        booking = attrs.get("booking")
        amount = attrs["amountCents"]
        if booking is not None:
            tc = booking.get("totalCents")
            if tc is not None and int(tc) != int(amount):
                raise serializers.ValidationError("amountCents does not match booking.totalCents.")
        return attrs
