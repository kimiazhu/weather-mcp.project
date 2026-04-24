"""
天气查询 MCP Server — SSE 远程模式（和风天气版）
支持多客户端远程连接
"""

import os
import json
from typing import Any, Optional
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

# SSE 模式 MCP 服务器
mcp = FastMCP("WeatherServer")

API_KEY = os.getenv("QWEATHER_API_KEY", "your_api_key")
API_HOST = os.getenv("QWEATHER_API_HOST", "devapi.qweather.com")
GEO_HOST = os.getenv("QWEATHER_GEO_HOST", "geoapi.qweather.com")
WEATHER_BASE = f"https://{API_HOST}/v7"
GEO_BASE = f"https://{GEO_HOST}/v2"


async def make_qweather_request(url: str, params: dict[str, Any]) -> Optional[dict]:
    """向和风天气 API 发起异步请求"""
    headers = {
        "X-QW-Api-Key": API_KEY,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            if data.get("code") != "200":
                return {"error": f"API错误码: {data.get('code')}"}
            return data
        except Exception as e:
            return {"error": str(e)}


async def get_location_id(city: str) -> tuple[Optional[str], Optional[str]]:
    """获取城市的 LocationID"""
    if city.isdigit():
        return city, city
    if "," in city:
        parts = city.split(",")
        try:
            float(parts[0]); float(parts[1])
            return city, city
        except ValueError:
            pass
    url = f"{GEO_BASE}/city/lookup"
    data = await make_qweather_request(url, {"location": city, "number": 1, "lang": "zh"})
    if data and "error" not in data:
        locs = data.get("location", [])
        if locs:
            return locs[0].get("id"), locs[0].get("name", city)
    return None, city


@mcp.tool()
async def get_realtime_weather(city: str) -> str:
    """获取指定城市的实时天气信息"""
    location_id, city_name = await get_location_id(city)
    if not location_id:
        return f"未找到城市「{city}」"
    data = await make_qweather_request(
        f"{WEATHER_BASE}/weather/now", {"location": location_id, "lang": "zh"}
    )
    if not data or "error" in data:
        return f"查询失败: {data}"
    now = data.get("now", {})
    return (
        f"城市: {city_name}\n"
        f"温度: {now.get('temp')}°C | 体感: {now.get('feelsLike')}°C\n"
        f"天气: {now.get('text')} | 湿度: {now.get('humidity')}%\n"
        f"风: {now.get('windDir')} {now.get('windScale')}级 {now.get('windSpeed')}km/h\n"
        f"能见度: {now.get('vis')}km | 气压: {now.get('pressure')}hPa"
    )


@mcp.tool()
async def get_weather_forecast(city: str, days: int = 3) -> str:
    """获取指定城市未来几天的天气预报"""
    location_id, city_name = await get_location_id(city)
    if not location_id:
        return f"未找到城市「{city}」"
    days_param = {3: "3d", 7: "7d"}.get(days, "3d")
    data = await make_qweather_request(
        f"{WEATHER_BASE}/weather/{days_param}", {"location": location_id, "lang": "zh"}
    )
    if not data or "error" in data:
        return f"查询失败: {data}"
    parts = []
    for d in data.get("daily", []):
        parts.append(
            f"日期: {d.get('fxDate')}\n"
            f"  白天: {d.get('textDay')} {d.get('tempMax')}°C | "
            f"夜间: {d.get('textNight')} {d.get('tempMin')}°C\n"
            f"  湿度: {d.get('humidity')}% | 紫外线: {d.get('uvIndex')}"
        )
    return f"城市: {city_name}\n" + "\n".join(parts)


@mcp.tool()
async def get_life_indices(city: str) -> str:
    """获取指定城市当天的生活指数建议"""
    location_id, city_name = await get_location_id(city)
    if not location_id:
        return f"未找到城市「{city}」"
    data = await make_qweather_request(
        f"{WEATHER_BASE}/indices/1d",
        {"location": location_id, "type": "0", "lang": "zh"}
    )
    if not data or "error" in data:
        return f"查询失败: {data}"
    parts = [f"城市: {city_name} - 生活指数"]
    for item in data.get("daily", []):
        parts.append(f"{item.get('name')}: {item.get('category')} - {item.get('text', '')}")
    return "\n".join(parts)


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9000)