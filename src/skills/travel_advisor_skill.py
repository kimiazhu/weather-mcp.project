"""
旅行天气建议 Skill - 根据天气数据提供旅行建议
"""

from base_skill import BaseSkill, SkillDefinition, SkillResult, SkillStatus


class TravelAdvisorSkill(BaseSkill):
    """
    旅行天气顾问技能
    功能：根据目的地天气情况，提供出行穿衣建议
    """

    def define(self) -> SkillDefinition:
        return SkillDefinition(
            name="travel_weather_advisor",
            description="根据目的地城市天气情况，提供旅行穿衣和出行建议",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "目的地城市名称"
                    },
                    "travel_date": {
                        "type": "string",
                        "description": "出行日期，如'明天'、'后天'、'2025-01-15'"
                    }
                },
                "required": ["city"]
            },
            tags=["weather", "travel", "advisor"],
            required_tools=["get_weather_forecast", "get_life_suggestion"]
        )

    async def execute(self, **kwargs) -> SkillResult:
        city = kwargs.get("city")
        travel_date = kwargs.get("travel_date", "近期")

        results = {}

        # 1. 获取天气预报
        try:
            if self.mcp_client:
                forecast = await self.mcp_client.call_tool(
                    "get_weather_forecast", {"city": city, "days": 3}
                )
            else:
                from weather_server import get_weather_forecast
                forecast = await get_weather_forecast(city, 3)
            results["forecast"] = forecast
        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"无法获取{city}的天气预报: {str(e)}"
            )

        # 2. 获取生活建议
        try:
            if self.mcp_client:
                suggestion = await self.mcp_client.call_tool(
                    "get_life_suggestion", {"city": city}
                )
            else:
                from weather_server import get_life_suggestion
                suggestion = await get_life_suggestion(city)
            results["suggestion"] = suggestion
        except Exception:
            results["suggestion"] = "暂无生活建议数据"

        # 3. 生成旅行建议
        advice = self._generate_travel_advice(city, travel_date, results)

        return SkillResult(
            status=SkillStatus.SUCCESS,
            data=advice,
            metadata={"city": city, "travel_date": travel_date}
        )

    def _generate_travel_advice(self, city: str, travel_date: str, results: dict) -> str:
        """根据天气数据生成旅行建议"""
        output = f"🧳 {city}旅行天气参考（{travel_date}）\n"
        output += "=" * 45 + "\n\n"

        if "forecast" in results:
            output += "📊 天气预报:\n"
            output += str(results["forecast"]) + "\n\n"

        if "suggestion" in results:
            output += "💡 生活建议:\n"
            output += str(results["suggestion"]) + "\n\n"

        output += "🎒 温馨提示:\n"
        output += "• 出行前请再次确认最新天气预报\n"
        output += "• 建议随身携带雨具以防万一\n"
        output += "• 注意防晒保暖，根据温差调整穿衣\n"

        return output