"""
天气查询 MCP Server（和风天气 QWeather 版）
基于和风天气 API v7，提供实时天气、天气预报、生活指数查询功能。

和风天气特点：
- 免费版 1000次/天，免费付费同权
- 认证方式：API KEY 放在请求头 X-QW-Api-Key
- 返回数据为 Gzip 压缩的 JSON
- 需要先通过 GeoAPI 获取城市 LocationID，再查询天气
"""

import os
import json
from typing import Any, Optional
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 加载环境变量
load_dotenv()

# ========== 初始化 MCP 服务器 ==========
mcp = FastMCP("WeatherServer")

# ========== API 配置 ==========
API_KEY = os.getenv("QWEATHER_API_KEY", "your_api_key")
API_HOST = os.getenv("QWEATHER_API_HOST", "devapi.qweather.com")
GEO_HOST = os.getenv("QWEATHER_GEO_HOST", "geoapi.qweather.com")

# API 基地址
WEATHER_BASE = f"https://{API_HOST}/v7"
GEO_BASE = f"https://{GEO_HOST}/v2"


# ========== HTTP 请求封装 ==========
async def make_qweather_request(url: str, params: dict[str, Any]) -> Optional[dict]:
    """
    向和风天气 API 发起异步请求。
    和风天气返回 Gzip 压缩数据，httpx 默认自动解压。

    :param url: 完整的 API URL
    :param params: 查询参数
    :return: 解析后的 JSON 字典，失败返回 None
    """
    headers = {
        "X-QW-Api-Key": API_KEY,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url,
                headers=headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

            # 和风天气用 code 字段表示状态
            if data.get("code") != "200":
                code = data.get("code", "未知")
                print(f"[QWeather] API返回错误码: {code}")
                return {"error": f"API错误码: {code}", "code": code}

            return data

        except httpx.HTTPStatusError as e:
            print(f"[QWeather] HTTP错误: {e.response.status_code}")
            return {"error": f"HTTP错误: {e.response.status_code}"}
        except httpx.RequestError as e:
            print(f"[QWeather] 请求失败: {str(e)}")
            return {"error": f"请求失败: {str(e)}"}
        except Exception as e:
            print(f"[QWeather] 未知错误: {str(e)}")
            return None


# ========== GeoAPI：城市名 → LocationID ==========
async def lookup_city(city_name: str) -> Optional[dict]:
    """
    通过城市名称查询 LocationID。
    和风天气的天气接口需要使用 LocationID 而非直接传城市名。
    也可直接传 "经度,纬度" 格式的坐标。

    :param city_name: 城市名称，如 "北京"、"上海"
    :return: 城市信息字典，包含 id, name, lat, lon 等
    """
    url = f"{GEO_BASE}/city/lookup"
    params = {
        "location": city_name,
        "range": "cn",    # 限定中国范围，可去掉以支持全球
        "number": 1,       # 只取最匹配的一个结果
        "lang": "zh"
    }
    data = await make_qweather_request(url, params)

    if not data or "error" in data:
        return None

    locations = data.get("location", [])
    if not locations:
        return None

    return locations[0]  # 返回最匹配的城市


async def get_location_id(city: str) -> tuple[Optional[str], Optional[str]]:
    """
    获取城市的 LocationID 和名称。
    如果输入已经是 LocationID（纯数字）或坐标格式，直接使用。

    :param city: 城市名称、LocationID 或 "经度,纬度"
    :return: (location_id, city_name) 元组
    """
    # 如果已经是 LocationID（纯数字格式如 101010100）
    if city.isdigit():
        return city, city

    # 如果是经纬度格式（如 "116.41,39.92"）
    if "," in city:
        parts = city.split(",")
        try:
            float(parts[0])
            float(parts[1])
            return city, city
        except ValueError:
            pass

    # 通过 GeoAPI 查询
    city_info = await lookup_city(city)
    if city_info:
        return city_info.get("id"), city_info.get("name", city)

    return None, city


# ========== 数据格式化函数 ==========
def format_realtime_weather(data: dict, city_name: str) -> str:
    """格式化和风天气实时天气数据"""
    try:
        now = data.get("now", {})
        update_time = data.get("updateTime", "未知")

        return (
            f"📍 城市: {city_name}\n"
            f"🌡️ 温度: {now.get('temp', '未知')}°C\n"
            f"🤒 体感温度: {now.get('feelsLike', '未知')}°C\n"
            f"☁️ 天气: {now.get('text', '未知')}\n"
            f"💨 风向: {now.get('windDir', '未知')} {now.get('windScale', '')}级\n"
            f"💨 风速: {now.get('windSpeed', '未知')} km/h\n"
            f"💧 湿度: {now.get('humidity', '未知')}%\n"
            f"🌧️ 降水量: {now.get('precip', '0')} mm\n"
            f"🔭 能见度: {now.get('vis', '未知')} km\n"
            f"🧭 气压: {now.get('pressure', '未知')} hPa\n"
            f"☁️ 云量: {now.get('cloud', '未知')}%\n"
            f"🔄 观测时间: {now.get('obsTime', update_time)}"
        )
    except Exception as e:
        return f"格式化实时天气数据出错: {e}"


def format_daily_forecast(data: dict, city_name: str) -> str:
    """格式化和风天气每日预报数据"""
    try:
        daily_list = data.get("daily", [])
        if not daily_list:
            return "无天气预报数据"

        output = f"📍 城市: {city_name} — 未来天气预报\n"
        output += "=" * 42 + "\n"

        for day in daily_list:
            output += (
                f"\n📅 日期: {day.get('fxDate', '未知')}\n"
                f"  🌞 白天: {day.get('textDay', '未知')}，"
                f"最高温 {day.get('tempMax', '未知')}°C\n"
                f"  🌙 夜间: {day.get('textNight', '未知')}，"
                f"最低温 {day.get('tempMin', '未知')}°C\n"
                f"  💨 白天风: {day.get('windDirDay', '未知')} "
                f"{day.get('windScaleDay', '')}级\n"
                f"  💨 夜间风: {day.get('windDirNight', '未知')} "
                f"{day.get('windScaleNight', '')}级\n"
                f"  💧 湿度: {day.get('humidity', '未知')}%\n"
                f"  🌧️ 降水量: {day.get('precip', '0')} mm\n"
                f"  ☀️ 紫外线指数: {day.get('uvIndex', '未知')}\n"
                f"  🌅 日出: {day.get('sunrise', '--')} | "
                f"日落: {day.get('sunset', '--')}\n"
                f"  {'-' * 38}"
            )

        return output
    except Exception as e:
        return f"格式化天气预报数据出错: {e}"


def format_life_indices(data: dict, city_name: str) -> str:
    """格式化和风天气生活指数数据"""
    try:
        daily_list = data.get("daily", [])
        if not daily_list:
            return "无生活指数数据"

        output = f"📍 城市: {city_name} — 生活指数\n"
        output += "=" * 42 + "\n"

        # 指数类型 emoji 映射
        emoji_map = {
            "运动指数": "🏃",
            "洗车指数": "🚗",
            "穿衣指数": "👔",
            "钓鱼指数": "🎣",
            "紫外线指数": "☀️",
            "旅游指数": "✈️",
            "感冒指数": "🤧",
            "舒适度指数": "😊",
            "空气污染扩散条件指数": "🌫️",
            "空调开启指数": "❄️",
            "过敏指数": "🤒",
            "太阳镜指数": "🕶️",
            "化妆指数": "💄",
            "晾晒指数": "👕",
            "交通指数": "🚦",
            "防晒指数": "🧴",
        }

        for item in daily_list:
            name = item.get("name", "未知指数")
            emoji = emoji_map.get(name, "📊")
            output += (
                f"\n{emoji} {name}: {item.get('category', '未知')}\n"
                f"  📝 {item.get('text', '暂无详情')}\n"
            )

        return output
    except Exception as e:
        return f"格式化生活指数数据出错: {e}"


# ========== MCP 工具注册 ==========
@mcp.tool()
async def get_realtime_weather(city: str) -> str:
    """
    获取指定城市的实时天气信息，包括温度、体感温度、天气状况、
    风向、风速、湿度、降水量、能见度、气压、云量等。

    Args:
        city: 城市名称（如"北京"、"上海"、"深圳"），
              也支持 LocationID 或 "经度,纬度" 格式

    Returns:
        格式化的实时天气信息字符串
    """
    # 1. 获取 LocationID
    location_id, city_name = await get_location_id(city)
    if not location_id:
        return f"未找到城市「{city}」，请检查城市名称是否正确。"

    # 2. 请求实时天气
    url = f"{WEATHER_BASE}/weather/now"
    params = {"location": location_id, "lang": "zh"}
    data = await make_qweather_request(url, params)

    if not data:
        return f"无法获取 {city_name} 的实时天气信息，请稍后重试。"
    if "error" in data:
        return f"获取天气失败: {data['error']}"

    return format_realtime_weather(data, city_name)


@mcp.tool()
async def get_weather_forecast(city: str, days: int = 3) -> str:
    """
    获取指定城市未来几天的每日天气预报，包括最高最低温度、白天夜间天气、
    风力风向、湿度、降水量、紫外线指数、日出日落等。

    Args:
        city: 城市名称（如"北京"、"上海"），
              也支持 LocationID 或 "经度,纬度" 格式
        days: 预报天数，可选 3 或 7（免费版支持 3 和 7 天），默认 3 天

    Returns:
        格式化的天气预报字符串
    """
    # 1. 获取 LocationID
    location_id, city_name = await get_location_id(city)
    if not location_id:
        return f"未找到城市「{city}」，请检查城市名称是否正确。"

    # 2. 确定预报天数路径参数
    valid_days = {3: "3d", 7: "7d"}
    days_param = valid_days.get(days, "3d")

    # 3. 请求每日天气预报
    url = f"{WEATHER_BASE}/weather/{days_param}"
    params = {"location": location_id, "lang": "zh"}
    data = await make_qweather_request(url, params)

    if not data:
        return f"无法获取 {city_name} 的天气预报，请稍后重试。"
    if "error" in data:
        return f"获取天气预报失败: {data['error']}"

    return format_daily_forecast(data, city_name)


@mcp.tool()
async def get_life_indices(city: str) -> str:
    """
    获取指定城市当天的生活指数建议，包括：
    运动指数、洗车指数、穿衣指数、感冒指数、紫外线指数、
    旅游指数、舒适度指数、空气污染扩散条件指数等共16项。

    Args:
        city: 城市名称（如"北京"、"上海"），
              也支持 LocationID 或 "经度,纬度" 格式

    Returns:
        格式化的生活指数建议字符串
    """
    # 1. 获取 LocationID
    location_id, city_name = await get_location_id(city)
    if not location_id:
        return f"未找到城市「{city}」，请检查城市名称是否正确。"

    # 2. 请求生活指数（type=0 表示全部指数）
    url = f"{WEATHER_BASE}/indices/1d"
    params = {
        "location": location_id,
        "type": "0",   # 0 = 全部生活指数
        "lang": "zh"
    }
    data = await make_qweather_request(url, params)

    if not data:
        return f"无法获取 {city_name} 的生活指数，请稍后重试。"
    if "error" in data:
        return f"获取生活指数失败: {data['error']}"

    return format_life_indices(data, city_name)


@mcp.tool()
async def search_city(query: str) -> str:
    """
    搜索城市信息，获取城市的 LocationID、经纬度、所属行政区等信息。
    支持模糊搜索，可以只输入城市名称的一部分。

    Args:
        query: 搜索关键词，如"北京"、"朝阳"、"london"

    Returns:
        匹配到的城市列表信息
    """
    url = f"{GEO_BASE}/city/lookup"
    params = {
        "location": query,
        "number": 5,
        "lang": "zh"
    }
    data = await make_qweather_request(url, params)

    if not data or "error" in data:
        return f"搜索「{query}」失败，请检查输入。"

    locations = data.get("location", [])
    if not locations:
        return f"未找到与「{query}」匹配的城市。"

    output = f"🔍 搜索「{query}」的结果：\n"
    output += "-" * 40 + "\n"
    for loc in locations:
        output += (
            f"  📍 {loc.get('name', '未知')} "
            f"(ID: {loc.get('id', '未知')})\n"
            f"     {loc.get('adm1', '')} > {loc.get('adm2', '')}\n"
            f"     {loc.get('country', '')} | "
            f"经纬度: {loc.get('lat', '')},{loc.get('lon', '')}\n"
            f"     时区: {loc.get('tz', '')}\n\n"
        )

    return output


# ========== MCP 资源注册 ==========
@mcp.resource("weather://supported-cities")
def get_supported_cities() -> str:
    """返回支持查询的热门城市列表（实际上和风天气支持全球20万+城市）"""
    cities = {
        "热门城市": [
            "北京", "上海", "广州", "深圳", "杭州",
            "成都", "武汉", "南京", "重庆", "西安",
            "苏州", "天津", "长沙", "郑州", "青岛"
        ],
        "说明": "和风天气支持全球20万+城市，输入任意城市名即可查询",
        "API": "QWeather v7"
    }
    return json.dumps(cities, ensure_ascii=False, indent=2)


# ========== MCP 提示模板注册 ==========
@mcp.prompt()
def weather_query_prompt(city: str) -> list[dict]:
    """生成天气查询的标准提示模板"""
    return [
        {
            "role": "user",
            "content": (
                f"请帮我查询{city}的天气情况，"
                f"包括当前实时天气和未来三天的天气预报，"
                f"并给出生活指数建议。"
            )
        }
    ]


@mcp.prompt()
def travel_weather_prompt(city: str, date: str) -> list[dict]:
    """生成旅行天气查询的提示模板"""
    return [
        {
            "role": "user",
            "content": (
                f"我计划{date}去{city}旅行，"
                f"请帮我查看当地天气情况，并给出穿衣、出行建议。"
            )
        }
    ]


# ========== 启动入口 ==========
if __name__ == "__main__":
    mcp.run(transport="stdio")