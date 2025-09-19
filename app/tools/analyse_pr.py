from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import requests
import json
import logging
import re
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    analysis_metadata: Dict  # New: tracks what worked/failed

    def dict(self):
        return asdict(self)

class PRAnalysisError(Exception):
    """Custom exception for PR analysis errors"""
    pass

def validate_pr_input(pr_diff_text: str) -> tuple[bool, str]:
    """Validate PR input before processing"""
    if not pr_diff_text:
        return False, "PR diff text is empty"
    
    if not pr_diff_text.strip():
        return False, "PR diff text contains only whitespace"
    
    if len(pr_diff_text) > 50000:  # 50KB limit
        return False, f"PR diff too large ({len(pr_diff_text)} chars). Maximum 50,000 characters."
    
    if "diff --git" not in pr_diff_text:
        return False, "Invalid PR diff format - missing 'diff --git' header"
    
    return True, "Valid input"

def get_llm_summary(pr_diff_text: str, analysis_data: dict) -> tuple[str, dict]:
    """Generate human-readable summary using Ollama with error handling"""
    
    metadata = {
        "llm_used": None,
        "llm_success": False,
        "llm_error": None,
        "response_time": None
    }
    
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
    
    # Try multiple models in order of preference
    models_to_try = ["llama3.2:3b", "qwen2.5-coder:1.5b", "tinyllama"]
    
    start_time = datetime.now()
    
    for model in models_to_try:
        try:
            logger.info(f"Attempting LLM analysis with model: {model}")
            metadata["llm_used"] = model
            
            response = requests.post('http://localhost:11434/api/generate',
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "top_p": 0.8,
                        "num_predict": 120,
                        "stop": ["Note:", "Overall,", "\n\nNote"]
                    }
                },
                timeout=20  # Shorter timeout per model
            )
            
            if response.status_code == 200:
                result = response.json()['response'].strip()
                cleaned_result = clean_ai_response(result)
                
                metadata["llm_success"] = True
                metadata["response_time"] = (datetime.now() - start_time).total_seconds()
                
                logger.info(f"Successfully got LLM response from {model}")
                return cleaned_result, metadata
            else:
                logger.warning(f"Model {model} returned status {response.status_code}: {response.text}")
                metadata["llm_error"] = f"HTTP {response.status_code}"
                
        except requests.exceptions.ConnectionError:
            logger.warning(f"Could not connect to Ollama for model {model}")
            metadata["llm_error"] = "Connection failed"
            continue
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout waiting for model {model}")
            metadata["llm_error"] = "Timeout"
            continue
        except Exception as e:
            logger.warning(f"Model {model} failed with error: {e}")
            metadata["llm_error"] = str(e)
            continue
    
    # All models failed - return intelligent fallback
    logger.info("All LLM models failed, using intelligent fallback")
    metadata["response_time"] = (datetime.now() - start_time).total_seconds()
    
    fallback_summary = generate_intelligent_fallback(analysis_data)
    return fallback_summary, metadata

def generate_intelligent_fallback(analysis_data: dict) -> str:
    """Generate intelligent summary when LLM fails"""
    files = analysis_data['files_changed']
    issues = analysis_data['notable_issues']
    risk_score = analysis_data['risk_score']
    
    # Determine file types for context
    file_types = set()
    for file in files:
        if file.endswith(('.py', '.pyx')):
            file_types.add('Python')
        elif file.endswith(('.js', '.ts', '.jsx', '.tsx')):
            file_types.add('JavaScript/TypeScript')
        elif file.endswith(('.java', '.kt')):
            file_types.add('Java/Kotlin')
        elif file.endswith(('.cpp', '.c', '.h')):
            file_types.add('C/C++')
        else:
            file_types.add('code')
    
    file_desc = ', '.join(file_types) if file_types else 'code'
    
    if risk_score > 0.7:
        risk_desc = "high risk due to significant concerns"
    elif risk_score > 0.3:
        risk_desc = "medium risk requiring review"
    else:
        risk_desc = "low risk with minimal concerns"
    
    summary = f"This PR modifies {len(files)} {file_desc} file(s)"
    
    if issues:
        issue_types = [issue['issue'] for issue in issues]
        summary += f" and contains {len(issues)} issue(s): {', '.join(issue_types)}"
    
    summary += f". Assessment indicates {risk_desc}."
    
    if risk_score > 0.3:
        summary += " Recommend careful review before merging."
    else:
        summary += " Changes appear safe for standard review process."
    
    return summary

def clean_ai_response(response: str) -> str:
    """Remove common AI meta-commentary and improve response quality"""
    # Remove common prefixes
    prefixes_to_remove = [
        "Here is a concise professional code review:",
        "Here's a concise professional code review:",
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

def analyze_pr(pr_diff_text: str) -> AnalyzePROutput:
    """
    Enhanced PR analysis with comprehensive error handling
    """
    
    analysis_metadata = {
        "timestamp": datetime.now().isoformat(),
        "input_valid": False,
        "parsing_success": False,
        "llm_metadata": {}
    }
    
    try:
        # Step 1: Validate input
        logger.info("Starting PR analysis")
        is_valid, validation_msg = validate_pr_input(pr_diff_text)
        
        if not is_valid:
            logger.error(f"Input validation failed: {validation_msg}")
            analysis_metadata["validation_error"] = validation_msg
            
            return AnalyzePROutput(
                summary="Analysis failed due to invalid input",
                risk_score=0.0,
                files_changed=[],
                notable_issues=[{"file": "input", "issue": validation_msg}],
                suggested_tests=["Fix input format"],
                suggested_labels=["invalid-input"],
                human_readable_review=f"Cannot analyze PR: {validation_msg}",
                analysis_metadata=analysis_metadata
            )
        
        analysis_metadata["input_valid"] = True
        
        # Step 2: Parse diff safely
        try:
            files_changed = []
            notable_issues = []
            
            lines = pr_diff_text.split("\n")
            current_file = None
            
            for line in lines:
                try:
                    if line.startswith("diff --git"):
                        parts = line.split(" ")
                        if len(parts) >= 3:
                            current_file = parts[2][2:]  # remove 'b/' prefix
                            if current_file not in files_changed:
                                files_changed.append(current_file)
                    elif line.startswith("+") and current_file:
                        if "TODO" in line or "FIXME" in line or "HACK" in line:
                            issue_type = "TODO" if "TODO" in line else "FIXME" if "FIXME" in line else "HACK"
                            notable_issues.append({
                                "file": current_file, 
                                "issue": f"Contains {issue_type} in added lines",
                                "line_preview": line.strip()[:100]  # First 100 chars
                            })
                except Exception as line_error:
                    logger.warning(f"Error processing line: {line_error}")
                    continue
            
            analysis_metadata["parsing_success"] = True
            analysis_metadata["files_found"] = len(files_changed)
            analysis_metadata["issues_found"] = len(notable_issues)
            
        except Exception as parse_error:
            logger.error(f"Diff parsing failed: {parse_error}")
            analysis_metadata["parsing_error"] = str(parse_error)
            
            # Fallback parsing
            files_changed = ["unknown_file"]
            notable_issues = [{"file": "parser", "issue": "Diff parsing failed"}]
        
        # Step 3: Calculate risk and recommendations
        summary = f"PR changes in {len(files_changed)} file(s)."
        risk_score = min(0.1 + (len(notable_issues) * 0.2), 1.0)  # Cap at 1.0
        suggested_tests = ["Run unit tests", "Run integration tests"] if risk_score > 0.3 else ["Run unit tests"]
        suggested_labels = ["needs-review"] if notable_issues else ["approved"]
        
        # Step 4: Generate human-readable review
        analysis_data = {
            'files_changed': files_changed,
            'risk_score': risk_score,
            'notable_issues': notable_issues,
            'summary': summary
        }
        
        human_readable_review, llm_metadata = get_llm_summary(pr_diff_text, analysis_data)
        analysis_metadata["llm_metadata"] = llm_metadata
        
        logger.info(f"PR analysis completed successfully. Risk score: {risk_score}")
        
        return AnalyzePROutput(
            summary=summary,
            risk_score=risk_score,
            files_changed=files_changed,
            notable_issues=notable_issues,
            suggested_tests=suggested_tests,
            suggested_labels=suggested_labels,
            human_readable_review=human_readable_review,
            analysis_metadata=analysis_metadata
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in PR analysis: {e}")
        analysis_metadata["unexpected_error"] = str(e)
        
        # Ultimate fallback
        return AnalyzePROutput(
            summary="Analysis encountered an unexpected error",
            risk_score=0.5,
            files_changed=["error"],
            notable_issues=[{"file": "system", "issue": f"Analysis error: {str(e)}"}],
            suggested_tests=["Manual review required"],
            suggested_labels=["analysis-failed"],
            human_readable_review=f"PR analysis failed due to system error: {str(e)}. Manual review recommended.",
            analysis_metadata=analysis_metadata
        )