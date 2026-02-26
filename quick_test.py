"""Quick test: send one query and print the full result."""
import sys
sys.path.insert(0, r"c:\Hold On Projects\P2")

# Force fresh import
for mod in list(sys.modules.keys()):
    if mod in ("ai_automator", "config", "storage"):
        del sys.modules[mod]

from ai_automator import GoogleAIModeAutomator
import json, time

auto = GoogleAIModeAutomator()
print("=== Sending query ===")
result = auto.send_and_get_response("What is Jira")
print("\n=== RESULT ===")
print(json.dumps(result, indent=2, ensure_ascii=False))
auto.close()
