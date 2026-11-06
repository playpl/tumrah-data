"""Read-only view of the live Tumrah database.

Only reads live here. Writes go through the importers in the tumrah repo
(backend/src/scripts/), never through this file. The URI is read from the
backend .env at run time and never printed.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BLOCKED_STAGES = {"$out", "$merge"}
MAX_ROWS = 500


def _uri(env_path):
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "MONGODB_URI":
            return value.strip().strip('"').strip("'")
    raise SystemExit("MONGODB_URI not found in " + str(env_path))


def _pin_dns():
    # Atlas SRV lookups fail on this PC's resolver (.claude/rules/backend.md).
    import dns.resolver
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = ["1.1.1.1"]
    dns.resolver.default_resolver = resolver


class Reader:
    """find, count and aggregate only; results capped at MAX_ROWS."""

    def __init__(self, database):
        self._db = database

    @classmethod
    def live(cls):
        from pymongo import MongoClient
        _pin_dns()
        client = MongoClient(_uri(CONFIG["backend_env"]), serverSelectionTimeoutMS=15000,
                             readPreference="secondaryPreferred", appname="tumrah-data")
        return cls(client.get_default_database(default=CONFIG["db_name"]))

    def find(self, collection, flt=None, projection=None, limit=50, sort=None, skip=0):
        cursor = self._db[collection].find(flt or {}, projection)
        if sort:
            cursor = cursor.sort(sort)
        return list(cursor.skip(skip).limit(min(limit, MAX_ROWS)))

    def count(self, collection, flt=None):
        return self._db[collection].count_documents(flt or {})

    def aggregate(self, collection, pipeline):
        for stage in pipeline:
            if BLOCKED_STAGES & set(stage):
                raise ValueError("pipeline stage writes: " + ",".join(BLOCKED_STAGES & set(stage)))
        return list(self._db[collection].aggregate(pipeline + [{"$limit": MAX_ROWS}]))
