from importlib import import_module

PLUGINS = [
    "start",
    "help",
    "ping",
    "play",
    "vplay",
    "vskip",
    "song",
    "video",
    "queue",
    "pause",
    "resume",
    "skip",
    "stop",
    "toss",
    "ban",
    "unban",
    "id",
    "welcome",
    "greetings",
]

def load_plugins():
    for plugin in PLUGINS:
        import_module(f"bot.plugins.{plugin}")
