import json

from django.core.management.base import BaseCommand, CommandError

from apps.locks.seam import get_seam_service
from services.seam_service import SeamAPIError


class Command(BaseCommand):
    help = "Verify Seam API credentials (calls POST /workspaces/get)."

    def handle(self, *args, **options):
        try:
            seam = get_seam_service()
        except ValueError as e:
            raise CommandError(str(e)) from e

        try:
            payload = seam.verify_connection()
        except SeamAPIError as e:
            raise CommandError(
                f"{e} body={json.dumps(e.body, default=str) if e.body is not None else 'n/a'}"
            ) from e

        workspace = payload.get("workspace", {})
        self.stdout.write(self.style.SUCCESS("Seam connection OK"))
        self.stdout.write(
            json.dumps(
                {
                    "workspace_id": workspace.get("workspace_id"),
                    "name": workspace.get("name"),
                    "is_sandbox": workspace.get("is_sandbox"),
                },
                indent=2,
            )
        )
