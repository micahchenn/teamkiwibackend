from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import ConfigurationError, PyMongoError

from services.mongo_client import get_mongo_client


class Command(BaseCommand):
    help = "Verify MongoDB (ping + default database name). Uses MONGO_URI or split Atlas env vars."

    def handle(self, *args, **options):
        try:
            client = get_mongo_client(serverSelectionTimeoutMS=10000)
            client.admin.command("ping")
        except ValueError as e:
            raise CommandError(str(e)) from e
        except PyMongoError as e:
            raise CommandError(f"MongoDB connection failed: {e}") from e

        try:
            default_db = client.get_default_database()
            db_name = default_db.name if default_db is not None else settings.MONGO_DB_NAME
            source = "URI path"
        except ConfigurationError:
            # Atlas sample URI often ends with /?appName=... with no database segment.
            db_name = settings.MONGO_DB_NAME
            source = f"MONGO_DB_NAME (URI has no /dbname/ — set MONGO_DB_NAME or use ...net/{db_name}?...)"

        self.stdout.write(self.style.SUCCESS("MongoDB connection OK (ping)"))
        self.stdout.write(f"App database: {db_name} ({source})")
