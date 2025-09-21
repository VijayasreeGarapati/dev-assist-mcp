from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import requests
import json
import logging
import re
from datetime import datetime
from pathlib import Path

# Import config system
from config import get_config

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
    analysis_metadata: Dict

    def dict(self):
        return asdict(self)

def validate_pr_input(pr_diff_text: str) -> tuple[bool, str]:
    """Validate PR input before processing"""
    config = get_config()
    
    if not pr_diff_text:
        return False, "PR diff text is empty"
    
    if not pr_diff_text.strip():
        return False, "PR diff text contains only whitespace"
    
    if len(pr_diff_text) > config.analysis.max_diff_size:
        return False, f"PR diff too large ({len(pr_diff_text)} chars). Maximum {config.analysis.max_diff_size} characters."
    
    if "diff --git" not in pr_diff_text:
        return False, "Invalid PR diff format - missing 'diff --git' header"
    
    return True, "Valid input"

def calculate_risk_score(files_changed: List[str], notable_issues: List[Dict]) -> float:
    """Calculate risk score based on files and issues with configurable weights"""
    config = get_config()
    
    base_risk = 0.1
    
    # Risk from issues
    issue_risk = 0.0
    for issue in notable_issues:
        risk_weight = issue.get('risk_weight', 0.2)
        issue_risk += risk_weight
    
    # Risk from file types
    file_risk = 0.0
    for file_path in files_changed:
        file_ext = Path(file_path).suffix.lower()
        weight = config.analysis.file_type_weights.get(file_ext, 1.0)
        file_risk += weight * 0.1
    
    # Combine risks
    total_risk = base_risk + issue_risk + (file_risk / len(files_changed) if files_changed else 0)
    
    # Cap at 1.0
    return min(total_risk, 1.0)

def get_llm_summary(pr_diff_text: str, analysis_data: dict) -> tuple[str, dict]:
    """Generate human-readable summary using Ollama with error handling"""
    config = get_config()
    
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
    
    start_time = datetime.now()
    
    for model in config.ollama.models:
        try:
            logger.info(f"Attempting LLM analysis with model: {model}")
            metadata["llm_used"] = model
            
            response = requests.post(f'{config.ollama.base_url}/api/generate',
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": config.ollama.temperature,
                        "top_p": config.ollama.top_p,
                        "num_predict": config.ollama.max_tokens,
                        "stop": ["Note:", "Overall,", "\n\nNote"]
                    }
                },
                timeout=config.ollama.timeout
            )
            
            if response.status_code == 200:
                result = response.json()['response'].strip()
                cleaned_result = clean_ai_response(result)
                
                metadata["llm_success"] = True
                metadata["response_time"] = (datetime.now() - start_time).total_seconds()
                
                logger.info(f"Successfully got LLM response from {model}")
                return cleaned_result, metadata
            else:
                logger.warning(f"Model {model} returned status {response.status_code}")
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
    
    summary = f"This PR modifies {len(files)} file(s)"
    
    if issues:
        high_risk_issues = [i for i in issues if i.get('risk_weight', 0) > 0.5]
        if high_risk_issues:
            summary += f" and contains {len(high_risk_issues)} high-risk issue(s)"
        else:
            summary += f" and contains {len(issues)} issue(s)"
    
    if risk_score > 0.7:
        summary += ". High risk - requires security review."
    elif risk_score > 0.3:
        summary += ". Medium risk - careful review recommended."
    else:
        summary += ". Low risk - standard review process."
    
    return summary

def clean_ai_response(response: str) -> str:
    """Remove common AI meta-commentary"""
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
    
    # Clean up formatting
    response = re.sub(r'\s+', ' ', response)
    response = re.sub(r'\.\s*\.', '.', response)
    
    if response and not response.endswith(('.', '!', '?')):
        response += '.'
    
    return response

def analyze_pr(pr_diff_text: str) -> AnalyzePROutput:
    """Enhanced PR analysis with configuration management"""
    config = get_config()
    
    analysis_metadata = {
        "timestamp": datetime.now().isoformat(),
        "input_valid": False,
        "parsing_success": False,
        "llm_metadata": {},
        "config_used": {
            "models": config.ollama.models,
            "max_diff_size": config.analysis.max_diff_size,
            "risk_keywords_count": len(config.analysis.risk_keywords)
        }
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
        
        # Step 2: Parse diff with enhanced analysis
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
                    # Check for configured risk keywords
                    line_lower = line.lower()
                    for keyword, weight in config.analysis.risk_keywords.items():
                        if keyword.lower() in line_lower:
                            notable_issues.append({
                                "file": current_file, 
                                "issue": f"Contains {keyword} in added lines",
                                "line_preview": line.strip()[:100],
                                "risk_weight": weight,
                                "keyword": keyword
                            })
                            break  # Only report first match per line
                            
            except Exception as line_error:
                logger.warning(f"Error processing line: {line_error}")
                continue
        
        analysis_metadata["parsing_success"] = True
        analysis_metadata["files_found"] = len(files_changed)
        analysis_metadata["issues_found"] = len(notable_issues)
        
        # Step 3: Calculate risk using config-based scoring
        summary = f"PR changes in {len(files_changed)} file(s)."
        risk_score = calculate_risk_score(files_changed, notable_issues)
        
        # Dynamic suggestions
        suggested_tests = ["Run unit tests"]
        if risk_score > 0.3:
            suggested_tests.append("Run integration tests")
        if risk_score > 0.5:
            suggested_tests.append("Security review required")
            
        suggested_labels = ["needs-review"] if notable_issues else ["approved"]
        if risk_score > 0.7:
            suggested_labels = ["high-risk", "security-review"]
        
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
        
        return AnalyzePROutput(
            summary="Analysis encountered an unexpected error",
            risk_score=0.5,
            files_changed=["error"],
            notable_issues=[{"file": "system", "issue": f"Analysis error: {str(e)}"}],
            suggested_tests=["Manual review required"],
            suggested_labels=["analysis-failed"],
            human_readable_review=f"PR analysis failed due to system error. Manual review recommended.",
            analysis_metadata=analysis_metadata
        )