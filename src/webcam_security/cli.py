"""Command-line interface for webcam security."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from pathlib import Path
import sys

from .config import Config
from .core import SecurityMonitor

app = typer.Typer(
    name="webcam-security",
    help="A webcam security monitoring system with Telegram notifications",
    add_completion=False,
)
console = Console()


@app.command()
def init(
    bot_token: str = typer.Option(..., "--bot-token", "-t", help="Telegram bot token"),
    chat_id: str = typer.Option(..., "--chat-id", "-c", help="Telegram chat ID"),
    topic_id: str = typer.Option(
        None, "--topic-id", help="Telegram topic ID (optional)"
    ),
) -> None:
    """Initialize the webcam security configuration."""
    try:
        config = Config(
            bot_token=bot_token,
            chat_id=chat_id,
            topic_id=topic_id,
        )
        config.save()

        console.print(
            Panel(
                Text("✅ Configuration saved successfully!", style="green"),
                title="[bold blue]Webcam Security[/bold blue]",
                border_style="green",
            )
        )

        console.print(
            f"\n[bold]Configuration saved to:[/bold] {config._get_config_path()}"
        )
        console.print("\n[bold]Next steps:[/bold]")
        console.print(
            "1. Run [bold green]webcam-security start[/bold green] to begin monitoring"
        )
        console.print("2. Press 'q' in the preview window to stop monitoring")

    except Exception as e:
        console.print(f"[red]Error saving configuration: {e}[/red]")
        sys.exit(1)


@app.command()
def start() -> None:
    """Start the security monitoring."""
    try:
        config = Config.load()

        if not config.is_configured():
            console.print(
                "[red]Configuration is incomplete. Please run 'webcam-security init' first.[/red]"
            )
            sys.exit(1)

        console.print(
            Panel(
                Text("🚀 Starting security monitoring...", style="green"),
                title="[bold blue]Webcam Security[/bold blue]",
                border_style="blue",
            )
        )

        console.print("\n[bold]Monitoring Configuration:[/bold]")
        console.print(
            f"• Monitoring hours: {config.monitoring_start_hour}:00 - {config.monitoring_end_hour}:00"
        )
        console.print(f"• Grace period: {config.grace_period} seconds")
        console.print(f"• Cleanup: {config.cleanup_days} days")
        console.print(f"• Chat ID: {config.chat_id}")
        if config.topic_id:
            console.print(f"• Topic ID: {config.topic_id}")

        console.print("\n[bold]Controls:[/bold]")
        console.print("• Press 'q' in the preview window to stop monitoring")
        console.print("• Press Ctrl+C in terminal to stop monitoring")

        monitor = SecurityMonitor(config)
        monitor.start()

    except FileNotFoundError:
        console.print(
            "[red]Configuration not found. Please run 'webcam-security init' first.[/red]"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitoring stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error starting monitoring: {e}[/red]")
        sys.exit(1)


@app.command()
def stop() -> None:
    """Stop the security monitoring (if running)."""
    console.print("[yellow]Note: This command is mainly for documentation.[/yellow]")
    console.print(
        "[yellow]To stop monitoring, press 'q' in the preview window or Ctrl+C in terminal.[/yellow]"
    )


@app.command()
def status() -> None:
    """Show current configuration status."""
    try:
        config = Config.load()

        console.print(
            Panel(
                Text("📊 Configuration Status", style="blue"),
                title="[bold blue]Webcam Security[/bold blue]",
                border_style="blue",
            )
        )

        console.print(f"\n[bold]Configuration file:[/bold] {config._get_config_path()}")
        console.print(
            f"[bold]Bot token:[/bold] {'✅ Set' if config.bot_token else '❌ Not set'}"
        )
        console.print(
            f"[bold]Chat ID:[/bold] {'✅ Set' if config.chat_id else '❌ Not set'}"
        )
        console.print(
            f"[bold]Topic ID:[/bold] {'✅ Set' if config.topic_id else '❌ Not set'}"
        )
        console.print(
            f"[bold]Monitoring hours:[/bold] {config.monitoring_start_hour}:00 - {config.monitoring_end_hour}:00"
        )
        console.print(f"[bold]Grace period:[/bold] {config.grace_period} seconds")
        console.print(f"[bold]Cleanup days:[/bold] {config.cleanup_days}")

        if config.is_configured():
            console.print(
                "\n[green]✅ Configuration is valid and ready to use![/green]"
            )
        else:
            console.print(
                "\n[red]❌ Configuration is incomplete. Please run 'webcam-security init'.[/red]"
            )

    except FileNotFoundError:
        console.print(
            "[red]Configuration not found. Please run 'webcam-security init' first.[/red]"
        )
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error reading configuration: {e}[/red]")
        sys.exit(1)


@app.command()
def clean() -> None:
    """Manually clean old recording files."""
    try:
        config = Config.load()
        monitor = SecurityMonitor(config)

        console.print("[yellow]Cleaning old recording files...[/yellow]")
        monitor.clean_old_files()
        console.print("[green]✅ Cleanup completed![/green]")

    except FileNotFoundError:
        console.print(
            "[red]Configuration not found. Please run 'webcam-security init' first.[/red]"
        )
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error during cleanup: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    app()
