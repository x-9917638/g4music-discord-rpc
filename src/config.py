import os
import tomllib
from typing import Any
import tomli_w


def get_config() -> dict[str, dict[str, Any]]:  # pyright: ignore[reportExplicitAny]
    if config_dir := os.environ.get("XDG_CONFIG_HOME"):
        CONFIG_DIR = os.path.join(config_dir, "g4music-discord-rpc/")
    else:
        CONFIG_DIR = os.path.join(
            os.environ.get("HOME", ""), ".config", "g4music-discord-rpc/"
        )

    CONFIG_FILE = os.path.join(CONFIG_DIR, "config.toml")

    DEFAULT_CONFIG = {
        "general": {
            "appid": 1436573238636576891,
            "cover-art": True,
            "show-time": True,
            "log-level": 30,  # 30 WARN, 20 INFO, 10 DEBUG,
        },
        "details": {
            "text": "",
            "url": "",
        },
        "state": {
            "text": "${song} / ${album} - ${artist}",
            "url": "",
        },
        "image": {
            "text": "Listening to ${song}",
            "url": "",
        },
        "buttons": {
            "1": {"text": "", "url": ""},
            "2": {"text": "", "url": ""},
        },
    }

    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(DEFAULT_CONFIG, f)

    with open(CONFIG_FILE, "rb") as f:
        conf = tomllib.load(f)

        # Set defaults if they don't exist
        for k, v in DEFAULT_CONFIG.items():
            if k not in conf:
                conf[k] = v

        return conf
