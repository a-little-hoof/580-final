"""Private bounded regex matching subprocess; never installed in the agent VM."""
import json
import re
import sys

if __name__ == "__main__":
    request = json.load(sys.stdin)
    compiled = re.compile(request["pattern"])
    examples = request["examples"]
    right = sum((compiled.fullmatch(example["text"]) is not None) == example["matches"] for example in examples)
    print(json.dumps({"right": right, "total": len(examples)}))
