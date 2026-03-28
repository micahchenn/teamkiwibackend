from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers


class LockCodeCreateSerializer(serializers.Serializer):
    """Create a 6-digit code. Omit time fields → starts now, expires 24h later (tomorrow same clock time)."""

    expires_at = serializers.DateTimeField(required=False)
    valid_for_hours = serializers.FloatField(required=False, min_value=1 / 60)
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    device_id = serializers.CharField(max_length=256, required=False, allow_blank=True, default="")
    lock_name = serializers.CharField(max_length=256, required=False, allow_blank=True, default="")
    lock_location = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")
    booking_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    customer_name = serializers.CharField(max_length=256, required=False, allow_blank=True, default="")
    customer_email = serializers.EmailField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    seam_access_code_id = serializers.CharField(max_length=256, required=False, allow_blank=True, default="")

    def validate(self, attrs: dict) -> dict:
        exp = attrs.get("expires_at")
        hours = attrs.get("valid_for_hours")
        if exp is not None and hours is not None:
            raise serializers.ValidationError("Provide only one of expires_at or valid_for_hours.")
        if hours is not None:
            start = attrs.get("starts_at") or timezone.now()
            attrs["expires_at"] = start + timedelta(hours=float(hours))
            if attrs.get("starts_at") is None:
                attrs["starts_at"] = start
            return attrs
        if exp is None:
            start = attrs.get("starts_at") or timezone.now()
            attrs["starts_at"] = start
            attrs["expires_at"] = start + timedelta(days=1)
            return attrs
        return attrs

    def clean_optional_str(self, key: str, attrs: dict) -> str | None:
        v = (attrs.get(key) or "").strip()
        return v or None


class LockCodeReadSerializer(serializers.Serializer):
    """Query by 6-digit code."""

    code = serializers.CharField(min_length=6, max_length=6)

    def validate_code(self, value: str) -> str:
        if not value.isdigit():
            raise serializers.ValidationError("Code must be 6 digits.")
        return value
