"""The site's private storage (Cloudflare R2, S3 API) from Python: the cloud runner uploads and keeps its state here.

Credentials: the environment (S3_BUCKET, S3_ENDPOINT, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_REGION) as on the
GitHub runner; on the PC, the same names are read from the backend's .env (config.json `backend_env`) when the
environment lacks them. Never printed.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPS = "ops/tumrah-data/"          # everything this repo keeps in the bucket that is not a student file
KEYS = ("S3_BUCKET", "S3_ENDPOINT", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_REGION")
_client = None


def env():
    out = {k: os.environ[k] for k in KEYS if os.environ.get(k)}
    if len(out) < 4:
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        f = Path(cfg.get("backend_env") or "")
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                k, sep, v = line.partition("=")
                k = k.strip()
                if sep and k in KEYS and k not in out:
                    out[k] = v.strip().strip('"').strip("'")
    missing = [k for k in KEYS[:4] if not out.get(k)]
    if missing:
        raise RuntimeError(f"storage credentials missing: {', '.join(missing)}")
    return out


def client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config
        e = env()
        _client = (boto3.client("s3", endpoint_url=e["S3_ENDPOINT"], region_name=e.get("S3_REGION") or "auto",
                                aws_access_key_id=e["S3_ACCESS_KEY_ID"], aws_secret_access_key=e["S3_SECRET_ACCESS_KEY"],
                                config=Config(retries={"max_attempts": 6, "mode": "standard"})), e["S3_BUCKET"])
    return _client


def get_bytes(key):
    c, bucket = client()
    try:
        return c.get_object(Bucket=bucket, Key=key)["Body"].read()
    except c.exceptions.NoSuchKey:
        return None


def put_bytes(key, data, content_type="application/octet-stream"):
    c, bucket = client()
    c.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def size(key):
    c, bucket = client()
    try:
        return c.head_object(Bucket=bucket, Key=key)["ContentLength"]
    except Exception:  # noqa: BLE001 - absent (404) or unreadable: treat as absent
        return None


def get_file(key, path):
    """Downloads key into path (atomically). True when the key exists."""
    c, bucket = client()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    try:
        c.download_file(bucket, key, str(tmp))
    except Exception:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    return True


def send(file, key):
    """Same shape as spine.records.machine.send: (ok, message). Skips a key that already holds a file of this size."""
    c, bucket = client()
    n = Path(file).stat().st_size
    if size(key) == n:
        return True, "already there"
    try:
        c.upload_file(str(file), bucket, key, ExtraArgs={"ContentType": "audio/mp4"})
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:120]}"
    return (size(key) == n), "uploaded"
