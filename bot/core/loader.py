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
    "departure",
    "broadcast",
    "stats",
    "sudo",
    "playback_buttons",
    "linksniffer",
    "kill",
    "pat",
    "pin",
    "purge",
    "celebrate",
]

def load_plugins():
    for plugin in PLUGINS:
        import_module(f"bot.plugins.{plugin}")
