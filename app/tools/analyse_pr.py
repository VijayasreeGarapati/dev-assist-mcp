# app/tools/analyse_pr.py

from pydantic import BaseModel
from typing import List
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# -----------------------------
# Pydantic Models for API
# -----------------------------
class NotableIssue(BaseModel):
    file: str
    hunk_start: str  # string type to avoid validation errors
    issue: str

class AnalyzePROutput(BaseModel):
    summary: str
    risk_score: float
    files_changed: List[str]
    notable_issues: List[NotableIssue]
    suggested_tests: List[str]
    suggested_labels: List[str]
    human_readable_review: str

class AnalyzePRInput(BaseModel):
    pr_diff_text: str

# -----------------------------
# Load Free Code Model
# -----------------------------
MODEL_NAME = "Salesforce/codet5-small"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

def summarize_diff(diff_text: str) -> str:
    """
    Generate a human-readable summary of PR diff using Codet5.
    """
    inputs = tokenizer(diff_text, return_tensors="pt", truncation=True, max_length=512)
    outputs = model.generate(**inputs, max_new_tokens=150)
    summary = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return summary

# -----------------------------
# PR Analysis Logic
# -----------------------------
def analyze_pr(pr_diff_text: str) -> AnalyzePROutput:
    """
    Analyze PR diff text and produce structured review.
    """
    lines = pr_diff_text.splitlines()
    files_changed = []
    notable_issues = []

    current_file = None
    for line in lines:
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 3:
                current_file = parts[2].replace("b/", "")
                files_changed.append(current_file)
        if line.strip().startswith("# TODO") and current_file:
            notable_issues.append({
                "file": current_file,
                "hunk_start": "0",  # string
                "issue": line.strip()
            })

    summary = f"PR changes in {len(files_changed)} files."
    risk_score = 0.5 if notable_issues else 0.1
    suggested_tests = ["Run unit tests"]
    suggested_labels = ["needs-review"]

    # Use the code model to generate human-readable review
    try:
        human_readable_review = summarize_diff(pr_diff_text)
    except Exception as e:
        human_readable_review = f"Could not generate review automatically: {e}"

    # Convert notable_issues dicts into Pydantic models
    notable_issues_models = [NotableIssue(**issue) for issue in notable_issues]

    return AnalyzePROutput(
        summary=summary,
        risk_score=risk_score,
        files_changed=files_changed,
        notable_issues=notable_issues_models,
        suggested_tests=suggested_tests,
        suggested_labels=suggested_labels,
        human_readable_review=human_readable_review
    )