"""Nimbus Home support agent entrypoint (scaffold)."""

from __future__ import annotations

import argparse

from src.utils.config import get_app_config, get_model_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Nimbus Home AI Support Agent")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run end-to-end demo (wired in later phases)",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print loaded app/model config (Phase 0 smoke check)",
    )
    args = parser.parse_args()

    if args.show_config:
        app = get_app_config()
        models = get_model_config()
        print(f"App: {app['app']['name']} ({app['app']['brand']})")
        print(f"Domain: {app['app']['domain']}")
        print(f"Chat: {models['chat']['provider']} / {models['chat']['model']}")
        print(
            f"Embeddings: {models['embeddings']['provider']} / "
            f"{models['embeddings']['model']} "
            f"({models['embeddings']['dimensions']} dims)"
        )
        return

    if args.demo:
        print("Demo pipeline not implemented yet — complete Phases 1–8.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
