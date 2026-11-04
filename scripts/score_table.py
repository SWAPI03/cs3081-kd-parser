"""Print the teacher / base / student scores side by side (the table in the report)."""
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
files = [("Teacher phi3.5", "results/teacher_validation.json"),
         ("Untrained Pythia-70M", "results/score_base.json"),
         ("Student v1", "results/score_student_v1.json"),
         ("Student v2", "results/score_student_v2.json")]
metrics = ["json_validity", "intent_accuracy", "date_accuracy", "time_accuracy",
           "place_accuracy", "full_frame"]
print("| Model | " + " | ".join(metrics) + " |")
print("|---|" + "---|" * len(metrics))
for name, path in files:
    p = os.path.join(ROOT, path)
    if os.path.exists(p):
        r = json.load(open(p))
        print(f"| {name} | " + " | ".join(f"{r[m]:.1f}" for m in metrics) + " |")
    else:
        print(f"| {name} | " + " | ".join("n/a" for _ in metrics) + " |")
