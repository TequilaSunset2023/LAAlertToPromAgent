#!/usr/bin/env python

import os
import sys
import logging
import click
import uvicorn
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI
import functools
from google.adk import version

# 确保当前目录在 Python 路径中，以便可以导入自定义模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入自定义的 fast_api 实现
from custom_fast_api import get_fast_api_app
from google.adk.cli.utils import logs

LOG_LEVELS = click.Choice(
    ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    case_sensitive=False,
)

def fast_api_common_options():
  """Decorator to add common fast api options to click commands."""

  def decorator(func):
    @click.option(
        "--port",
        type=int,
        help="Optional. The port of the server",
        default=8000,
    )
    @click.option(
        "--allow_origins",
        help="Optional. Any additional origins to allow for CORS.",
        multiple=True,
    )
    @click.option(
        "--log_level",
        type=LOG_LEVELS,
        default="INFO",
        help="Optional. Set the logging level",
    )
    @click.option(
        "--trace_to_cloud",
        is_flag=True,
        show_default=True,
        default=False,
        help="Optional. Whether to enable cloud trace for telemetry.",
    )
    @click.option(
        "--reload/--no-reload",
        default=True,
        help=(
            "Optional. Whether to enable auto reload for server. Not supported"
            " for Cloud Run."
        ),
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
      return func(*args, **kwargs)

    return wrapper

  return decorator

@click.group(context_settings={"max_content_width": 240})
@click.version_option(version.__version__)
def main():
  """Agent Development Kit CLI tools."""
  pass

def adk_services_options():
  """Decorator to add ADK services options to click commands."""

  def decorator(func):
    @click.option(
        "--session_service_uri",
        help=(
            """Optional. The URI of the session service.
          - Use 'agentengine://<agent_engine_resource_id>' to connect to Agent Engine sessions.
          - Use 'sqlite://<path_to_sqlite_file>' to connect to a SQLite DB.
          - See https://docs.sqlalchemy.org/en/20/core/engines.html#backend-specific-urls for more details on supported database URIs."""
        ),
    )
    @click.option(
        "--artifact_service_uri",
        type=str,
        help=(
            "Optional. The URI of the artifact service,"
            " supported URIs: gs://<bucket name> for GCS artifact service."
        ),
        default=None,
    )
    @click.option(
        "--eval_storage_uri",
        type=str,
        help=(
            "Optional. The evals storage URI to store agent evals,"
            " supported URIs: gs://<bucket name>."
        ),
        default=None,
    )
    @click.option(
        "--memory_service_uri",
        type=str,
        help=(
            """Optional. The URI of the memory service.
            - Use 'rag://<rag_corpus_id>' to connect to Vertex AI Rag Memory Service.
            - Use 'agentengine://<agent_engine_resource_id>' to connect to Vertex AI Memory Bank Service. e.g. agentengine://12345"""
        ),
        default=None,
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
      return func(*args, **kwargs)

    return wrapper

  return decorator


def deprecated_adk_services_options():
  """Depracated ADK services options."""

  def warn(alternative_param, ctx, param, value):
    if value:
      click.echo(
          click.style(
              f"WARNING: Deprecated option {param.name} is used. Please use"
              f" {alternative_param} instead.",
              fg="yellow",
          ),
          err=True,
      )
    return value

  def decorator(func):
    @click.option(
        "--session_db_url",
        help="Deprecated. Use --session_service_uri instead.",
        callback=functools.partial(warn, "--session_service_uri"),
    )
    @click.option(
        "--artifact_storage_uri",
        type=str,
        help="Deprecated. Use --artifact_service_uri instead.",
        callback=functools.partial(warn, "--artifact_service_uri"),
        default=None,
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
      return func(*args, **kwargs)

    return wrapper

  return decorator


@main.command("web")
@click.option(
    "--host",
    type=str,
    help="Optional. The binding host of the server",
    default="127.0.0.1",
    show_default=True,
)
@fast_api_common_options()
@adk_services_options()
@deprecated_adk_services_options()
@click.argument(
    "agents_dir",
    type=click.Path(
        exists=True, dir_okay=True, file_okay=False, resolve_path=True
    ),
    default=os.getcwd,
)
def cli_web_custom(
    agents_dir: str,
    eval_storage_uri: Optional[str] = None,
    log_level: str = "INFO",
    allow_origins: Optional[list[str]] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    trace_to_cloud: bool = False,
    reload: bool = True,
    session_service_uri: Optional[str] = None,
    artifact_service_uri: Optional[str] = None,
    memory_service_uri: Optional[str] = None,
    session_db_url: Optional[str] = None,  # Deprecated
    artifact_storage_uri: Optional[str] = None,  # Deprecated
):
  """Starts a FastAPI server with Web UI for agents.

  AGENTS_DIR: The directory of agents, where each sub-directory is a single
  agent, containing at least `__init__.py` and `agent.py` files.

  Example:

    adk web --port=[port] path/to/agents_dir
  """
  logs.setup_adk_logger(getattr(logging, log_level.upper()))

  @asynccontextmanager
  async def _lifespan(app: FastAPI):
    click.secho(
        f"""
+-----------------------------------------------------------------------------+
| ADK Web Server started                                                      |
|                                                                             |
| For local testing, access at http://localhost:{port}.{" "*(29 - len(str(port)))}|
+-----------------------------------------------------------------------------+
""",
        fg="green",
    )
    yield  # Startup is done, now app is running
    click.secho(
        """
+-----------------------------------------------------------------------------+
| ADK Web Server shutting down...                                             |
+-----------------------------------------------------------------------------+
""",
        fg="green",
    )

  session_service_uri = session_service_uri or session_db_url
  artifact_service_uri = artifact_service_uri or artifact_storage_uri
  app = get_fast_api_app(
      agents_dir=agents_dir,
      session_service_uri=session_service_uri,
      artifact_service_uri=artifact_service_uri,
      memory_service_uri=memory_service_uri,
      eval_storage_uri=eval_storage_uri,
      allow_origins=allow_origins,
      web=True,
      trace_to_cloud=trace_to_cloud,
      lifespan=_lifespan,
  )
  config = uvicorn.Config(
      app,
      host=host,
      port=port,
      reload=reload,
  )

  server = uvicorn.Server(config)
  server.run()

if __name__ == "__main__":
    cli_web_custom()