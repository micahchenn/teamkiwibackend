from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from services.email_service import send_template_test_email


class Command(BaseCommand):
    help = (
        "Send a test email: uses SendGrid Dynamic Template when "
        "SENDGRID_DEFAULT_TEMPLATE_ID is set, otherwise plain SMTP."
    )

    def add_arguments(self, parser):
        parser.add_argument("to", type=str, help="Recipient email address")

    def handle(self, *args, **options):
        to_addr = (options["to"] or "").strip()
        api_key = (getattr(settings, "SENDGRID_API_KEY", None) or "").strip()
        if not api_key:
            self.stderr.write("SENDGRID_API_KEY is not set. Add it to .env and restart.")
            return

        template_id = (getattr(settings, "SENDGRID_DEFAULT_TEMPLATE_ID", None) or "").strip()
        if template_id:
            try:
                send_template_test_email(to_addr)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                raise
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sent dynamic template {template_id} to {to_addr} (sample booking data)."
                )
            )
            return

        if not getattr(settings, "EMAIL_HOST_PASSWORD", None):
            self.stderr.write(
                "Set SENDGRID_DEFAULT_TEMPLATE_ID for template tests, or EMAIL_PASS for SMTP-only."
            )
            return
        send_mail(
            subject="Team Kiwi — SendGrid test",
            message="If you received this, Django SMTP + SendGrid is working.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_addr],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f"Sent plain SMTP test email to {to_addr}"))
