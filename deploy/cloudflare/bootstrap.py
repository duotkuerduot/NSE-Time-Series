"""Create the three R2 buckets and their policies (ENGINEERING.md 29.3; review FE-1).

Run once with an R2 API token that can administer buckets (Admin Read & Write). The daily
pipeline uses a narrower token afterwards (docs/runbooks/infra-bootstrap.md).

    export R2_ACCOUNT_ID=... R2_ADMIN_KEY_ID=... R2_ADMIN_SECRET=...
    uv run python deploy/cloudflare/bootstrap.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3

BUCKETS = {
    "nsefc-data": "private: raw files, database versions, snapshots, artifacts, logs",
    "nsefc-public": "public: published API releases only",
    "nsefc-scratch": "dry-run output, deleted after 14 days",
}

# Public, read-only data: CORS restricts nothing worth protecting, and a narrow origin list
# breaks per-PR preview deployments (review FE-1).
PUBLIC_CORS = {
    "CORSRules": [
        {
            "AllowedOrigins": ["*"],
            "AllowedMethods": ["GET", "HEAD"],
            "AllowedHeaders": ["*"],
            "MaxAgeSeconds": 3600,
        }
    ]
}

SCRATCH_LIFECYCLE = {
    "Rules": [
        {
            "ID": "expire-dry-runs",
            "Status": "Enabled",
            "Filter": {"Prefix": ""},
            "Expiration": {"Days": 14},
        }
    ]
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        account = os.environ["R2_ACCOUNT_ID"]
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ADMIN_KEY_ID"],
            aws_secret_access_key=os.environ["R2_ADMIN_SECRET"],
            region_name="auto",
        )
    except KeyError as missing:
        print(f"set {missing} first", file=sys.stderr)
        return 2

    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    for name, purpose in BUCKETS.items():
        action = "exists" if name in existing else "create"
        print(f"{name:<14} {action:<7} {purpose}")
        if action == "create" and not args.dry_run:
            client.create_bucket(Bucket=name)
    print("nsefc-public  CORS: GET and HEAD from any origin")
    print("nsefc-scratch lifecycle: expire objects after 14 days")
    if not args.dry_run:
        client.put_bucket_cors(Bucket="nsefc-public", CORSConfiguration=PUBLIC_CORS)
        client.put_bucket_lifecycle_configuration(
            Bucket="nsefc-scratch", LifecycleConfiguration=SCRATCH_LIFECYCLE
        )
    print("done" if not args.dry_run else "dry run: nothing changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
