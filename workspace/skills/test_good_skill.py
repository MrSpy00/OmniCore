from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class CustomTestTool(BaseTool):
    name = "custom_test_tool"
    description = "Test custom tool"
    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        return self._success("custom_ok")
