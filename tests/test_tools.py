"""Tests for tool registry and safe execution."""

from excelsior_harness.tools import ToolRegistry, safe_execute, tool


class TestToolDecorator:
    def test_register_via_decorator(self):
        registry = ToolRegistry()

        @registry.register
        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello, {name}!"

        assert "greet" in registry
        defn = registry.get("greet")
        assert defn.description == "Say hello."
        assert defn.callable("world") == "Hello, world!"

    def test_register_with_custom_name(self):
        registry = ToolRegistry()

        @registry.register(name="my_tool")
        def some_func(x: int) -> int:
            """Double it."""
            return x * 2

        assert "my_tool" in registry
        assert "some_func" not in registry


class TestToolRegistry:
    def test_list_tools(self):
        registry = ToolRegistry()

        @registry.register
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "add"

    def test_to_openai_schema(self):
        registry = ToolRegistry()

        @registry.register
        def search(query: str) -> str:
            """Search the web."""
            return "results"

        schemas = registry.to_openai_schema()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "search"
        assert "query" in schemas[0]["function"]["parameters"]["properties"]

    def test_get_nonexistent_raises(self):
        registry = ToolRegistry()
        import pytest

        with pytest.raises(KeyError):
            registry.get("nonexistent")


class TestSafeExecute:
    def test_successful_execution(self):
        registry = ToolRegistry()

        @registry.register
        def double(x: int) -> int:
            """Double."""
            return x * 2

        result = safe_execute(registry, "double", {"x": 5})
        assert result["name"] == "double"
        assert result["result"] == 10
        assert result["error"] is None

    def test_execution_with_error(self):
        registry = ToolRegistry()

        @registry.register
        def fail_tool() -> str:
            """Always fails."""
            raise ValueError("broken")

        result = safe_execute(registry, "fail_tool", {})
        assert result["name"] == "fail_tool"
        assert result["result"] is None
        assert "broken" in result["error"]
