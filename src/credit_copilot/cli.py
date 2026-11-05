import argparse
import json
import os
from dotenv import load_dotenv


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Initialize or evaluate Credit Analyst Copilot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-demo")
    sub.add_parser("connect-risk-desk")
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--output", default="reports/evaluation.json")
    args = parser.parse_args()
    if args.command == "evaluate":
        from .evaluation import evaluate
        result = evaluate(args.output)
    else:
        from .bootstrap import initialize
        admin = os.getenv("COPILOT_ADMIN_URL")
        password = os.getenv("COPILOT_READER_PASSWORD")
        if not admin or not password:
            parser.error("Set COPILOT_ADMIN_URL and COPILOT_READER_PASSWORD for initialization only.")
        result = initialize(admin, password, adapter=args.command == "connect-risk-desk")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
