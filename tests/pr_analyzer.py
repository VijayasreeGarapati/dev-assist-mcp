#!/usr/bin/env python3
"""Test Step 1: Error Handling"""

import sys
sys.path.append('app')

from app.tools.analyse_pr import analyze_pr

def test_invalid_inputs():
    """Test various invalid inputs"""
    
    test_cases = [
        ("", "Empty input"),
        ("   \n  \n  ", "Whitespace only"),
        ("not a real diff", "Invalid format"),
        ("x" * 60000, "Too large input")
    ]
    
    print("🧪 Testing invalid inputs...")
    
    for test_input, description in test_cases:
        print(f"\nTesting: {description}")
        try:
            result = analyze_pr(test_input)
            print(f"✅ Handled gracefully: {result.summary}")
            print(f"   Risk score: {result.risk_score}")
            print(f"   Issues: {len(result.notable_issues)}")
        except Exception as e:
            print(f"❌ Failed: {e}")

def test_valid_input():
    """Test with valid input"""
    
    valid_diff = r"""diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,5 @@
 def test():
     pass
+# TODO: implement this
+# FIXME: security issue here"""
    
    print("\n🧪 Testing valid input...")
    try:
        result = analyze_pr(valid_diff)
        print(f"✅ Analysis successful: {result.summary}")
        print(f"   Risk score: {result.risk_score}")
        print(f"   Issues found: {len(result.notable_issues)}")
        print(f"   LLM used: {result.analysis_metadata.get('llm_metadata', {}).get('llm_used', 'None')}")
        print(f"   LLM success: {result.analysis_metadata.get('llm_metadata', {}).get('llm_success', 'Unknown')}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_invalid_inputs()
    test_valid_input()
    print("\n🎉 Step 1 testing complete!")