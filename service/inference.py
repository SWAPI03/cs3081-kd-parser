"""Loading the student and turning one command into its raw output text.

Shared by the service (service/app.py) and the evaluation script (training/predict.py), so the
scores in results/ come from exactly the same prompt format and decoding as the live service.

Prompt format (same as in training):   "Command: <the command>\nJSON:"
Decoding: greedy (deterministic). Generation stops at the end-of-text token, or as soon as the
first JSON object closes (its "{" is matched by "}"), or after max_new_tokens.
"""
import json
import os

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList

SCHEMA_PATH = os.environ.get(
    "SCHEMA_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "schema.json"))


def prompt_for(command):
    return f"Command: {command}\nJSON:"


def _closing_index(text):
    """Index of the "}" that closes the first "{" in text, or -1 if it is not closed yet."""
    start = text.find("{")
    if start < 0:
        return -1
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def first_object(text):
    """Text up to and including the "}" that closes the first "{" (all text if it never closes)."""
    end = _closing_index(text)
    return text if end < 0 else text[: end + 1]


class _ObjectClosed(StoppingCriteria):
    """Stop generating as soon as the continuation contains one complete JSON object."""

    def __init__(self, tokenizer, prompt_len):
        self.tokenizer, self.prompt_len = tokenizer, prompt_len

    def __call__(self, input_ids, scores, **kwargs):
        text = self.tokenizer.decode(input_ids[0, self.prompt_len:], skip_special_tokens=True)
        return _closing_index(text) >= 0


class Student:
    def __init__(self, model_dir, max_new_tokens=64, threads=None):
        if threads:
            torch.set_num_threads(threads)
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForCausalLM.from_pretrained(model_dir, torch_dtype=torch.float32)
        self.model.eval()
        self.max_new_tokens = max_new_tokens

    @torch.inference_mode()
    def raw_output(self, command):
        enc = self.tokenizer(prompt_for(command), return_tensors="pt")
        n = enc["input_ids"].shape[1]
        out = self.model.generate(
            **enc,
            max_new_tokens=self.max_new_tokens,
            do_sample=False,
            eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=self.tokenizer.eos_token_id,
            stopping_criteria=StoppingCriteriaList([_ObjectClosed(self.tokenizer, n)]),
        )
        text = self.tokenizer.decode(out[0, n:], skip_special_tokens=True)
        return first_object(text).strip()


def load_schema(path=SCHEMA_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate(raw, schema):
    """Return the parsed object if it matches schema.json exactly, otherwise None."""
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict) or sorted(obj) != sorted(schema["keys"]):
        return None
    if obj["intent"] not in schema["intents"]:
        return None
    for slot in ("date", "time", "place"):
        if obj[slot] is not None and not isinstance(obj[slot], str):
            return None
    return obj
