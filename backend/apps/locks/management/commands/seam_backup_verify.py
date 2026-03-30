"""
Read-only check: POST /access_codes/get for each SEAM_BACKUP_CODE_*_ID.
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.locks.seam import get_seam_service
from services.seam_service import SeamAPIError


def _mask_code(code: object) -> str:
    s = "".join(c for c in str(code or "") if c.isdigit())
    if len(s) == 6:
        return f"**{s[2:4]}**"  # middle two digits only
    if len(s) >= 2:
        return f"…{s[-2:]}"
    return "(no 6-digit code)"


class Command(BaseCommand):
    help = "Verify SEAM_BACKUP_CODE_*_ID values via Seam access_codes/get (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--show-code",
            action="store_true",
            help="Print full PIN (avoid in shared logs).",
        )

    def handle(self, *args, **options):
        show_full = options["show_code"]
        ids = list(getattr(settings, "SEAM_BACKUP_CODE_IDS", None) or [])
        if not ids:
            self.stdout.write(self.style.WARNING("No SEAM_BACKUP_CODE_*_ID configured."))
            return

        try:
            seam = get_seam_service()
        except ValueError as e:
            raise CommandError(str(e)) from e

        ok = 0
        for aid in ids:
            try:
                ac = seam.get_access_code(aid)
            except SeamAPIError as e:
                self.stdout.write(
                    self.style.ERROR(f"{aid}\n  FAIL: {e}\n  body={json.dumps(e.body, default=str)[:500]}")
                )
                continue

            errs = ac.get("errors")
            code = ac.get("code")
            name = (ac.get("name") or "").strip()
            status = (ac.get("status") or "").strip()
            if isinstance(errs, list) and len(errs) > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"{aid}\n  name={name!r} status={status!r}\n  errors={errs!r}"
                    )
                )
                continue

            pin_display = str(code) if show_full else _mask_code(code)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{aid}\n  OK  name={name!r} status={status!r}  code={pin_display}\n"
                )
            )
            ok += 1

        self.stdout.write(f"\nSummary: {ok}/{len(ids)} backup access codes usable (no errors on object).")
