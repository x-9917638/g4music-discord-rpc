import asyncio
import time
from typing import Any
from dbus_fast import Message
from dbus_fast.aio.proxy_object import ProxyObject, Variant
from discordrpc import RPC
from dbus_fast.aio import MessageBus
import logging
from string import Template
from textwrap import shorten
from discordrpc.presence import Activity
from config import get_config
import requests

logger = logging.getLogger(__name__)
logger.level = logging.INFO

CONFIG = get_config()
LARGE_TEXT_TEMPLATE = Template(CONFIG["image-hover"]) if CONFIG["image-hover"] else None
DETAILS_TEMPLATE = Template(CONFIG["details"]) if CONFIG["details"] else None
STATE_TEMPLATE = Template(CONFIG["state"]) if CONFIG["state"] else None

# Dictionary keys that mpris metadata query returns
ARTIST = "xesam:artist"
ALBUM = "xesam:album"
TITLE = "xesam:title"
ARTURL = "mpris:artUrl"
LENGTH = "mpris:length"

loop = asyncio.get_event_loop()

activity: dict[str, Any] = {  # pyright: ignore[reportExplicitAny]
    "state": None,
    "details": None,
    "act_type": Activity.Listening,
    "large_image": None,
    "large_url": "https://gitlab.gnome.org/neithern/g4music",
    "large_text": None,
    "small_image": None,
    "ts_start": None,
    "ts_end": None
}

def get_app() -> RPC:
    while True:
        try:
            logger.info("Attempting to connect to Discord RPC socket.")
            app = RPC(
                app_id=CONFIG.get("appid") or 1436573238636576891,
                exit_if_discord_close=False,
                exit_on_disconnect=False
            )
            logger.info("Connection success!")
            break
        except ConnectionRefusedError:
            logger.info("Connection failure, retrying in 2s.")
            time.sleep(2)
    return app

app = get_app()


async def on_properties_changed(_a, changed_properties: dict[str, Variant], _c):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    if len(changed_properties) == 4:
        # Useless property changes, these are sent in a group of 4.:
        # {'CanGoNext': <dbus_fast.signature.Variant ('b', True)>,
        # 'CanGoPrevious': <dbus_fast.signature.Variant ('b', True)>,
        # 'CanPause': <dbus_fast.signature.Variant ('b', True)>,
        # 'CanPlay': <dbus_fast.signature.Variant ('b', True)>}
        return

    for changed, variant in changed_properties.items():
        if changed == "Metadata":
            values: dict[str, Any] = {key: val.value for key, val in variant.value.items()}  # pyright: ignore[reportAny, reportExplicitAny]

            artist = values[ARTIST][0]
            album = values[ALBUM]
            song = values[TITLE]

            if CONFIG["cover-art"]:
                path = await upload_image(values[ARTURL].removeprefix("file://"))  # pyright: ignore[reportAny]
                activity["large_image"] = path if path else "error"

            activity["ts_start"] = int(time.time())
            activity["ts_end"] = int(time.time()) + (values[LENGTH] // 1000000)

            activity["details"] = DETAILS_TEMPLATE.safe_substitute(artist=artist, album=album, song=song) if DETAILS_TEMPLATE else None
            activity["state"] = STATE_TEMPLATE.safe_substitute(artist=artist, album=album, song=song) if STATE_TEMPLATE else None
            activity["large_text"] = LARGE_TEXT_TEMPLATE.safe_substitute(artist=artist, album=album, song=song) if LARGE_TEXT_TEMPLATE else None
        elif changed == "PlaybackStatus":
            match variant.value:  # pyright: ignore[reportAny]
                case "Playing":
                    activity["small_image"] = "playing"
                case "Paused":
                    activity["small_image"] = "paused"
                    activity["ts_start"] = int(time.time())
                    activity["ts_end"] = int(time.time())
                case _:
                    return
        else:
            return

    print(activity)
    _ = app.set_activity(**activity)  # pyright: ignore[reportAny, reportUnknownMemberType]


async def upload_image(image_path: str) -> str | None:
    """
    Uploads an image to litterbox.catbox.moe
    :param image_path: A path to the local image

    :return: A url to the image on catbox.
    """
    with open(image_path, "rb") as f:
        files = {
            "fileToUpload": f
        }
        data = {
                        "reqtype": "fileupload",
                        "time": "1h"
        }
        resp = requests.post(url="https://litterbox.catbox.moe/resources/internals/api.php", files=files, data=data)
        resp.raise_for_status()
        if resp.text.startswith("https://"):
            return resp.text.strip()
    return None


async def main():
    bus = await MessageBus().connect()
    introspection = await bus.introspect("org.mpris.MediaPlayer2.com.github.neithern.g4music", "/org/mpris/MediaPlayer2")
    obj = bus.get_proxy_object("org.mpris.MediaPlayer2.com.github.neithern.g4music", "/org/mpris/MediaPlayer2", introspection)
    global properties
    properties = obj.get_interface('org.freedesktop.DBus.Properties')

    properties.on_properties_changed(on_properties_changed)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]

    await loop.create_future()

if __name__ == "__main__":
    # app.run()
    loop.run_until_complete(main())
