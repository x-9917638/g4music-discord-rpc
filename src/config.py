import os
import tomllib
from typing import Any
import tomli_w

def get_config() -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
    if (config_dir := os.environ.get('XDG_CONFIG_HOME')):
        CONFIG_DIR = os.path.join(config_dir, "g4music-discord-rpc/")
    else:
        CONFIG_DIR = os.path.join(os.environ.get("HOME", ""), ".config", "g4music-discord-rpc/")


    CONFIG_FILE = os.path.join(CONFIG_DIR, "config.toml")

    DEFAULT_CONFIG = {
        "appid": 1436573238636576891,
        "idle-detect": False,
        "details": "",
        "show-queue-size": True,
        "image-hover": "Listening to {song}",
        "icon": True,
        "cover-art": True,
        "state": "{song} / {album} - {artist}"
    }

    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(DEFAULT_CONFIG, f)

    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)
