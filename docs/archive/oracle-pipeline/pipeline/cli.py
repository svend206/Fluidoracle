"""
Oracle Pipeline CLI
Usage:
    python -m pipeline run --vertical hydraulic-filters --phase 1
    python -m pipeline init --vertical hydraulic-filters
    python -m pipeline status --vertical hydraulic-filters
"""

import click
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from .db import init_db, get_connection


@click.group()
def cli():
    """Oracle Pipeline — industrial domain knowledge collection system."""
    pass


@cli.command()
def bootstrap():
    """Initialize oracle.db and seed all reference data."""
    from .bootstrap import bootstrap_all
    bootstrap_all()


@cli.command()
@click.option("--vertical", required=True, help="Vertical identifier (e.g. hydraulic-filters)")
def init(vertical: str):
    """(Legacy) Initialize databases for a vertical. Use bootstrap instead."""
    init_db()
    click.echo(f"Initialized oracle.db")


@cli.command()
@click.option("--vertical", required=True)
@click.option("--phase", required=True, type=int, help="Phase number 1-6")
@click.option("--force", is_flag=True, default=False,
              help="Re-collect already-seen sources")
def run(vertical: str, phase: int, force: bool):
    """Run a pipeline phase for a vertical."""
    if phase == 1:
        from .phases.phase1_standards import Phase1Runner
        runner = Phase1Runner(vertical, force=force)
        runner.run()
    elif phase == 2:
        from .phases.phase2_fetch import Phase2Runner
        runner = Phase2Runner(vertical, force=force)
        result = runner.run()
        click.echo(f"\nPhase 2 complete: {result['fetched']} fetched, "
                   f"{result['skipped']} skipped, {result['failed']} failed")
        if result['failed_urls']:
            click.echo("\nFailed URLs (likely paywalled or binary):")
            for url in result['failed_urls']:
                click.echo(f"  {url}")
    else:
        click.echo(f"Phase {phase} not yet implemented.")


@cli.command()
@click.option("--vertical", default=None, help="Filter by vertical")
def status(vertical):
    """Show collection status."""
    try:
        with get_connection() as conn:
            fluids = conn.execute("SELECT COUNT(*) FROM fluids").fetchone()[0]
            artifacts = conn.execute("SELECT COUNT(*) FROM knowledge_artifacts").fetchone()[0]
            fetched   = conn.execute("SELECT COUNT(*) FROM knowledge_artifacts WHERE raw_snapshot_path IS NOT NULL").fetchone()[0]
            standards = conn.execute("SELECT COUNT(*) FROM standards").fetchone()[0]
            products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            click.echo(f"oracle.db — fluids: {fluids} | artifacts: {artifacts} ({fetched} fetched) | standards: {standards} | products: {products}")

            if vertical:
                for phase in range(1, 7):
                    count = conn.execute(
                        "SELECT COUNT(*) FROM knowledge_artifacts WHERE collection_phase = ?",
                        (phase,)
                    ).fetchone()[0]
                    if count > 0:
                        click.echo(f"  Phase {phase}: {count} artifacts")

            runs = conn.execute(
                """SELECT vertical_id, phase, status, started_at, artifacts_collected
                   FROM pipeline_runs ORDER BY id DESC LIMIT 5"""
            ).fetchall()
            if runs:
                click.echo("\nRecent runs:")
                for r in runs:
                    click.echo(f"  [{r['vertical_id']}] Phase {r['phase']} — "
                               f"{r['status']} at {r['started_at']} "
                               f"({r['artifacts_collected']} artifacts)")
    except Exception as e:
        click.echo(f"DB error: {e}")


def main():
    cli()


if __name__ == "__main__":
    main()
