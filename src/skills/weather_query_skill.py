"""
天气查询 Skill — 和风天气版
组合多个 MCP Tool 完成完整的天气查询
"""

from skills.base_skill import BaseSkill, SkillDefinition, SkillResult, SkillStatus


class WeatherQuerySkill(BaseSkill):
    """
    天气查询技能
    功能：查询指定城市的实时天气、天气预报和生活指数
    """

    def define(self) -> SkillDefinition:
        return SkillDefinition(
            name="weather_query",
            description=(
                "查询指定城市的完整天气信息，包括实时天气、"
                "未来天气预报和生活指数建议。基于和风天气API。"
            ),
            version="2.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "要查询天气的城市名称，如北京、上海"
                    },
                    "include_forecast": {
                        "type": "boolean",
                        "description": "是否包含天气预报，默认True",
                        "default": True
                    },
                    "include_indices": {
                        "type": "boolean",
                        "description": "是否包含生活指数，默认True",
                        "default": True
                    },
                    "forecast_days": {
                        "type": "integer",
                        "description": "预报天数，3 或 7，默认 3",
                        "default": 3,
                        "enum": [3, 7]
                    }
                },
                "required": ["city"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "realtime": {"type": "string"},
                    "forecast": {"type": "string"},
                    "indices": {"type": "string"}
                }
            },
            tags=["weather", "query", "qweather"],
            required_tools=[
                "get_realtime_weather",
                "get_weather_forecast",
                "get_life_indices"
            ]
        )

    async def execute(self, **kwargs) -> SkillResult:
        city = kwargs.get("city")
        include_forecast = kwargs.get("include_forecast", True)
        include_indices = kwargs.get("include_indices", True)
        forecast_days = kwargs.get("forecast_days", 3)

        results = {}
        errors = []

        # 1. 查询实时天气（必选）
        try:
            if self.mcp_client:
                realtime_data = await self.mcp_client.call_tool(
                    "get_realtime_weather", {"city": city}
                )
                results["realtime"] = realtime_data
            else:
                from weather_server import get_realtime_weather
                results["realtime"] = await get_realtime_weather(city)
        except Exception as e:
            errors.append(f"实时天气查询失败: {str(e)}")

        # 2. 查询天气预报（可选）
        if include_forecast:
            try:
                if self.mcp_client:
                    forecast_data = await self.mcp_client.call_tool(
                        "get_weather_forecast",
                        {"city": city, "days": forecast_days}
                    )
                    results["forecast"] = forecast_data
                else:
                    from weather_server import get_weather_forecast
                    results["forecast"] = await get_weather_forecast(
                        city, forecast_days
                    )
            except Exception as e:
                errors.append(f"天气预报查询失败: {str(e)}")

        # 3. 查询生活指数（可选）
        if include_indices:
            try:
                if self.mcp_client:
                    indices_data = await self.mcp_client.call_tool(
                        "get_life_indices", {"city": city}
                    )
                    results["indices"] = indices_data
                else:
                    from weather_server import get_life_indices
                    results["indices"] = await get_life_indices(city)
            except Exception as e:
                errors.append(f"生活指数查询失败: {str(e)}")

        # 4. 汇总结果
        if not results:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"无法获取{city}的任何天气信息。" + " ".join(errors)
            )

        output_parts = []
        if "realtime" in results:
            output_parts.append("【实时天气】\n" + str(results["realtime"]))
        if "forecast" in results:
            output_parts.append("\n【天气预报】\n" + str(results["forecast"]))
        if "indices" in results:
            output_parts.append("\n【生活指数】\n" + str(results["indices"]))

        status = SkillStatus.SUCCESS if not errors else SkillStatus.PARTIAL

        return SkillResult(
            status=status,
            data="\n".join(output_parts),
            message="" if not errors else "部分查询失败: " + "; ".join(errors),
            metadata={
                "city": city,
                "queried_items": list(results.keys()),
                "api_provider": "QWeather",
                "error_count": len(errors)
            }
        )