"""
sopno/tools/schema/files.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool schemas for file read, write, edit, list, delete, rename, copy, move, search.
"""

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file inside an allowed folder (by default the project). PDFs, images, and Office documents (.pdf/.png/.jpg/.docx/.xlsx/.pptx/…) are read automatically with text extraction or OCR. Folders are never listed here — use list_directory for that.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to read."
                    },
                    "lines": {
                        "type": "number",
                        "description": "Optional — positive = first N lines, negative = last N lines."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or overwrite an existing one inside an allowed write folder (by default the project). Overwriting a file needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to create or overwrite."
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text to write."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace one exact string inside a file. The old_string must appear exactly once, so include enough surrounding text to be unique. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to edit."
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to replace (must occur exactly once)."
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The replacement text."
                    }
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List the files and folders inside an allowed folder (defaults to the project root), with type and size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the folder to list (optional — defaults to the project root)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a single file inside an allowed write folder. Folders are never deleted. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to delete."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rename_file",
            "description": "Rename or move a single file inside an allowed write folder. The destination must not already exist. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to move."
                    },
                    "new_path": {
                        "type": "string",
                        "description": "Absolute destination path."
                    }
                },
                "required": ["path", "new_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Duplicate a file or folder inside an allowed folder. Won't overwrite an existing destination unless overwrite=true. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file or folder to copy."
                    },
                    "new_path": {
                        "type": "string",
                        "description": "Absolute destination path."
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Allow replacing an existing destination (default false)."
                    }
                },
                "required": ["path", "new_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a single file inside an allowed folder. The destination must not already exist. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to move."
                    },
                    "new_path": {
                        "type": "string",
                        "description": "Absolute destination path."
                    }
                },
                "required": ["path", "new_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find files by file name (mode='name') or by their contents (mode='content'). Name mode matches fnmatch globs or substrings; content mode matches regex or plain text and returns path:line hits. Searches a folder (defaults to the project root) and skips blocked paths and binary files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Filename pattern (mode='name') or text/regex to find inside files (mode='content')."
                    },
                    "path": {
                        "type": "string",
                        "description": "Absolute folder to search (optional — defaults to the project root)."
                    },
                    "mode": {
                        "type": "string",
                        "description": "'name' or 'content' (default 'content')."
                    }
                },
                "required": ["query"]
            }
        }
    },
]
