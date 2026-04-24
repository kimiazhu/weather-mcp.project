"""
天气查询 Agent
集成 LLM + MCP + Skill 的完整智能体
"""

import os
import json
import asyncio
from typing import Optional
from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp_client_manager import MCPClientManager

load_dotenv()


class WeatherAgent:
    """
    天气查询智能体
    核心流程：
    1. 接收用户输入
    2. 调用 LLM 分析意图
    3. LLM 决策是否调用工具
    4. 通过 MCP Client 调用工具
    5. 将工具结果交回 LLM 综合回答
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: str = None,
        base_url: str = None
    ):
        # LLM 客户端配置（这里使用 OpenAI 兼容接口，支持 DeepSeek 等）
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("LLM_API_KEY"),
            base_url=base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        )
        self.model = model

        # MCP 客户端管理器
        self.mcp_manager = MCPClientManager()

        # 对话历史
        self.conversation_history: list[dict] = []

        # 系统提示词
        # 替换 agent.py 中的 system_prompt 为：
        self.system_prompt = """你是一个智能天气助手，基于和风天气(QWeather)数据，可以帮助用户查询全球天气信息并提供生活建议。

你的能力包括：
1. 查询任意城市的实时天气（温度、体感温度、天气状况、风力、湿度、能见度、气压等）
2. 查询未来3~7天的每日天气预报（最高最低温度、白天夜间天气、降水量、紫外线指数等）
3. 查询当天的生活指数（穿衣、洗车、运动、感冒、紫外线、旅游等共16项指数）
4. 搜索城市信息（支持模糊搜索、获取LocationID）

使用规则：
- 当用户询问天气相关问题时，使用对应的工具获取数据
- 获取数据后，用友好自然的语言总结天气信息
- 如果用户提到多个城市，逐个查询
- 主动根据天气数据给出穿衣、出行等实用建议
- 如果某个城市查询失败，告知用户可能是城市名有误，建议使用 search_city 工具确认
- 对于非天气相关的问题，礼貌地告知你是天气助手

请始终使用中文回复。"""

    async def connect_mcp_server(
        self,
        command: str = "python",
        args: list[str] = None,
        env: dict = None
    ):
        """连接 MCP Server"""
        if args is None:
            args = ["weather_server.py"]
        await self.mcp_manager.connect(command, args, env)
        print(f"[Agent] MCP Server 已连接")

    async def chat(self, user_message: str) -> str:
        """
        处理用户消息的核心方法
        实现 ReAct 模式：推理 → 行动 → 观察 → 回答
        """
        # 1. 添加用户消息到历史
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # 2. 构建完整的消息列表
        messages = [
            {"role": "system", "content": self.system_prompt}
        ] + self.conversation_history

        # 3. 获取 MCP 工具描述
        tools = self.mcp_manager.get_tools_for_llm()

        # 4. 调用 LLM（第一次 - 决定是否需要工具）
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            temperature=0.7,
            max_tokens=4096
        )

        assistant_message = response.choices[0].message

        # 5. 工具调用循环（可能多轮）
        max_tool_calls = 10  # 防止无限循环
        tool_call_count = 0

        while assistant_message.tool_calls and tool_call_count < max_tool_calls:
            tool_call_count += 1

            # 记录助手消息（包含工具调用请求）
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
            })

            # 逐个执行工具调用
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                print(f"[Agent] 调用工具: {tool_name}({tool_args})")

                try:
                    # 通过 MCP Client 调用工具
                    tool_result = await self.mcp_manager.call_tool(
                        tool_name, tool_args
                    )
                except Exception as e:
                    tool_result = f"工具调用失败: {str(e)}"

                print(f"[Agent] 工具返回: {tool_result[:100]}...")

                # 将工具结果添加到对话历史
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })

            # 再次调用 LLM（带上工具结果，让 LLM 综合回答）
            messages = [
                {"role": "system", "content": self.system_prompt}
            ] + self.conversation_history

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                temperature=0.7,
                max_tokens=4096
            )

            assistant_message = response.choices[0].message

        # 6. 最终回复
        final_response = assistant_message.content or "抱歉，我暂时无法回答这个问题。"

        # 记录到对话历史
        self.conversation_history.append({
            "role": "assistant",
            "content": final_response
        })

        return final_response

    def clear_history(self):
        """清空对话历史"""
        self.conversation_history = []

    async def close(self):
        """关闭 Agent，释放资源"""
        await self.mcp_manager.disconnect()