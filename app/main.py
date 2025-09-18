from mcp.server.fastmcp import FastMCP
from tools.analyse_pr import AnalyzePRInput, AnalyzePROutput, analyze_pr

# Initialize the MCP server
mcp = FastMCP("pr_analyzer_mcp")

# Define the tool
@mcp.tool()
def analyze_pr_tool(pr_diff_text: str):
    """Analyze PR diff text and return structured output."""
    result = analyze_pr(pr_diff_text)
    # Return the dataclass directly, FastMCP will handle serialization
    return result

# Run the server over STDIO for local testing
if __name__ == "__main__":
    mcp.run(transport="stdio")