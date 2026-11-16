"""Read-only MT5 connection diagnostic."""
import argparse
import json
from .mt5_adapter import MT5Adapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="mt5_openai/config.json")
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as fh:
        config = json.load(fh)
    adapter = MT5Adapter(config.get("terminal_path"))
    try:
        account = adapter.connect()
        print(json.dumps({
            "connected": True,
            "login": int(account.login),
            "server": str(account.server),
            "currency": str(account.currency),
            "balance": float(account.balance),
            "equity": float(account.equity),
            "trade_allowed": bool(account.trade_allowed),
            "execution_mode": config.get("execution_mode", "paper")
        }, indent=2))
    finally:
        adapter.shutdown()


if __name__ == "__main__":
    main()
