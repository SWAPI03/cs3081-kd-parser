"""Small helpers for talking to SeaweedFS through its S3 API (boto3).

Every setting comes from environment variables, so the same code runs on the laptop
(S3_ENDPOINT=http://localhost:8333) and inside the cluster
(S3_ENDPOINT=http://seaweedfs.data.svc.cluster.local:8333).
Credentials: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (from .env or a Kubernetes Secret).
"""
import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

DEFAULT_ENDPOINT = "http://localhost:8333"


def load_dotenv(path=".env"):
    """Read KEY=VALUE lines from .env into os.environ.

    On the laptop .env is the source of truth for this project, so it overrides any AWS_*
    variables already set in the shell. Inside the cluster there is no .env file: the keys
    come from a Kubernetes Secret as environment variables.
    """
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()


def client():
    load_dotenv()
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", DEFAULT_ENDPOINT),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      retries={"max_attempts": 5, "mode": "standard"}),
    )


def get_bytes(s3, bucket, key):
    """Return the object's bytes, or None if it does not exist."""
    try:
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NoSuchBucket"):
            return None
        raise


def put_bytes(s3, bucket, key, data):
    s3.put_object(Bucket=bucket, Key=key, Body=data)


def list_keys(s3, bucket, prefix):
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", [])]
    return sorted(keys)


def ensure_bucket(s3, bucket):
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
