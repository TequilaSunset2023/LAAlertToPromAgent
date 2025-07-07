"""
自定义的 fast_api.py 文件，用于覆盖 google.adk.cli 的 fast_api.py 文件
这允许我们修改 ADK web 服务器的行为而不直接修改原始包
"""

import sys
import os
import logging
from typing import Optional, List, Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from starlette.types import Lifespan
from google.genai import types

# 从 google.adk.cli.fast_api 导入原始函数和所需类型
from google.adk.cli.fast_api import get_fast_api_app as original_get_fast_api_app
from google.adk.cli.fast_api import AgentRunRequest
from google.adk.agents.run_config import StreamingMode
from google.adk.agents import RunConfig

logger = logging.getLogger(__name__)

def get_fast_api_app(
    *,
    agents_dir: str,
    session_service_uri: Optional[str] = None,
    artifact_service_uri: Optional[str] = None,
    memory_service_uri: Optional[str] = None,
    eval_storage_uri: Optional[str] = None,
    allow_origins: Optional[list[str]] = None,
    web: bool,
    trace_to_cloud: bool = False,
    lifespan: Optional[Lifespan[FastAPI]] = None,
) -> FastAPI:
    """
    这是一个自定义的 get_fast_api_app 函数，可以覆盖原始的函数
    添加自定义逻辑或修改现有行为
    """
    print("使用自定义 fast_api.py 实现！")
    
    # 调用原始函数获取基础应用程序
    app = original_get_fast_api_app(
        agents_dir=agents_dir,
        session_service_uri=session_service_uri,
        artifact_service_uri=artifact_service_uri,
        memory_service_uri=memory_service_uri,
        eval_storage_uri=eval_storage_uri,
        allow_origins=allow_origins,
        web=web,
        trace_to_cloud=trace_to_cloud,
        lifespan=lifespan,
    )
    
    # 获取原始 app 的各种服务，以便在我们的自定义路由中使用
    agent_engine_id = getattr(app.state, "agent_engine_id", "")
    session_service = getattr(app.state, "session_service", None)
    
    # 创建一个内部函数，用于获取 runner
    async def _get_runner_async(app_name: str):
        # 这里我们需要使用原始应用程序的 _get_runner_async 函数
        # 由于它是内部函数，我们需要访问 app 上的属性
        if hasattr(app, "_get_runner_async"):
            return await app._get_runner_async(app_name)
        else:
            # 尝试使用内部全局变量字典
            import inspect
            for name, func in inspect.getmembers(sys.modules['google.adk.cli.fast_api']):
                if name == '_get_runner_async':
                    return await func(app_name)
            raise ValueError("找不到 _get_runner_async 函数")
    
    # 添加自定义路由或修改现有路由
    @app.get("/custom-endpoint")
    async def custom_endpoint():
        """自定义端点示例"""
        return {"message": "这是一个自定义端点"}
    
    # 覆盖原始的 /run_sse 接口
    @app.post("/run_sse")
    async def agent_run_sse(req: AgentRunRequest) -> StreamingResponse:
        # Connect to managed session if agent_engine_id is set.
        app_id = agent_engine_id if agent_engine_id else req.app_name
        # SSE endpoint
        session = session_service.get_session(
            app_name=app_id, user_id=req.user_id, session_id=req.session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if req.new_message and req.new_message.parts and len(req.new_message.parts) > 0:
            hitl_prefix = "#HITL "
            if req.new_message.parts[0].text.startswith(hitl_prefix):
                session_service.user_state[app_id][req.user_id]["hitl"] = req.new_message.parts[0].text.strip(hitl_prefix)
                return StreamingResponse(
                    content="",
                    media_type="text",
                )

        # Convert the events to properly formatted SSE
        async def event_generator():
            try:
                stream_mode = StreamingMode.SSE if req.streaming else StreamingMode.NONE
                runner = await _get_runner_async(req.app_name)
                async for event in runner.run_async(
                    user_id=req.user_id,
                    session_id=req.session_id,
                    new_message=req.new_message,
                    run_config=RunConfig(streaming_mode=stream_mode),
                ):
                    # Format as SSE data
                    sse_event = event.model_dump_json(exclude_none=True, by_alias=True)
                    logger.info("Generated event in agent run streaming: %s", sse_event)
                    yield f"data: {sse_event}\n\n"
            except Exception as e:
                logger.exception("Error in event_generator: %s", e)
                # You might want to yield an error event here
                yield f'data: {{"error": "{str(e)}"}}\n\n'

        # Returns a streaming response with the proper media type for SSE
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
        )
    
    return app

# 替换原模块中的 get_fast_api_app 函数
sys.modules['google.adk.cli.fast_api'].get_fast_api_app = get_fast_api_app