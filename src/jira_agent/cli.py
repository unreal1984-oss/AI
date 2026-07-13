"""CLI for the Jira Data Center AI agent."""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from jira_agent import __version__
from jira_agent.agent import JiraAgent
from jira_agent.assets_client import AssetsClient
from jira_agent.config import Settings, get_settings
from jira_agent.jira_client import JiraClient
from jira_agent.llm import create_llm_client
from jira_agent.tools import ToolRegistry

app = typer.Typer(
    name="jira-agent",
    help="AI-агент Jira Data Center: задачи и Insight/Assets (DeepSeek Cloud по умолчанию).",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _load_settings() -> Settings:
    try:
        get_settings.cache_clear()
        return get_settings()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Ошибка конфигурации:[/red] {exc}")
        console.print("Скопируйте [.cyan].env.example[/cyan] → [.cyan].env[/cyan] и заполните.")
        raise typer.Exit(code=1) from exc


def _parse_projects(value: Optional[str], settings: Settings) -> list[str]:
    if value:
        return [p.strip().upper() for p in value.split(",") if p.strip()]
    return list(settings.jira_project_keys)


def _apply_insecure(settings: Settings, insecure: bool) -> None:
    if insecure:
        settings.llm_verify_ssl = False
        settings.jira_verify_ssl = False


def _ssl_label(settings: Settings) -> str:
    verify = settings.llm_http_verify()
    if verify is False:
        return "off (--insecure / LLM_VERIFY_SSL=false)"
    if isinstance(verify, str):
        return f"CA bundle: {verify}"
    return "on"


@app.command("chat")
def chat_cmd(
    projects: Optional[str] = typer.Option(
        None,
        "--projects",
        "-p",
        help="Ключи проектов через запятую, например ITSM,PROJ",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Имя модели (по умолчанию deepseek-chat)",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="deepseek | openai | ollama (переопределяет LLM_PROVIDER)",
    ),
    insecure: bool = typer.Option(
        False,
        "--insecure",
        help="Отключить проверку SSL (корпоративный MITM / self-signed)",
    ),
    show_tools: bool = typer.Option(
        False,
        "--show-tools",
        help="Показывать вызовы инструментов в чате",
    ),
) -> None:
    """Интерактивный чат с агентом."""
    settings = _load_settings()
    _apply_insecure(settings, insecure)
    if provider:
        settings.llm_provider = provider.strip().lower()
    if model:
        settings.set_active_model(model)
    project_keys = _parse_projects(projects, settings)

    console.print(
        Panel.fit(
            f"[bold]Jira DC Agent[/bold] v{__version__}\n"
            f"Jira: {settings.jira_base_url}\n"
            f"Projects: {', '.join(project_keys) or '—'}\n"
            f"Assets schema: {settings.assets_object_schema_id}\n"
            f"LLM: {settings.llm_provider} / {settings.active_model}\n"
            f"SSL verify: {_ssl_label(settings)}\n"
            f"Выход: /exit  |  сброс: /reset",
            title="chat",
        )
    )

    with (
        JiraClient(settings) as jira,
        AssetsClient(settings) as assets,
        create_llm_client(settings) as llm,
    ):
        tools = ToolRegistry(settings, jira, assets, default_project_keys=project_keys)
        agent = JiraAgent(settings, llm, tools, project_keys=project_keys)

        while True:
            try:
                user = console.input("[bold cyan]you>[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\nПока.")
                break
            if not user:
                continue
            if user in {"/exit", "/quit", "exit", "quit"}:
                break
            if user == "/reset":
                agent.reset()
                console.print("[yellow]Диалог сброшен.[/yellow]")
                continue

            def on_progress(msg: str) -> None:
                console.print(f"[dim]… {msg}[/dim]")

            try:
                result = agent.ask(user, on_progress=on_progress)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Ошибка:[/red] {exc}")
                continue

            if show_tools:
                for turn in result.turns:
                    if turn.role == "tool":
                        console.print(
                            Panel(
                                turn.content[:2000],
                                title=f"tool:{turn.tool_name}",
                                border_style="blue",
                            )
                        )
            console.print(Panel(Markdown(result.answer), title="agent", border_style="green"))


@app.command("ask")
def ask_cmd(
    question: str = typer.Argument(..., help="Вопрос агенту"),
    projects: Optional[str] = typer.Option(None, "--projects", "-p"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    provider: Optional[str] = typer.Option(None, "--provider"),
    insecure: bool = typer.Option(
        False,
        "--insecure",
        help="Отключить проверку SSL (корпоративный MITM / self-signed)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Вывести JSON с ответом"),
) -> None:
    """Один вопрос без интерактива."""
    settings = _load_settings()
    _apply_insecure(settings, insecure)
    if provider:
        settings.llm_provider = provider.strip().lower()
    if model:
        settings.set_active_model(model)
    project_keys = _parse_projects(projects, settings)

    with (
        JiraClient(settings) as jira,
        AssetsClient(settings) as assets,
        create_llm_client(settings) as llm,
    ):
        tools = ToolRegistry(settings, jira, assets, default_project_keys=project_keys)
        agent = JiraAgent(settings, llm, tools, project_keys=project_keys)
        result = agent.ask(question)

    if json_out:
        console.print_json(
            data={
                "answer": result.answer,
                "tool_calls": result.tool_calls,
                "provider": settings.llm_provider,
                "model": settings.active_model,
            }
        )
    else:
        console.print(Markdown(result.answer))


@app.command("projects")
def projects_cmd() -> None:
    """Список проектов Jira (GET /rest/api/2/project)."""
    settings = _load_settings()
    with JiraClient(settings) as jira:
        items = jira.list_projects()
    table = Table(title="Jira projects")
    table.add_column("Key")
    table.add_column("Name")
    table.add_column("Type")
    for p in items:
        table.add_row(
            str(p.get("key", "")),
            str(p.get("name", "")),
            str(p.get("projectTypeKey", "")),
        )
    console.print(table)


@app.command("issues")
def issues_cmd(
    projects: Optional[str] = typer.Option(None, "--projects", "-p"),
    jql: str = typer.Option("", "--jql", help="Дополнительный JQL"),
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """Поиск задач (POST /rest/api/2/search)."""
    settings = _load_settings()
    keys = _parse_projects(projects, settings)
    if not keys and not jql:
        console.print("[red]Укажите --projects или --jql[/red]")
        raise typer.Exit(1)
    with JiraClient(settings) as jira:
        if keys:
            data = jira.search_issues_by_projects(keys, extra_jql=jql, max_results=limit)
        else:
            data = jira.search_issues(jql, max_results=limit)
    console.print_json(json.dumps(data, ensure_ascii=False, default=str))


@app.command("assets")
def assets_cmd(
    aql: Optional[str] = typer.Option(None, "--aql", help="AQL запрос"),
    iql: Optional[str] = typer.Option(None, "--iql", help="IQL для navlist"),
    projects: Optional[str] = typer.Option(None, "--projects", "-p"),
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """Поиск активов AQL / IQL / по проектам."""
    settings = _load_settings()
    keys = _parse_projects(projects, settings)
    with AssetsClient(settings) as assets:
        if aql:
            data = assets.aql_objects(aql, max_results=limit)
        elif iql:
            data = assets.navlist_iql(iql, results_per_page=limit)
        elif keys:
            data = assets.search_assets_for_projects(keys, max_results=limit)
        else:
            data = assets.aql_objects(
                f"objectSchemaId = {settings.assets_object_schema_id}",
                max_results=limit,
            )
    console.print_json(json.dumps(data, ensure_ascii=False, default=str))


@app.command("asset")
def asset_cmd(
    object_id: str = typer.Argument(..., help="ID объекта Assets"),
    tickets: bool = typer.Option(False, "--tickets", help="Показать связанные тикеты"),
) -> None:
    """Детали актива и опционально связанные задачи."""
    settings = _load_settings()
    with AssetsClient(settings) as assets:
        obj = assets.get_object(object_id)
        console.print_json(json.dumps(obj, ensure_ascii=False, default=str))
        if tickets:
            linked = assets.get_connected_tickets(object_id)
            console.print("\n[bold]Connected tickets[/bold]")
            console.print_json(json.dumps(linked, ensure_ascii=False, default=str))


@app.command("schema")
def schema_cmd(
    schema_id: Optional[int] = typer.Option(
        None,
        "--id",
        help="Object schema id (default ASSETS_OBJECT_SCHEMA_ID)",
    ),
) -> None:
    """GET /rest/assets/1.0/objectschema/{id}"""
    settings = _load_settings()
    with AssetsClient(settings) as assets:
        data = assets.get_object_schema(schema_id)
    console.print_json(json.dumps(data, ensure_ascii=False, default=str))


@app.command("doctor")
def doctor_cmd() -> None:
    """Проверка связности Jira и LLM (DeepSeek / cloud / Ollama)."""
    settings = _load_settings()
    ok = True

    console.print(f"[bold]LLM[/bold] provider={settings.llm_provider}")
    try:
        with create_llm_client(settings) as llm:
            models = llm.list_models()
        console.print(f"  model: {settings.active_model}")
        if settings.llm_provider in {"ollama", "local"}:
            console.print(f"  URL: {settings.ollama_base_url}")
            console.print(f"  models: {', '.join(models[:20]) or '(пусто)'}")
            if settings.ollama_model not in models and not any(
                m.startswith(settings.ollama_model.split(":")[0]) for m in models
            ):
                console.print(
                    f"  [yellow]Модель {settings.ollama_model} не найдена в /api/tags[/yellow]"
                )
                ok = False
            else:
                console.print(f"  [green]OK[/green] Ollama / {settings.ollama_model}")
        else:
            console.print(f"  URL: {settings.openai_base_url}")
            key_set = bool(settings.openai_api_key)
            console.print(f"  API key: {'set' if key_set else '[red]MISSING[/red]'}")
            console.print(
                f"  [green]OK[/green] {llm.provider_name} / {settings.openai_model}"
            )
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]FAIL[/red] {exc}")
        ok = False

    console.print("[bold]Jira[/bold]")
    try:
        with JiraClient(settings) as jira:
            me = jira.myself()
            projects = jira.list_projects()
        console.print(f"  URL: {settings.jira_base_url}")
        console.print(
            f"  user: {me.get('displayName') or me.get('name') or me.get('key')} "
            f"<{me.get('emailAddress') or ''}>"
        )
        auth_mode = (
            "Basic(username+password)"
            if settings.jira_username and settings.jira_password
            else "Basic(username+PAT)"
            if settings.jira_username and settings.jira_pat
            else "Bearer PAT"
            if settings.jira_pat
            else "unknown"
        )
        console.print(f"  auth: {auth_mode}")
        console.print(f"  projects: {len(projects)}")
        if len(projects) == 0:
            console.print(
                "  [yellow]WARN[/yellow] 0 projects — проверьте Browse Projects "
                "или что учётная запись не сервисная без прав"
            )
        console.print("  [green]OK[/green] /rest/api/2/myself + /project")
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]FAIL[/red] {exc}")
        ok = False

    console.print("[bold]Assets[/bold]")
    try:
        # Force Basic-friendly credentials check early
        _ = settings.assets_basic_auth()
        with AssetsClient(settings) as assets:
            schema = assets.get_object_schema()
            used = assets.api_prefix
        console.print(
            f"  schema {settings.assets_object_schema_id}: "
            f"{schema.get('name') or schema.get('id')}"
        )
        console.print(f"  prefix: {used}")
        console.print(f"  [green]OK[/green] {used}/objectschema/{{id}}")
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]FAIL[/red] {exc}")
        console.print(
            "  [dim]Hint: в .env нужны JIRA_USERNAME + JIRA_PASSWORD "
            "(или USERNAME + JIRA_PAT). Не оставляйте только JIRA_PAT без username — "
            "Assets на DC часто отвечает 401 на Bearer.[/dim]"
        )
        console.print(
            "  [dim]Также: право на Assets/Insight и схема "
            f"ASSETS_OBJECT_SCHEMA_ID={settings.assets_object_schema_id}. "
            "При необходимости ASSETS_API_PREFIX=insight[/dim]"
        )
        ok = False

    raise typer.Exit(code=0 if ok else 2)


@app.callback()
def main_callback() -> None:
    """Jira Data Center AI agent."""


if __name__ == "__main__":
    app()
