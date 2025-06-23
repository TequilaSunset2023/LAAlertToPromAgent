#!/usr/bin/env python

import os
import sys
import logging
import click
import uvicorn
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI

# 确保当前目录在 Python 路径中，以便可以导入自定义模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入自定义的 fast_api 实现
from custom_fast_api import get_fast_api_app
from google.adk.cli.utils import logs

@click.command()
@click.option(
    "--session_db_url",
    help=(
        """Optional. The database URL to store the session.

  - Use 'agentengine://<agent_engine_resource_id>' to connect to Agent Engine sessions.

  - Use 'sqlite://<path_to_sqlite_file>' to connect to a SQLite DB.

  - See https://docs.sqlalchemy.org/en/20/core/engines.html#backend-specific-urls for more details on supported DB URLs."""
    ),
)
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
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default="INFO",
    help="Optional. Set the logging level",
)
@click.option(
    "--log_to_tmp",
    is_flag=True,
    show_default=True,
    default=False,
    help=(
        "Optional. Whether to log to system temp folder instead of console."
        " This is useful for local debugging."
    ),
)
@click.option(
    "--trace_to_cloud",
    is_flag=True,
    show_default=True,
    default=False,
    help="Optional. Whether to enable cloud trace for telemetry.",
)
@click.argument(
    "agents_dir",
    type=click.Path(
        exists=True, dir_okay=True, file_okay=False, resolve_path=True
    ),
    default=os.getcwd,
)
def cli_web_custom(
    agents_dir: str,
    log_to_tmp: bool,
    session_db_url: str = "",
    log_level: str = "INFO",
    allow_origins: Optional[List[str]] = None,
    port: int = 8000,
    trace_to_cloud: bool = False,
):
    """Starts a FastAPI server with Web UI for agents.

  AGENTS_DIR: The directory of agents, where each sub-directory is a single
  agent, containing at least `__init__.py` and `agent.py` files.
    """
    if log_to_tmp:
        logs.log_to_tmp_folder()
    else:
        logs.log_to_stderr()

    logging.getLogger().setLevel(log_level)

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
        yield  # 启动完成，应用程序正在运行
        click.secho(
            """
+-----------------------------------------------------------------------------+
| 自定义 ADK Web 服务器正在关闭...                                             |
+-----------------------------------------------------------------------------+
""",
            fg="green",
        )

    app = get_fast_api_app(
        agent_dir=agents_dir,
        session_db_url=session_db_url,
        allow_origins=allow_origins,
        web=True,
        trace_to_cloud=trace_to_cloud,
        lifespan=_lifespan,
    )
    
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        reload=True,
    )

    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    cli_web_custom()