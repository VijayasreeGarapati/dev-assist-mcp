import subprocess
import json
import sys
import os

def call_analyze_pr_tool(pr_diff_text: str):
    """
    Calls the MCP server over STDIO with the analyze_pr_tool.
    """
    # Get the correct path to main.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    main_py_path = os.path.join(current_dir, "main.py")
    
    # Start the MCP server as a subprocess
    proc = subprocess.Popen(
        [sys.executable, main_py_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0  # Unbuffered
    )

    try:
        # Initialize the MCP connection
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }

        # Send initialize request
        proc.stdin.write(json.dumps(init_request) + "\n")
        proc.stdin.flush()

        # Read initialize response
        init_response_line = proc.stdout.readline()
        if not init_response_line:
            stderr_output = proc.stderr.read()
            raise RuntimeError(f"No initialize response from MCP server. Stderr: {stderr_output}")
        
        init_response = json.loads(init_response_line)
        if "error" in init_response:
            raise RuntimeError(f"Initialize error: {init_response['error']}")

        # Send initialized notification
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        proc.stdin.write(json.dumps(initialized_notification) + "\n")
        proc.stdin.flush()

        # Construct the MCP tool call request
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "analyze_pr_tool",
                "arguments": {
                    "pr_diff_text": pr_diff_text
                }
            }
        }

        # Send tool call request
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()

        # Read response
        response_line = proc.stdout.readline()
        if not response_line:
            stderr_output = proc.stderr.read()
            raise RuntimeError(f"No tool response from MCP server. Stderr: {stderr_output}")

        response = json.loads(response_line)
        
        # Extract the actual result from MCP response format
        if "result" in response and "content" in response["result"]:
            content = response["result"]["content"]
            if content and len(content) > 0 and content[0]["type"] == "text":
                # If the text is JSON string, parse it
                text_content = content[0]["text"]
                try:
                    parsed_result = json.loads(text_content)
                    return {"result": parsed_result}
                except json.JSONDecodeError:
                    return {"result": text_content}
        
        return response

    except Exception as e:
        # Read any error output
        stderr_output = proc.stderr.read()
        print(f"Error: {e}")
        if stderr_output:
            print(f"Server stderr: {stderr_output}")
        raise
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    # Example PR diff
    pr_diff_initial = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,5 @@
 def hello():
     pass
+print('Hello')
+# TODO: refactor this"""

   # Real-world PR diff example - adding user authentication validation
    pr_diff = """diff --git a/auth/validators.py b/auth/validators.py
index a1b2c3d..e4f5g6h 100644
--- a/auth/validators.py
+++ b/auth/validators.py
@@ -1,5 +1,7 @@
 import re
+import hashlib
 from typing import Optional
+from datetime import datetime, timedelta
 
 class UserValidator:
     def __init__(self):
@@ -15,6 +17,22 @@ class UserValidator:
         if len(password) < 8:
             return False, "Password must be at least 8 characters long"
         return True, "Valid password"
+    
+    def validate_email_format(self, email: str) -> tuple[bool, str]:
+        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}
+        if not re.match(email_pattern, email):
+            return False, "Invalid email format"
+        return True, "Valid email format"
+    
+    def hash_password(self, password: str) -> str:
+        # TODO: Use more secure hashing algorithm like bcrypt
+        salt = "user_salt_2024"
+        return hashlib.sha256((password + salt).encode()).hexdigest()
+    
+    def is_password_expired(self, last_changed: datetime, days_valid: int = 90) -> bool:
+        if not last_changed:
+            return True
+        return datetime.now() - last_changed > timedelta(days=days_valid)
 
 def create_user(username: str, email: str, password: str):
     validator = UserValidator()
@@ -26,4 +44,11 @@ def create_user(username: str, email: str, password: str):
     if not is_valid_password:
         raise ValueError(password_msg)
     
+    # Validate email format
+    is_valid_email, email_msg = validator.validate_email_format(email)
+    if not is_valid_email:
+        raise ValueError(email_msg)
+    
+    hashed_password = validator.hash_password(password)
     print(f"User {username} created successfully!")
+    return {"username": username, "email": email, "password_hash": hashed_password}"""

    print("Calling analyze_pr_tool...")
    try:
        result = call_analyze_pr_tool(pr_diff)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Failed to call tool: {e}")