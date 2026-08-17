"""
sopno/tools/schema/knowledge.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool schemas for vision/OCR and notes.
"""

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "describe_screenshot",
            "description": "Describe an image with the configured local vision model (opt-in).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the image (inside the read roots)."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_image",
            "description": "Extract text from an image with Tesseract.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the image (inside the read roots)."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "note_write",
            "description": "Save a note as a markdown file. Requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Note title (becomes the file name)."
                    },
                    "content": {
                        "type": "string",
                        "description": "Note body (markdown ok)."
                    }
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "note_list",
            "description": "List the saved notes with sizes and dates.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "note_search",
            "description": "Search the notes for a phrase (case-insensitive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The text to look for."
                    }
                },
                "required": ["query"]
            }
        }
    },
]
