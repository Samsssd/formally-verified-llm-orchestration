"""Tool registry and safe execution wrapper.

Provides a decorator-based tool registration system with automatic schema
extraction from type hints, plus a safe execution wrapper that catches
errors and returns structured results.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, overload

from excelsior_harness._types import ToolResult

logger = logging.getLogger(__name__)

# Python type → JSON Schema type mapping
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass
class ToolDefinition:
    """Metadata + callable for a registered tool."""

    name: str
    description: str
    callable: Callable[..., Any]
    parameters: dict[str, Any]


def _extract_schema(func: Callable) -> dict[str, Any]:
    """Extract a JSON-Schema-style parameter dict from function type hints."""
    sig = inspect.signature(func)
    hints = func.__annotations__
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name == "return":
            continue
        hint = hints.get(param_name, str)
        json_type = _TYPE_MAP.get(hint, "string")
        properties[param_name] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


class ToolRegistry:
    """Registry of tools available to agents."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    @overload
    def register(self, func: Callable) -> Callable: ...

    @overload
    def register(self, *, name: str) -> Callable[[Callable], Callable]: ...

    def register(
        self, func: Callable | None = None, *, name: str | None = None
    ) -> Callable | Callable[[Callable], Callable]:
        """Register a function as a tool, optionally with a custom name."""

        def decorator(f: Callable) -> Callable:
            tool_name = name or f.__name__
            defn = ToolDefinition(
                name=tool_name,
                description=(f.__doc__ or "").strip(),
                callable=f,
                parameters=_extract_schema(f),
            )
            self._tools[tool_name] = defn
            logger.debug("Registered tool: %s", tool_name)
            return f

        if func is not None:
            return decorator(func)
        return decorator

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> ToolDefinition:
        """Look up a tool by name. Raises KeyError if not found."""
        return self._tools[name]

    def list_tools(self) -> list[ToolDefinition]:
        """Return all registered tool definitions."""
        return list(self._tools.values())

    def to_openai_schema(self) -> list[dict[str, Any]]:
        """Generate OpenAI-format tool schemas for LLM calls."""
        return [
            {
                "type": "function",
                "function": {
                    "name": defn.name,
                    "description": defn.description,
                    "parameters": defn.parameters,
                },
            }
            for defn in self._tools.values()
        ]


def safe_execute(
    registry: ToolRegistry, tool_name: str, arguments: dict[str, Any]
) -> ToolResult:
    """Execute a tool safely, catching any exceptions."""
    try:
        defn = registry.get(tool_name)
        result = defn.callable(**arguments)
        logger.info("Tool %s executed successfully", tool_name)
        return {"name": tool_name, "result": result, "error": None}
    except Exception as exc:
        logger.warning("Tool %s failed: %s", tool_name, exc)
        return {"name": tool_name, "result": None, "error": str(exc)}


# Convenience alias
tool = ToolRegistry.register
