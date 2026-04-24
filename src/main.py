"""
天气查询 Agent - 命令行交互入口
"""

import asyncio
import os
from dotenv import load_dotenv
from agent import WeatherAgent

load_dotenv()


async def main():
    print("=" * 55)
    print("  🌤️  智能天气助手 v1.0")
    print("  支持查询实时天气、天气预报、生活建议")
    print("  输入 'quit' 退出, 'clear' 清空对话历史")
    print("=" * 55)

    # 1. 创建 Agent
    agent = WeatherAgent(
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    )

    # 2. 连接 MCP Server
    try:
        await agent.connect_mcp_server(
            command="python",
            args=["weather_server.py"],
            env={
                **os.environ,
                "SENIVERSE_API_KEY": os.getenv("SENIVERSE_API_KEY", "")
            }
        )
    except Exception as e:
        print(f"[Error] 无法连接 MCP Server: {e}")
        return

    # 3. 交互循环
    try:
        while True:
            user_input = input("\n🙋 你: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "quit":
                print("\n👋 再见！")
                break

            if user_input.lower() == "clear":
                agent.clear_history()
                print("🗑️ 对话历史已清空")
                continue

            print("\n🤖 助手: ", end="", flush=True)
            try:
                response = await agent.chat(user_input)
                print(response)
            except Exception as e:
                print(f"\n❌ 发生错误: {str(e)}")

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())