"""Inference service for the command parser (Task 3). Listens on port 8000.

  POST /parse   {"text": "..."} -> 200 + the four-key JSON object, nothing else in the body.
                Headers: X-Model-Version (MODEL_VERSION) and X-Served-By (the Pod name).
                If the model output does not match schema.json -> 500 {"error": "invalid_model_output"}.
  GET  /healthz 200 while the process is alive.
  GET  /readyz  503 until the model is loaded, then 200.

Configuration, all from environment variables:
  MODEL_URI       e.g. s3://models/v1   (the model is downloaded from object storage at start-up)
  MODEL_VERSION   e.g. v1
  S3_ENDPOINT     e.g. http://seaweedfs.data.svc.cluster.local:8333
  MAX_NEW_TOKENS  generation limit, e.g. 64
  FAULT_INJECT    "1" replaces the model output with the text `not json` (tests the 500 path)
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY come from the Kubernetes Secret s3-credentials.
"""
import os
import socket
import tempfile
import threading
import time

import boto3
from botocore.client import Config
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

import inference

MODEL_URI = os.environ["MODEL_URI"]
MODEL_VERSION = os.environ["MODEL_VERSION"]
S3_ENDPOINT = os.environ["S3_ENDPOINT"]
MAX_NEW_TOKENS = int(os.environ["MAX_NEW_TOKENS"])
POD_NAME = os.environ.get("HOSTNAME") or socket.gethostname()   # in Kubernetes: the Pod name

SCHEMA = inference.load_schema()
state = {"student": None}
lock = threading.Lock()   # one generation at a time: the container has one CPU


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def download_model(uri):
    """Copy every object under s3://bucket/prefix/ into a local folder and return the folder."""
    bucket, _, prefix = uri[len("s3://"):].partition("/")
    prefix = prefix.rstrip("/") + "/"
    s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT, region_name="us-east-1",
                      config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
    dest = tempfile.mkdtemp(prefix="model-")
    objects = s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
    if not objects:
        raise RuntimeError(f"nothing found under {uri}")
    for obj in objects:
        name = obj["Key"][len(prefix):]
        log(f"downloading s3://{bucket}/{obj['Key']} ({obj['Size'] / 1e6:.1f} MB) from {S3_ENDPOINT}")
        s3.download_file(bucket, obj["Key"], os.path.join(dest, name))
    return dest


def load_in_background():
    while state["student"] is None:
        try:
            start = time.time()
            folder = download_model(MODEL_URI)
            state["student"] = inference.Student(folder, max_new_tokens=MAX_NEW_TOKENS, threads=1)
            log(f"model {MODEL_VERSION} from {MODEL_URI} loaded in {time.time() - start:.1f}s; ready")
        except Exception as e:  # storage not up yet, etc.: stay not-ready and retry
            log(f"model load failed: {e!r}; retrying in 5s")
            time.sleep(5)


app = FastAPI(title="command-parser")


@app.on_event("startup")
def startup():
    log(f"starting: pod={POD_NAME} MODEL_URI={MODEL_URI} MODEL_VERSION={MODEL_VERSION} "
        f"MAX_NEW_TOKENS={MAX_NEW_TOKENS} FAULT_INJECT={os.environ.get('FAULT_INJECT', '0')}")
    threading.Thread(target=load_in_background, daemon=True).start()


class ParseRequest(BaseModel):
    text: str


def headers():
    return {"X-Model-Version": MODEL_VERSION, "X-Served-By": POD_NAME}


@app.get("/healthz")
def healthz():
    return Response(status_code=200)


@app.get("/readyz")
def readyz():
    return Response(status_code=200 if state["student"] is not None else 503)


@app.post("/parse")
def parse(req: ParseRequest):
    student = state["student"]
    if student is None:
        return JSONResponse({"error": "model_not_ready"}, status_code=503, headers=headers())
    with lock:
        raw = student.raw_output(req.text)
    if os.environ.get("FAULT_INJECT") == "1":
        raw = "not json"
    obj = inference.validate(raw, SCHEMA)
    if obj is None:
        log(f"invalid model output for {req.text!r}: {raw[:120]!r}")
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=headers())
    return JSONResponse({k: obj[k] for k in SCHEMA["keys"]}, status_code=200, headers=headers())
