"""
check_gemini.py - confirm your API key works and see which model names you can use.

    python tools/check_gemini.py                      # lists models your key can use
    $env:GEMINI_MODEL="one-of-those-names"      # pick one (a 'flash' model is a good start)
    python tools/check_gemini.py                      # now also makes a tiny test call
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # lets this tool import the project modules
import llm  # noqa: E402

print("Models your key can use for text generation:\n")
try:
    for name in llm.list_models():
        print("  ", name)
except Exception as e:
    raise SystemExit(f"Could not list models: {e}")

if os.environ.get("GEMINI_MODEL"):
    print(f"\nTesting model '{os.environ['GEMINI_MODEL']}' ...")
    try:
        print("Reply:", llm.ask("Reply with the single word: ready").strip())
    except RuntimeError as e:
        print("\nThe test call failed:\n", e)
else:
    print('\nNext: pick a name from the list and run  $env:GEMINI_MODEL="name"  then run this again.')
