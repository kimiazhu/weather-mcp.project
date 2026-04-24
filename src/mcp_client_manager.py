"""
MCP Client 管理器
负责连接和管理 MCP Server
"""

import asyncio
import json
from typing import Any, Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClientManager:
    """
    MCP 客户端管理器
    负责：
    1. 连接 MCP Server
    2. 获取可用工具列表
    3. 调用 MCP Tools
    """

    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.available_tools: list[dict] = []

    async def connect(self, server_command: str, server_args: list[str],
                      env: dict = None) -> None:
        """
        连接到 MCP Server
        :param server_command: 启动命令（如 "python" 或 "uv"）
        :param server_args: 命令参数
        :param env: 环境变量
        """
        server_params = StdioServerParameters(
            command=server_command,
            args=server_args,
            env=env
        )

        # 创建 stdio 传输连接
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read, write = stdio_transport

        # 创建客户端会话
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read, write)
        )

        # 初始化连接
        await self.session.initialize()

        # 获取可用工具
        response = await self.session.list_tools()
        self.available_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            }
            for tool in response.tools
        ]

        print(f"[MCPClient] 已连接，可用工具: "
              f"{[t['name'] for t in self.available_tools]}")

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] = None) -> str:
        """
        调用 MCP Tool
        :param tool_name: 工具名称
        :param arguments: 工具参数
        :return: 工具返回结果（文本）
        """
        if not self.session:
            raise RuntimeError("MCP Client 未连接，请先调用 connect()")

        result = await self.session.call_tool(tool_name, arguments or {})

        # 提取文本内容
        if result.content:
            return "\n".join(
                item.text for item in result.content
                if hasattr(item, "text")
            )
        return "工具未返回结果"

    def get_tools_for_llm(self) -> list[dict]:
        """
        获取适合传递给 LLM function calling 的工具描述
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"]
                }
            }
            for tool in self.available_tools
        ]

    async def disconnect(self) -> None:
        """断开连接"""
        await self.exit_stack.aclose()
        self.session = None
        self.available_tools = []
        print("[MCPClient] 已断开连接")