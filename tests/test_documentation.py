# tests/test_documentation.py

import unittest
import inspect
import dataclasses
import ast
from typing import get_type_hints, Any

# Assuming the schema is in the 'core' directory relative to the project root
import core.config_schema as config_schema

# Helper functions to parse the schema file
def _get_attribute_docs(cls: type) -> dict[str, str]:
    """
    Parses a class's source code to extract docstrings for its attributes.
    This works by finding an attribute assignment and checking if the very next
    line is a string literal, which is the common pattern for attribute docstrings.
    """
    docs = {}
    try:
        source = inspect.getsource(cls)
        tree = ast.parse(source)
        class_node = tree.body[0]

        for i, node in enumerate(class_node.body):
            # This pattern looks for an assignment (AnnAssign for 'attr: type')
            if isinstance(node, ast.AnnAssign) and i + 1 < len(class_node.body):
                # Get the attribute name
                attr_name = node.target.id

                # Check if the next node is a docstring
                next_node = class_node.body[i+1]
                if isinstance(next_node, ast.Expr) and isinstance(next_node.value, ast.Constant):
                    if isinstance(next_node.value.value, str):
                        docs[attr_name] = inspect.cleandoc(next_node.value.value)
    except (TypeError, OSError, IndexError):
        # This can happen for built-in types or dynamically generated classes
        pass
    return docs

def _format_type_for_md(t: Any) -> str:
    """Cleans up type hints for presentation in Markdown."""
    s = str(t)
    # Use backticks for better rendering
    s = s.replace("<class '", "`").replace("'>", "`")
    # Clean up typing module prefixes
    s = s.replace("typing.", "")
    # Make optional types more readable
    s = s.replace(" | None", " (optional)")
    s = s.replace("Union[", "").replace("]", "")
    s = s.replace(", NoneType", " (optional)")
    # Escape pipe characters for markdown tables
    return s.replace("|", "\\|")

def _generate_markdown_for_class(cls: type) -> str:
    """Generates markdown documentation for a single dataclass."""
    if not dataclasses.is_dataclass(cls):
        return ""

    md_parts = [f"### `{cls.__name__}`"]
    if cls.__doc__:
        md_parts.append(f"> {cls.__doc__}\n")

    md_parts.append("| Attribute | Type | Default | Description |")
    md_parts.append("|-----------|------|---------|-------------|")

    attribute_docs = _get_attribute_docs(cls)
    try:
        # Use get_type_hints to resolve forward references
        type_hints = get_type_hints(cls, include_extras=True)
    except (NameError, TypeError):
        # Fallback if a type hint can't be resolved
        type_hints = {f.name: f.type for f in dataclasses.fields(cls)}

    for f in dataclasses.fields(cls):
        name = f"`{f.name}`"
        type_str = _format_type_for_md(type_hints.get(f.name, f.type))

        if f.default is not dataclasses.MISSING:
            default_val = f"`{f.default}`"
        elif f.default_factory is not dataclasses.MISSING:
            default_val = "_(generated)_"
        else:
            default_val = "_Required_"

        description = attribute_docs.get(f.name, "No description available.")
        description = description.replace("\n", " ")

        md_parts.append(f"| {name} | {type_str} | {default_val} | {description} |")

    return "\n".join(md_parts) + "\n"


class TestDocumentation(unittest.TestCase):
    """
    A test suite that generates documentation from the config schema.
    Running this test will print the full markdown documentation to the console.
    """

    def test_generate_documentation_from_schema(self):
        """
        Generates markdown documentation from all dataclasses in config_schema.py.
        """
        all_markdown = ["# Configuration Schema Documentation\n"]
        all_markdown.append(
            "This document is auto-generated from `core/config_schema.py` and describes "
            "all available configuration options.\n"
        )

        # Find all dataclass objects within the imported module
        for name, obj in inspect.getmembers(config_schema, inspect.isclass):
            if obj.__module__ == config_schema.__name__ and dataclasses.is_dataclass(obj):
                class_md = _generate_markdown_for_class(obj)
                if class_md:
                    all_markdown.append(class_md)

        # The "test" is to print the documentation and ensure it's not empty.
        final_doc = "\n".join(all_markdown)
        print(final_doc)
        self.assertTrue(len(final_doc) > 200, "Generated documentation seems too short.")
