"""CLI entry point for the Jira Emulator."""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="jira-emulator",
        description="Jira REST API v2 Emulator",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start the HTTP server")
    serve_parser.add_argument("--host", default=None, help="Listen address")
    serve_parser.add_argument("--port", type=int, default=None, help="Listen port")
    serve_parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )

    # import command (stub for Phase 3)
    import_parser = subparsers.add_parser("import", help="Import issues from JSON")
    import_parser.add_argument("path", help="Path to JSON file or directory")

    args = parser.parse_args()

    if args.command == "serve":
        _run_server(args)
    elif args.command == "import":
        _run_import(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_server(args):
    import uvicorn
    from jira_emulator.config import get_settings

    settings = get_settings()
    host = args.host or settings.HOST
    port = args.port or settings.PORT

    uvicorn.run(
        "jira_emulator.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=args.reload,
    )


def _run_import(args):
    """Import issues from a JSON file or directory."""
    import asyncio
    from jira_emulator.database import init_db, get_session_factory, reset_engine
    from jira_emulator.services.import_service import import_file, import_directory

    async def _do_import():
        # Import models so tables are known
        import jira_emulator.models  # noqa: F401

        await init_db()
        factory = get_session_factory()
        async with factory() as db:
            path = args.path
            if os.path.isdir(path):
                result = await import_directory(db, path)
            else:
                result = await import_file(db, path)
            await db.commit()
        return result

    result = asyncio.run(_do_import())
    print(f"Import complete:")
    print(f"  Imported: {result.imported}")
    print(f"  Updated:  {result.updated}")
    if result.projects_created:
        print(f"  Projects created: {', '.join(result.projects_created)}")
    if result.users_created:
        print(f"  Users created: {', '.join(result.users_created)}")
    if result.errors:
        print(f"  Errors: {len(result.errors)}")
        for err in result.errors[:10]:
            print(f"    - {err}")


if __name__ == "__main__":
    main()
