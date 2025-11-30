"""CLI app for hello-fancy."""

import typer
from hello_py import hello

app = typer.Typer()


@app.command()
def main(name: str) -> None:
    """
    Greet someone in a fancy way!

    Args:
        name: The name of the person to greet
    """
    # Get the greeting from the Rust-backed hello_py library
    greeting = hello(name)

    # Make it fancy: capitalize the name and add exclamation
    parts = greeting.split()
    if len(parts) >= 2:
        fancy_greeting = f"{parts[0].capitalize()} {parts[1].capitalize()}!"
        typer.echo(fancy_greeting)
    else:
        typer.echo(greeting)


if __name__ == "__main__":
    app()
