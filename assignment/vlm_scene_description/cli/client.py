"""HTTP client commands — talk to a running API instance.

Demonstrates a full CRUD CLI client pattern (like curl, but typed and colored).

Usage (with the API running on the default port)::

    vlm_scene_description client list
    vlm_scene_description client create widget-1 "First Widget" --desc "Optional"
    vlm_scene_description client get widget-1
    vlm_scene_description client update widget-1 --name "Renamed Widget"
    vlm_scene_description client delete widget-1
    vlm_scene_description client health
"""
import http
from typing import Annotated, Any
from urllib.parse import urljoin

import typer

from vlm_scene_description.cli import _DEFAULT_API_URL, client_app

_TIMEOUT = 10.0


def _on_error(exc: Exception) -> None:
    typer.secho(f"Connection error: {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _on_api_error(response: Any) -> None:
    error = response.json().get("error", {})
    typer.secho(
        f"Error {response.status_code}: {error.get('message', response.text)}",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(1)


@client_app.command("list")
def items_list(
    page: Annotated[int, typer.Option("--page", "-p", min=1, help="Page number")] = 1,
    page_size: Annotated[
        int, typer.Option("--size", "-s", min=1, max=100, help="Items per page")
    ] = 20,
    api_url: Annotated[
        str, typer.Option(envvar="API_URL", help="API base URL")
    ] = _DEFAULT_API_URL,
) -> None:
    """List items with optional pagination."""
    import httpx

    try:
        resp = httpx.get(
            urljoin(api_url, "/items/"),
            params={"page": page, "page_size": page_size},
            timeout=_TIMEOUT,
        )
    except httpx.RequestError as exc:
        _on_error(exc)
        return
    if resp.status_code != http.HTTPStatus.OK:
        _on_api_error(resp)
        return
    data = resp.json()
    items = data["items"]
    if not items:
        typer.secho("(no items)", fg=typer.colors.BRIGHT_BLACK)
        return
    for item in items:
        suffix = f"  — {item['description']}" if item.get("description") else ""
        typer.echo(f"  {item['id']}: {item['name']}{suffix}")
    typer.secho(f"  Total: {data['total']}", fg=typer.colors.BRIGHT_BLACK)


@client_app.command("get")
def items_get(
    item_id: Annotated[str, typer.Argument(help="ID of the item to fetch")],
    api_url: Annotated[
        str, typer.Option(envvar="API_URL", help="API base URL")
    ] = _DEFAULT_API_URL,
) -> None:
    """Fetch a single item by ID."""
    import httpx

    try:
        resp = httpx.get(urljoin(api_url, f"/items/{item_id}"), timeout=_TIMEOUT)
    except httpx.RequestError as exc:
        _on_error(exc)
        return
    if resp.status_code != http.HTTPStatus.OK:
        _on_api_error(resp)
        return
    item = resp.json()
    typer.echo(f"id:          {item['id']}")
    typer.echo(f"name:        {item['name']}")
    typer.echo(f"description: {item.get('description') or '(none)'}")


@client_app.command("create")
def items_create(
    item_id: Annotated[str, typer.Argument(help="Unique item ID")],
    name: Annotated[str, typer.Argument(help="Item display name")],
    description: Annotated[
        str | None, typer.Option("--desc", "-d", help="Optional description")
    ] = None,
    api_url: Annotated[
        str, typer.Option(envvar="API_URL", help="API base URL")
    ] = _DEFAULT_API_URL,
) -> None:
    """Create a new item."""
    import httpx

    payload: dict[str, str] = {"id": item_id, "name": name}
    if description:
        payload["description"] = description
    try:
        resp = httpx.post(urljoin(api_url, "/items/"), json=payload, timeout=_TIMEOUT)
    except httpx.RequestError as exc:
        _on_error(exc)
        return
    if resp.status_code != http.HTTPStatus.CREATED:
        _on_api_error(resp)
        return
    item = resp.json()
    typer.secho(f"Created: {item['id']} — {item['name']}", fg=typer.colors.GREEN)


@client_app.command("update")
def items_update(
    item_id: Annotated[str, typer.Argument(help="ID of the item to update")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="New name")] = None,
    description: Annotated[
        str | None, typer.Option("--desc", "-d", help="New description")
    ] = None,
    api_url: Annotated[
        str, typer.Option(envvar="API_URL", help="API base URL")
    ] = _DEFAULT_API_URL,
) -> None:
    """Partially update an item. Only supplied fields are changed."""
    if name is None and description is None:
        typer.secho("Provide at least --name or --desc", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(1)
    import httpx

    patch: dict[str, str] = {}
    if name:
        patch["name"] = name
    if description:
        patch["description"] = description
    try:
        resp = httpx.patch(urljoin(api_url, f"/items/{item_id}"), json=patch, timeout=_TIMEOUT)
    except httpx.RequestError as exc:
        _on_error(exc)
        return
    if resp.status_code != http.HTTPStatus.OK:
        _on_api_error(resp)
        return
    item = resp.json()
    typer.secho(f"Updated: {item['id']} — {item['name']}", fg=typer.colors.GREEN)


@client_app.command("delete")
def items_delete(
    item_id: Annotated[str, typer.Argument(help="ID of the item to delete")],
    api_url: Annotated[
        str, typer.Option(envvar="API_URL", help="API base URL")
    ] = _DEFAULT_API_URL,
) -> None:
    """Delete an item permanently."""
    import httpx

    try:
        resp = httpx.delete(urljoin(api_url, f"/items/{item_id}"), timeout=_TIMEOUT)
    except httpx.RequestError as exc:
        _on_error(exc)
        return
    if resp.status_code != http.HTTPStatus.NO_CONTENT:
        _on_api_error(resp)
        return
    typer.secho(f"Deleted: {item_id}", fg=typer.colors.GREEN)


@client_app.command()
def health(
    api_url: Annotated[
        str, typer.Option(envvar="API_URL", help="API base URL")
    ] = _DEFAULT_API_URL,
) -> None:
    """Check whether the API is reachable and healthy."""
    import httpx

    try:
        resp = httpx.get(urljoin(api_url, "/health"), timeout=5.0)
    except httpx.RequestError as exc:
        typer.secho(f"Unreachable: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    if resp.status_code == http.HTTPStatus.OK:
        typer.secho("healthy", fg=typer.colors.GREEN)
    else:
        typer.secho(f"unhealthy ({resp.status_code})", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
