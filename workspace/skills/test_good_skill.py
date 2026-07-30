from tools.base import BaseTool
from models.tools import ToolInput, ToolOutput

class CustomTestTool(BaseTool):
    name = "custom_test_tool"
    description = "Test custom tool"
    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        return self._success("custom_ok")