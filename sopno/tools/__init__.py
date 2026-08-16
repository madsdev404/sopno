"""
sopno/tools
━━━━━━━━━━━
Skills — what Sopno can DO.

The framework (how a skill is declared and run) lives at this level:

  - schema.py   → TOOLS_SCHEMA           (JSON schemas for the LLM)
  - registry.py → execute_tool, get_registered_names

The skills themselves live in the ``builtins`` subpackage, one file per
skill or small domain. Add new skills there and register them in the
framework.
"""

from sopno.tools.registry import execute_tool, get_registered_names
from sopno.tools.schema import TOOLS_SCHEMA, get_schema

__all__ = [
    "execute_tool",
    "get_registered_names",
    "TOOLS_SCHEMA",
    "get_schema",
]
