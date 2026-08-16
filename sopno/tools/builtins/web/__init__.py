"""
sopno/tools/builtins/web
━━━━━━━━━━━━━━━━━━━━━━━━
Internet-facing tools: browser automation (browser.py, Playwright, opt-in),
web search (search.py), and network diagnostics (network.py).
"""

from . import browser, search, network  # noqa: F401


def _reexport(*modules):
    namespace = globals()
    for module in modules:
        own = module.__name__.rpartition(".")[2]
        for name, value in vars(module).items():
            if name.startswith("__") or name == own:
                continue
            namespace.setdefault(name, value)


_reexport(browser, search, network)
del _reexport
