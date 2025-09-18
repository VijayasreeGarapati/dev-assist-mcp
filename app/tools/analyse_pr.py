from dataclasses import dataclass, asdict
from typing import List, Dict
import requests
import json

@dataclass
class AnalyzePRInput:
    pr_diff_text: str

@dataclass
class AnalyzePROutput:
    summary: str
    risk_score: float
    files_changed: List[str]
    notable_issues: List[Dict]
    suggested_tests: List[str]
    suggested_labels: List[str]
    human_readable_review: str

    def dict(self):
        return asdict(self)

def get_llm_summary(pr_diff_text: str, analysis_data: dict) -> str:
    """Generate human-readable summary using Ollama on Mac"""
    
    # Create context about the changes
    issues_context = ""
    if analysis_data['notable_issues']:
        issues_list = [issue['issue'] for issue in analysis_data['notable_issues']]
        issues_context = f"\nIssues detected: {', '.join(issues_list)}"
    
    risk_level = "high" if analysis_data['risk_score'] > 0.7 else "medium" if analysis_data['risk_score'] > 0.3 else "low"
    
    prompt = f"""You are a senior software engineer conducting a code review. Analyze this PR and provide a professional assessment.

Files Changed: {', '.join(analysis_data['files_changed'])}
Risk Level: {risk_level}{issues_context}

PR Diff:
{pr_diff_text}

Provide a concise professional code review (2-3 sentences) covering:
1. What functionality was added/changed
2. Any security, performance, or code quality concerns
3. Overall recommendation

Be direct and actionable. Focus on what matters to developers."""
    
    try:
        response = requests.post('http://localhost:11434/api/generate',
            json={
                "model": "llama3.2:3b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,  # More focused responses
                    "top_p": 0.8,
                    "num_predict": 120,  # Shorter, more concise
                    "stop": ["Note:", "Overall,", "\n\nNote"]  # Stop meta-commentary
                }
            },
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json()['response'].strip()
            
            # Clean up common AI response patterns
            result = clean_ai_response(result)
            return result
        else:
            return generate_fallback_summary(analysis_data)
            
    except requests.exceptions.ConnectionError:
        return generate_fallback_summary(analysis_data)
    except Exception as e:
        return generate_fallback_summary(analysis_data)

def clean_ai_response(response: str) -> str:
    """Remove common AI meta-commentary and improve response quality"""
    import re
    
    # Remove common prefixes
    prefixes_to_remove = [
        "Here is a concise professional code review:",
        "Here is a professional assessment:",
        "Here's my code review:",
        "Based on the PR diff:",
        "Looking at this PR:"
    ]
    
    for prefix in prefixes_to_remove:
        if response.startswith(prefix):
            response = response[len(prefix):].strip()
    
    # Remove meta-commentary endings
    endings_to_remove = [
        r"Note:.*$",
        r"Overall.*recommendation.*$",
        r"I've kept.*concise.*$"
    ]
    
    for pattern in endings_to_remove:
        response = re.sub(pattern, "", response, flags=re.IGNORECASE | re.MULTILINE).strip()
    
    # Clean up extra whitespace
    response = re.sub(r'\s+', ' ', response)
    response = re.sub(r'\.\s*\.', '.', response)  # Remove double periods
    
    # Ensure it ends with proper punctuation
    if response and not response.endswith(('.', '!', '?')):
        response += '.'
    
    return response

def generate_fallback_summary(analysis_data: dict) -> str:
    """Fallback summary if Ollama is unavailable"""
    risk_level = "high" if analysis_data['risk_score'] > 0.7 else "medium" if analysis_data['risk_score'] > 0.3 else "low"
    issues_text = f" with {len(analysis_data['notable_issues'])} issues identified" if analysis_data['notable_issues'] else ""
    
    return f"This PR modifies {len(analysis_data['files_changed'])} file(s){issues_text}. Risk assessment: {risk_level}. Recommended for {'careful review' if risk_level != 'low' else 'standard review process'}."

def analyze_pr(pr_diff_text: str) -> AnalyzePROutput:
    """
    Example analysis logic:
    - Counts files changed
    - Finds TODOs in added lines
    - Returns a mock risk score and suggested tests/labels
    """
    files_changed = []
    notable_issues = []
    
    lines = pr_diff_text.split("\n")
    current_file = None
    for line in lines:
        if line.startswith("diff --git"):
            parts = line.split(" ")
            if len(parts) >= 3:
                current_file = parts[2][2:]  # remove 'b/' prefix
                files_changed.append(current_file)
        elif line.startswith("+") and current_file:
            if "TODO" in line or "FIXME" in line:
                issue_type = "TODO" if "TODO" in line else "FIXME"
                notable_issues.append({"file": current_file, "issue": f"Contains {issue_type} in added lines"})
    
    summary = f"PR changes in {len(files_changed)} file(s)."
    risk_score = 0.5 if notable_issues else 0.1
    suggested_tests = ["Run unit tests"]
    suggested_labels = ["needs-review"] if notable_issues else ["approved"]
    
    # Prepare analysis data for LLM
    analysis_data = {
        'files_changed': files_changed,
        'risk_score': risk_score,
        'notable_issues': notable_issues,
        'summary': summary
    }
    
    # Generate human-readable review using LLM
    human_readable_review = get_llm_summary(pr_diff_text, analysis_data)
    
    return AnalyzePROutput(
        summary=summary,
        risk_score=risk_score,
        files_changed=files_changed,
        notable_issues=notable_issues,
        suggested_tests=suggested_tests,
        suggested_labels=suggested_labels,
        human_readable_review=human_readable_review
    )