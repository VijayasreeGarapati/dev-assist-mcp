# app/main.py

from fastapi import FastAPI, HTTPException
from app.tools.analyse_pr import AnalyzePRInput, AnalyzePROutput, analyze_pr

app = FastAPI(title="MCP Server for PR Analysis")

# -----------------------------
# Health check endpoint
# -----------------------------
@app.get("/health")
def health_check():
    return {"status": "ok"}

# -----------------------------
# MCP endpoint for PR analysis
# -----------------------------
@app.post("/mcp", response_model=AnalyzePROutput)
def mcp_analyze_pr(input_data: AnalyzePRInput):
    try:
        result = analyze_pr(input_data.pr_diff_text)
        return result
    except Exception as e:
        # Catch any exceptions to avoid crashing
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")