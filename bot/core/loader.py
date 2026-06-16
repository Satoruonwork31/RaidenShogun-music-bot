from importlib import import_module

PLUGINS = [
    "start",
    "help",
    "ping",
    "play",
    "queue",
    "pause",
    "resume",
    "skip",
    "stop",
]

def load_plugins():
    for plugin in PLUGINS:
        import_module(f"bot.plugins.{plugin}")
