"""Calls the teacher model (phi3.5 served by Ollama).

Used by the labelling worker (Task 1) and by scripts/eval_teacher.py (Task 2, step 6),
so the teacher is always run with the SAME prompt and the SAME settings.

Settings fixed by the brief: model phi3.5, temperature 0, seed 42.
Two extra settings, both disclosed in the report:
  format="json"   Ollama only lets the model emit syntactically valid JSON. The model still
                  chooses the keys, the intent and the slot values itself.
  num_predict=96  hard cap on reply length (a correct reply is about 30 tokens), so a
                  runaway reply cannot block a worker for minutes.
"""
import json
import os
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("TEACHER_MODEL", "phi3.5")
OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 96}
FORMAT = "json"

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROMPT_FILE = os.path.join(_HERE, "..", "prompts", "teacher_prompt.txt")


def load_prompt(path=None):
    path = path or os.environ.get("PROMPT_FILE") or DEFAULT_PROMPT_FILE
    with open(path, encoding="utf-8") as f:
        template = f.read()
    if "{command}" not in template:
        raise ValueError(f"{path} must contain the placeholder {{command}}")
    return template


def build_prompt(template, command):
    # str.replace, not str.format: the prompt contains JSON braces.
    return template.replace("{command}", command)


def _candidate_urls():
    """Where Ollama might be. The first one that answers is used."""
    if os.environ.get("OLLAMA_URL"):
        return [os.environ["OLLAMA_URL"].rstrip("/")]
    urls = ["http://localhost:11434", "http://host.k3d.internal:11434",
            "http://host.docker.internal:11434"]
    # WSL2 (NAT mode): Windows is the default gateway.
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if parts[1] == "00000000":
                    gw = bytes.fromhex(parts[2])[::-1]
                    urls.append("http://%d.%d.%d.%d:11434" % tuple(gw))
    except OSError:
        pass
    return urls


def resolve_url():
    for url in _candidate_urls():
        try:
            with urllib.request.urlopen(url + "/api/tags", timeout=3) as r:
                if r.status == 200:
                    return url
        except (urllib.error.URLError, OSError):
            continue
    raise RuntimeError("Ollama is not reachable. Tried: " + ", ".join(_candidate_urls()))


def ask(url, prompt, retries=4, timeout=600):
    """Send one prompt to the teacher and return its reply text exactly as generated."""
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "format": FORMAT, "options": OPTIONS, "keep_alive": "60m"}).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url + "/api/generate", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())["response"]
        except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError) as e:
            if attempt == retries - 1:
                raise
            wait = 5 * (attempt + 1)
            print(f"[teacher] request failed ({e}); retrying in {wait}s", flush=True)
            time.sleep(wait)
