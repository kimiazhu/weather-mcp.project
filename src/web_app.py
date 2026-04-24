"""
天气查询 Agent - Web API 入口 (FastAPI)
提供 REST API 供前端或其他服务调用
"""

import os
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import WeatherAgent

load_dotenv()

# ========== 全局 Agent 实例 ==========
agent: Optional[WeatherAgent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global agent

    # 启动时初始化
    agent = WeatherAgent(
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    )

    try:
        await agent.connect_mcp_server(
            command="python",
            args=["weather_server.py"],
            env={
                **os.environ,
                "SENIVERSE_API_KEY": os.getenv("SENIVERSE_API_KEY", "")
            }
        )
        print("[WebApp] Agent 初始化完成")
    except Exception as e:
        print(f"[WebApp] Agent 初始化失败: {e}")

    yield

    # 关闭时清理
    if agent:
        await agent.close()
        print("[WebApp] Agent 已关闭")


# ========== FastAPI 应用 ==========
app = FastAPI(
    title="天气查询智能体 API",
    description="基于 MCP + LLM 的智能天气查询服务",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 数据模型 ==========
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class HealthResponse(BaseModel):
    status: str
    mcp_connected: bool
    available_tools: list[str]


# ========== API 路由 ==========
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查接口"""
    return HealthResponse(
        status="healthy" if agent else "unhealthy",
        mcp_connected=agent.mcp_manager.session is not None if agent else False,
        available_tools=[
            t["name"] for t in agent.mcp_manager.available_tools
        ] if agent else []
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    对话接口
    发送消息给天气助手，获取回复
    """
    if not agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        reply = await agent.chat(request.message)
        return ChatResponse(
            reply=reply,
            session_id=request.session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@app.post("/clear")
async def clear_history():
    """清空对话历史"""
    if agent:
        agent.clear_history()
    return {"message": "对话历史已清空"}


@app.get("/tools")
async def list_tools():
    """列出可用的 MCP 工具"""
    if not agent:
        return {"tools": []}
    return {"tools": agent.mcp_manager.available_tools}


# ========== 启动 ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "web_app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )