"""Command-line interface for Grail Hunter."""

import asyncio
import signal
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live

from grail_hunter import __version__
from grail_hunter.brands import BrandClassifier, TIER_1_GRAILS, ALL_BRANDS
from grail_hunter.database import init_db
from grail_hunter.scrapers import SellpyScraper

app = typer.Typer(
    name="grail-hunter",
    help="Designer thrift scraper for Sellpy - find grails efficiently",
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"[bold blue]Grail Hunter[/bold blue] v{__version__}")


@app.command()
def brands(
    tier: Optional[str] = typer.Option(None, "--tier", "-t", help="Filter by tier"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
) -> None:
    """List all tracked brands."""
    classifier = BrandClassifier()

    table = Table(title="Tracked Brands", show_header=True)
    table.add_column("Brand", style="cyan")
    table.add_column("Category", style="magenta")
    table.add_column("Tier", style="green")

    for brand in sorted(ALL_BRANDS):
        match = classifier.classify(brand)

        # Apply filters
        if tier and match.tier.value != tier:
            continue
        if category and match.category.value != category:
            continue

        tier_style = "bold red" if match.tier.value == "TIER_1" else "yellow"
        table.add_row(
            brand,
            match.category.value,
            f"[{tier_style}]{match.tier.value}[/{tier_style}]",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(ALL_BRANDS)} brands tracked[/dim]")


@app.command()
def grails() -> None:
    """List Tier 1 grail brands."""
    console.print(Panel("[bold red]🏆 TIER 1 GRAILS[/bold red]", expand=False))

    for brand in TIER_1_GRAILS:
        console.print(f"  • {brand}")

    console.print(f"\n[dim]These brands trigger instant alerts![/dim]")


@app.command()
def hunt(
    category: str = typer.Option("Miehet", "--category", "-c", help="Category to search"),
    pages: int = typer.Option(3, "--pages", "-p", help="Number of pages to fetch"),
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all items, not just grails"),
) -> None:
    """Hunt for grails on Sellpy."""

    async def _hunt() -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Initializing database...", total=None)
            await init_db()

            progress.add_task(description="Fetching from Sellpy...", total=None)

            async with SellpyScraper() as scraper:
                if show_all:
                    items = await scraper.fetch_all_pages(
                        category=category,
                        max_pages=pages,
                    )
                else:
                    items = await scraper.hunt_grails(category=category)

        # Filter to tracked brands if not showing all
        if not show_all:
            items = [i for i in items if i.brand_tier in ("TIER_1", "TIER_2")]

        if not items:
            console.print("[yellow]No grails found in this search.[/yellow]")
            return

        # Display results
        table = Table(title=f"🦅 Hunt Results ({len(items)} items)", show_header=True)
        table.add_column("Brand", style="cyan", width=20)
        table.add_column("Title", style="white", width=35)
        table.add_column("Price", style="green", justify="right")
        table.add_column("Score", style="magenta", justify="right")
        table.add_column("Tier", style="yellow")

        for item in items[:50]:  # Show top 50
            tier_display = "🏆" if item.brand_tier == "TIER_1" else "⚡"
            price_display = f"€{item.price:.0f}"
            if item.discount_pct:
                price_display += f" (-{item.discount_pct}%)"

            table.add_row(
                item.brand or "Unknown",
                item.title[:35] + "..." if len(item.title) > 35 else item.title,
                price_display,
                str(item.item_score),
                tier_display,
            )

        console.print(table)

        # Show grail alert if found
        grail_count = sum(1 for i in items if i.brand_tier == "TIER_1")
        if grail_count > 0:
            console.print(
                Panel(
                    f"[bold red]🚨 {grail_count} GRAIL(S) FOUND![/bold red]\n"
                    "Check the list above for Tier 1 items!",
                    title="GRAIL ALERT",
                    border_style="red",
                )
            )

    asyncio.run(_hunt())


@app.command()
def search(
    brand: str = typer.Argument(..., help="Brand name to search for"),
    category: str = typer.Option("Miehet", "--category", "-c", help="Category to search"),
) -> None:
    """Search for a specific brand."""

    async def _search() -> None:
        console.print(f"[bold]Searching for:[/bold] {brand}")

        async with SellpyScraper() as scraper:
            items = await scraper.search_brand(brand, category)

        if not items:
            console.print(f"[yellow]No items found for '{brand}'[/yellow]")
            return

        table = Table(title=f"Results for {brand}", show_header=True)
        table.add_column("Title", style="white", width=40)
        table.add_column("Price", style="green", justify="right")
        table.add_column("Size", style="cyan")
        table.add_column("Condition", style="yellow")
        table.add_column("URL", style="dim")

        for item in items[:20]:
            table.add_row(
                item.title[:40],
                f"€{item.price:.0f}",
                item.size or "-",
                item.condition or "-",
                item.item_url,
            )

        console.print(table)

    asyncio.run(_search())


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
) -> None:
    """Start the FastAPI server."""
    import uvicorn

    console.print(
        Panel(
            f"[bold green]Starting Grail Hunter API[/bold green]\n"
            f"URL: http://{host}:{port}\n"
            f"Docs: http://{host}:{port}/docs",
            title="🦅 Grail Hunter",
        )
    )

    uvicorn.run(
        "grail_hunter.main:app",
        host=host,
        port=port,
        reload=reload,
    )


# =============================================================================
# Scheduler Commands
# =============================================================================

scheduler_app = typer.Typer(help="Scheduler commands for automated scanning")
app.add_typer(scheduler_app, name="scheduler")


@scheduler_app.command("start")
def scheduler_start(
    foreground: bool = typer.Option(False, "--foreground", "-f", help="Run in foreground"),
) -> None:
    """Start the automated grail scanner."""
    from grail_hunter.config import get_settings
    from grail_hunter.services.scheduler import get_scheduler

    settings = get_settings()
    scheduler = get_scheduler()

    console.print(
        Panel(
            f"[bold green]Starting Grail Hunter Scheduler[/bold green]\n\n"
            f"Scan interval: [cyan]{settings.scrape_interval_minutes}[/cyan] minutes\n"
            f"Min price: [cyan]€{settings.min_price}[/cyan]\n"
            f"Max price: [cyan]€{settings.max_price}[/cyan]\n"
            f"Notifications: [cyan]{'Enabled' if settings.telegram_bot_token else 'Disabled'}[/cyan]",
            title="🦅 Scheduler",
        )
    )

    scheduler.start()

    if foreground:
        console.print("\n[dim]Press Ctrl+C to stop...[/dim]\n")

        # Handle graceful shutdown
        def shutdown(sig, frame):
            console.print("\n[yellow]Shutting down scheduler...[/yellow]")
            scheduler.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        # Keep running
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            scheduler.stop()
    else:
        console.print("[green]Scheduler started in background.[/green]")
        console.print("[dim]Use 'grail-hunter scheduler status' to check status.[/dim]")


@scheduler_app.command("stop")
def scheduler_stop() -> None:
    """Stop the automated grail scanner."""
    from grail_hunter.services.scheduler import get_scheduler
    scheduler = get_scheduler()

    if not scheduler._running:
        console.print("[yellow]Scheduler is not running.[/yellow]")
        return

    scheduler.stop()
    console.print("[green]Scheduler stopped.[/green]")


@scheduler_app.command("status")
def scheduler_status() -> None:
    """Show scheduler status."""
    from grail_hunter.services.scheduler import get_scheduler
    scheduler = get_scheduler()
    status = scheduler.get_status()

    if status["running"]:
        status_text = "[bold green]RUNNING[/bold green]"
    else:
        status_text = "[bold red]STOPPED[/bold red]"

    table = Table(title="Scheduler Status", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("Status", status_text)
    table.add_row("Scans completed", str(status["scan_count"]))
    table.add_row("Deals found", str(status["deals_found"]))
    table.add_row("Last scan", status["last_scan"] or "Never")
    table.add_row("Next scan", status["next_scan"] or "N/A")

    console.print(table)


@scheduler_app.command("run")
def scheduler_run() -> None:
    """Run a single scan immediately."""
    from grail_hunter.services.scheduler import get_scheduler
    scheduler = get_scheduler()

    console.print("[bold]Running single scan...[/bold]\n")

    async def _run_once():
        await scheduler._run_scan()

    asyncio.run(_run_once())

    console.print("\n[green]Scan complete.[/green]")


if __name__ == "__main__":
    app()
