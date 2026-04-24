"""
Skill 注册中心 - 管理所有可用技能
"""

from typing import Optional
from base_skill import BaseSkill, SkillResult, SkillStatus


class SkillRegistry:
    """
    技能注册中心
    负责技能的注册、查找、管理
    """

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """注册一个技能"""
        self._skills[skill.name] = skill
        print(f"[SkillRegistry] 已注册技能: {skill.name} - {skill.description}")

    def unregister(self, skill_name: str) -> None:
        """注销一个技能"""
        if skill_name in self._skills:
            del self._skills[skill_name]
            print(f"[SkillRegistry] 已注销技能: {skill_name}")

    def get_skill(self, skill_name: str) -> Optional[BaseSkill]:
        """根据名称获取技能"""
        return self._skills.get(skill_name)

    def list_skills(self) -> list[dict]:
        """列出所有已注册技能"""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "tags": skill._definition.tags
            }
            for skill in self._skills.values()
        ]

    def get_all_tool_descriptions(self) -> list[dict]:
        """
        获取所有技能的工具描述，用于传递给 LLM 的 function calling
        """
        return [
            skill.to_tool_description()
            for skill in self._skills.values()
        ]

    async def execute_skill(self, skill_name: str, **kwargs) -> SkillResult:
        """
        执行指定技能
        :param skill_name: 技能名称
        :param kwargs: 技能参数
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"未找到技能: {skill_name}，"
                        f"可用技能: {', '.join(self._skills.keys())}"
            )
        return await skill.run(**kwargs)


# ========== 工厂函数 ==========
def create_weather_skill_registry(mcp_client=None) -> SkillRegistry:
    """
    创建天气相关的技能注册中心
    """
    from weather_query_skill import WeatherQuerySkill
    from travel_advisor_skill import TravelAdvisorSkill

    registry = SkillRegistry()
    registry.register(WeatherQuerySkill(mcp_client=mcp_client))
    registry.register(TravelAdvisorSkill(mcp_client=mcp_client))

    return registry