"""CLI entry point for recipebrain.

Subcommands mirror the planned tool surface in docs/05-mcp-tools.md.
"""

from __future__ import annotations

import argparse

from recipebrain import __version__


def _stub(name: str) -> int:
    print(f"recipebrain {name}: not yet implemented — see docs/06-architecture.md build phasing")
    return 0


def _cmd_etl(args: argparse.Namespace) -> int:
    from recipebrain.etl import run_etl
    from recipebrain.settings import Settings

    settings = Settings.load(args.config)
    results = run_etl(settings, source_filter=args.source, limit=args.limit)

    if not results:
        print("No sources processed.")
        return 0

    for r in results:
        print(
            f"  {r.source}: discovered={r.discovered} fetched={r.fetched} "
            f"skipped={r.skipped} errors={r.errors}"
        )
        for detail in r.error_details:
            print(f"    ! {detail}")

    total_errors = sum(r.errors for r in results)
    return 1 if total_errors > 0 and all(r.fetched == 0 for r in results) else 0


def _cmd_promotions_refresh(args: argparse.Namespace) -> int:
    return _stub("promotions refresh")


def _cmd_ingest(args: argparse.Namespace) -> int:
    return _stub("ingest")


def _cmd_validate(args: argparse.Namespace) -> int:
    from pathlib import Path

    from recipebrain.settings import Settings
    from recipebrain.validate import validate

    settings = Settings.load(args.config)
    output_dir = Path(settings.paths.output_dir)
    result = validate(output_dir)

    if result.ok:
        print(f"All checks passed ({result.checks_run} checks).")
        return 0

    print(f"Validation found {len(result.issues)} issue(s) ({result.checks_run} checks):")
    for issue in result.issues:
        print(f"  ! {issue}")
    return 1


def _cmd_mcp(args: argparse.Namespace) -> int:
    import os
    from pathlib import Path

    from recipebrain.settings import Settings

    # Resolve paths to absolute before starting MCP server — the server
    # may be launched by an external client with a different CWD.
    settings = Settings.load(args.config)
    os.environ["RECIPEBRAIN_OUTPUT_DIR"] = str(Path(settings.paths.output_dir).resolve())
    if args.config:
        os.environ["RECIPEBRAIN_CONFIG"] = str(Path(args.config).resolve())

    from recipebrain.mcp_server import run

    return run()


def _cmd_reindex(args: argparse.Namespace) -> int:
    return _stub("reindex")


def _cmd_doctor(args: argparse.Namespace) -> int:
    from pathlib import Path

    from recipebrain.doctor import Severity, run_doctor
    from recipebrain.settings import Settings

    settings = Settings.load(args.config)
    report = run_doctor(
        output_dir=Path(settings.paths.output_dir),
        snapshot_dir=Path(settings.paths.snapshot_dir),
        dossier_dir=Path(settings.paths.dossier_dir),
    )

    icons = {Severity.OK: "✓", Severity.WARN: "!", Severity.ERROR: "✗"}
    for check in report.checks:
        icon = icons[check.severity]
        print(f"  {icon} {check.name}: {check.message}")

    if report.ok:
        print("\nAll checks passed.")
        return 0
    print(f"\n{report.worst.value.upper()}: some checks need attention.")
    return 1 if report.worst == Severity.ERROR else 0


def _cmd_info(args: argparse.Namespace) -> int:
    from pathlib import Path

    from recipebrain.info import format_info, gather_info
    from recipebrain.settings import Settings

    settings = Settings.load(args.config)
    report = gather_info(Path(settings.paths.output_dir))
    print(format_info(report))
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    from pathlib import Path

    from recipebrain.settings import Settings
    from recipebrain.snapshot import create_snapshot, list_snapshots, restore_snapshot

    settings = Settings.load(args.config)
    output_dir = Path(settings.paths.output_dir)
    snapshot_dir = Path(settings.paths.snapshot_dir)

    action = getattr(args, "snapshot_action", None) or "create"

    if action == "list":
        snaps = list_snapshots(snapshot_dir)
        if not snaps:
            print("No snapshots found.")
            return 0
        for s in snaps:
            print(f"  {s['name']}  ({s['file_count']} files)")
        return 0

    if action == "restore":
        name = args.name
        snap_path = snapshot_dir / name
        try:
            count = restore_snapshot(snap_path, output_dir)
            print(f"Restored {count} file(s) from snapshot '{name}'.")
            return 0
        except FileNotFoundError as exc:
            print(f"Error: {exc}")
            return 1

    # Default: create
    label = getattr(args, "label", None)
    result = create_snapshot(output_dir, snapshot_dir, label=label)
    if result is None:
        print("Nothing to snapshot (no parquet files found).")
        return 0
    print(f"Snapshot created: {result.name}")
    return 0


def _cmd_install_skills(args: argparse.Namespace) -> int:
    from pathlib import Path

    from recipebrain.install_skills import install

    target = Path(args.target) if args.target else None
    count = install(target=target, force=args.force)
    if count < 0:
        return 1
    print(f"Installed {count} skill file(s).")
    return 0


def _cmd_log(args: argparse.Namespace) -> int:
    from recipebrain.mcp_server import log_cook

    result = log_cook(
        recipe_id=args.recipe_id,
        rating=args.rating,
        notes=args.notes,
        servings=args.servings,
        scale_factor=args.scale_factor,
    )
    print(result)
    return 1 if result.startswith("Error") else 0


def _cmd_dashboard(args: argparse.Namespace) -> int:
    from recipebrain.dashboard import run_dashboard

    host = args.host
    port = args.port
    print(f"Starting dashboard at http://{host}:{port}")
    run_dashboard(host=host, port=port)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="recipebrain",
        description="Personal Swiss recipe knowledge base with promotion-aware meal planning.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        "-c",
        default="recipebrain.toml",
        help="Path to config file (default: recipebrain.toml)",
    )

    subparsers = parser.add_subparsers(dest="command")

    # etl
    sp_etl = subparsers.add_parser("etl", help="Run ETL pipeline for recipe sources")
    sp_etl.add_argument("--source", "-s", help="Specific source to scrape (default: all enabled)")
    sp_etl.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Max new recipes to fetch per source (default: unlimited)",
    )
    sp_etl.set_defaults(func=_cmd_etl)

    # promotions
    sp_promo = subparsers.add_parser("promotions", help="Manage promotion data")
    promo_sub = sp_promo.add_subparsers(dest="promotions_command")
    sp_promo_refresh = promo_sub.add_parser("refresh", help="Refresh promotion data")
    sp_promo_refresh.set_defaults(func=_cmd_promotions_refresh)
    sp_promo.set_defaults(func=_cmd_promotions_refresh)

    # ingest
    sp_ingest = subparsers.add_parser("ingest", help="Ingest a recipe from file or URL")
    sp_ingest.add_argument("target", help="File path or URL to ingest")
    sp_ingest.set_defaults(func=_cmd_ingest)

    # validate
    sp_validate = subparsers.add_parser("validate", help="Validate data integrity")
    sp_validate.set_defaults(func=_cmd_validate)

    # mcp
    sp_mcp = subparsers.add_parser("mcp", help="Start MCP server")
    sp_mcp.set_defaults(func=_cmd_mcp)

    # reindex
    sp_reindex = subparsers.add_parser("reindex", help="Rebuild search indexes")
    sp_reindex.set_defaults(func=_cmd_reindex)

    # doctor
    sp_doctor = subparsers.add_parser("doctor", help="Run health checks on data and config")
    sp_doctor.set_defaults(func=_cmd_doctor)

    # info
    sp_info = subparsers.add_parser("info", help="Show version, environment, and data summary")
    sp_info.set_defaults(func=_cmd_info)

    # snapshot
    sp_snapshot = subparsers.add_parser("snapshot", help="Create or manage data snapshots")
    snap_sub = sp_snapshot.add_subparsers(dest="snapshot_action")
    sp_snap_create = snap_sub.add_parser("create", help="Create a new snapshot")
    sp_snap_create.add_argument("--label", "-l", default=None, help="Label for the snapshot")
    snap_sub.add_parser("list", help="List available snapshots")
    sp_snap_restore = snap_sub.add_parser("restore", help="Restore a snapshot")
    sp_snap_restore.add_argument("name", help="Snapshot name to restore")
    sp_snapshot.set_defaults(func=_cmd_snapshot)

    # install-skills
    sp_skills = subparsers.add_parser("install-skills", help="Install OpenClaw skills")
    sp_skills.add_argument(
        "--target",
        "-t",
        default=None,
        help="Target directory (default: ~/.openclaw/skills/recipebrain/)",
    )
    sp_skills.add_argument("--force", action="store_true", help="Overwrite existing skill files")
    sp_skills.set_defaults(func=_cmd_install_skills)

    # log
    sp_log = subparsers.add_parser("log", help="Log a cook event for a recipe")
    sp_log.add_argument("recipe_id", type=int, help="ID of the recipe cooked")
    sp_log.add_argument("--rating", "-r", type=int, default=None, help="Rating 1-5")
    sp_log.add_argument("--notes", "-n", default=None, help="Free-form notes")
    sp_log.add_argument("--servings", "-s", type=int, default=None, help="Number of servings made")
    sp_log.add_argument(
        "--scale-factor", type=float, default=None, help="Scale multiplier (e.g. 2.0 for doubled)"
    )
    sp_log.set_defaults(func=_cmd_log)

    # dashboard
    sp_dash = subparsers.add_parser("dashboard", help="Start observability dashboard")
    sp_dash.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    sp_dash.add_argument("--port", "-p", type=int, default=8777, help="Bind port (default: 8777)")
    sp_dash.set_defaults(func=_cmd_dashboard)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Initialise structured logging before running any command
    from recipebrain.log import setup_logging

    setup_logging()

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
