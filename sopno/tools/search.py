"""
sopno/tools/search.py
━━━━━━━━━━━━━━━━━━━━━
Web search tool.

Performs a Google search using the system's default web browser.
"""

import webbrowser


def search_web(query: str) -> str:
    """
    Search Google for a query in the default web browser.

    Args:
        query: The search terms.

    Returns:
        A short spoken response confirming the search.
    """
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    try:
        webbrowser.open(url)
        return f"Searching the web for {query}."
    except Exception as e:
        return f"Failed to search the web: {e}"
