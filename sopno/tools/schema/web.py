"""
sopno/tools/schema/web.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Tool schemas for web search, fetch, and browser automation.
"""

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for a query and return the top results with titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The web search query string."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch a webpage or URL and return its readable text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch (e.g. https://en.wikipedia.org/wiki/Python_(programming_language))."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research",
            "description": "Research a question in depth across the web and return a complete, cited answer (uses multiple search engines and reads several full pages).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question to research, phrased as a full question (e.g., 'What is the latest Linux kernel release?')."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Open a web page (only domains in browser_allowed_domains) and return a text snapshot: page title, body text, and indexed interactive elements ([0] …) you can click or type into.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to open (https:// is assumed if omitted)."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element on the current page. Use the index from the interactive-elements snapshot (selector may be empty), or a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector (optional — empty uses the snapshot index)."
                    },
                    "index": {
                        "type": "integer",
                        "description": "Element index within the selector match or the snapshot list (default 0)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type text into an input or textarea on the current page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector (empty = first visible input/textarea)."
                    },
                    "text": {
                        "type": "string",
                        "description": "The text to type."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_extract",
            "description": "Read the (capped) text of a region of the current page — empty selector reads the whole body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector (optional)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Save a PNG screenshot of the current page. The path must be inside the allowed file write roots; overwriting an existing file asks for confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute PNG path."
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture the full scrollable page (default false)."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_back",
            "description": "Go back to the previous page and return a new snapshot.",
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
            "name": "browser_close",
            "description": "Close the browser session (frees the Playwright process).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]
