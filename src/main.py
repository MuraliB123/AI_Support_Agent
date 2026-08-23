"""Nimbus Home support agent entrypoint."""

from __future__ import annotations

import argparse

from src.utils.config import get_app_config, get_model_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Nimbus Home AI Support Agent")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run the API + customer chat UI on http://127.0.0.1:8000",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for --serve")
    parser.add_argument("--port", type=int, default=8000, help="Bind port for --serve")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload while developing",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print loaded app/model config",
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

    if args.serve:
        import uvicorn

        print(f"Customer chat UI: http://{args.host}:{args.port}/")
        print(f"Agent HITL UI:    http://{args.host}:{args.port}/agent")
        uvicorn.run(
            "src.api.server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
