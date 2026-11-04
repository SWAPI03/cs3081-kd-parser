import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for sub in ("worker", "service", "scripts"):
    sys.path.insert(0, os.path.join(ROOT, sub))
