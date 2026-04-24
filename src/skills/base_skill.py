"""
Skill 基类 - 定义所有技能的统一接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class SkillStatus(Enum):
    """技能执行状态"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


@dataclass
class SkillResult:
    """技能执行结果"""
    status: SkillStatus
    data: Any = None
    message: str = ""
    metadata: dict = field(default_factory=dict)

    def is_success(self) -> bool:
        return self.status == SkillStatus.SUCCESS

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "data": self.data,
            "message": self.message,
            "metadata": self.metadata
        }


@dataclass
class SkillDefinition:
    """技能定义元数据"""
    name: str
    description: str
    version: str = "1.0.0"
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)


class BaseSkill(ABC):
    """
    Skill 抽象基类
    所有技能都需要继承此类并实现 execute 方法
    """

    def __init__(self, mcp_client=None):
        """
        :param mcp_client: MCP 客户端实例，用于调用 MCP Tools
        """
        self.mcp_client = mcp_client
        self._definition = self.define()

    @abstractmethod
    def define(self) -> SkillDefinition:
        """定义技能的元数据"""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> SkillResult:
        """执行技能的核心逻辑"""
        pass

    async def validate_input(self, **kwargs) -> Optional[str]:
        """
        验证输入参数，返回 None 表示验证通过，否则返回错误信息
        """
        required_fields = self._definition.input_schema.get("required", [])
        for field_name in required_fields:
            if field_name not in kwargs or kwargs[field_name] is None:
                return f"缺少必填参数: {field_name}"
        return None

    async def run(self, **kwargs) -> SkillResult:
        """
        运行技能（包含参数验证和错误处理）
        """
        # 1. 参数验证
        error = await self.validate_input(**kwargs)
        if error:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=error
            )

        # 2. 执行技能
        try:
            result = await self.execute(**kwargs)
            return result
        except TimeoutError:
            return SkillResult(
                status=SkillStatus.TIMEOUT,
                message="技能执行超时"
            )
        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"技能执行异常: {str(e)}"
            )

    @property
    def name(self) -> str:
        return self._definition.name

    @property
    def description(self) -> str:
        return self._definition.description

    def to_tool_description(self) -> dict:
        """
        将 Skill 转换为 LLM 可理解的工具描述（兼容 function calling 格式）
        """
        return {
            "type": "function",
            "function": {
                "name": self._definition.name,
                "description": self._definition.description,
                "parameters": self._definition.input_schema
            }
        }