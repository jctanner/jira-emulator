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
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    # import command (stub for Phase 3)
    import_parser = subparsers.add_parser("import", help="Import issues from JSON")
    import_parser.add_argument("path", help="Path to JSON file or directory")

    # import-config command
    config_parser = subparsers.add_parser("import-config", help="Import v1.0 project configuration")
    config_parser.add_argument("path", help="Path to v1.0 project config JSON file")

    args = parser.parse_args()

    if args.command == "serve":
        _run_server(args)
    elif args.command == "import":
        _run_import(args)
    elif args.command == "import-config":
        _run_import_config(args)
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

    from jira_emulator.database import get_session_factory, init_db
    from jira_emulator.services.import_service import import_directory, import_file

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
    print("Import complete:")
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


def _run_import_config(args):
    """Import a v1.0 project configuration file."""
    import asyncio
    import json

    from jira_emulator.database import get_session_factory, init_db
    from jira_emulator.services.config_import_service import import_project_config

    path = args.path
    if not os.path.isfile(path):
        print(f"Error: {path} is not a file", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        config = json.load(f)

    version = config.get("version")
    if version != "1.0":
        print(f"Error: unsupported config version: {version!r} (expected '1.0')", file=sys.stderr)
        sys.exit(1)

    async def _do_import():
        import jira_emulator.models  # noqa: F401

        await init_db()
        factory = get_session_factory()
        async with factory() as db:
            return await import_project_config(db, config)

    result = asyncio.run(_do_import())
    print("Config import complete:")
    print(f"  Statuses:      {result.statuses}")
    print(f"  Issue types:   {result.issue_types}")
    print(f"  Priorities:    {result.priorities}")
    print(f"  Resolutions:   {result.resolutions}")
    print(f"  Link types:    {result.link_types}")
    print(f"  Custom fields: {result.custom_fields}")
    print(f"  Workflows:     {result.workflows}")
    print(f"  Projects:      {result.projects}")
    if result.errors:
        print(f"  Errors: {len(result.errors)}")
        for err in result.errors[:20]:
            print(f"    - {err}")


if __name__ == "__main__":
    main()
