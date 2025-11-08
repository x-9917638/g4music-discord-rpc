#! /home/some1/Documents/Python/g4music-discord-rpc/.venv/bin/python

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

POLL_INTERVAL = 2

# Track song changing so we aren't uploading art every 2 seconds
song_change = True

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


async def poll_position(properties) -> float:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    """Poll current playback position in microseconds"""
    try:
        position = await properties.call_get(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            'org.mpris.MediaPlayer2.Player',
            'Position'
        )
        return position.value if hasattr(position, 'value') else position  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
    except Exception as e:
        logger.error(f"Error polling position: {e}")
        return 0


async def poll_metadata(properties) -> dict[str, Any]:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType, reportExplicitAny]
    """Poll current track metadata"""
    try:
        metadata = await properties.call_get(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            'org.mpris.MediaPlayer2.Player',
            'Metadata'
        )
        return {key: val.value for key, val in metadata.value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    except Exception as e:
        logger.error(f"Error polling metadata: {e}")
        return {}


async def poll_playback_status(properties) -> str:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    """Poll current playback status (Playing, Paused, Stopped)"""
    try:
        status = await properties.call_get(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            'org.mpris.MediaPlayer2.Player',
            'PlaybackStatus'
        )
        return status.value if hasattr(status, 'value') else status  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
    except Exception as e:
        logger.error(f"Error polling playback status: {e}")
        return "Stopped"


async def update_activity(properties):
    global song_change
    metadata = await poll_metadata(properties)
    status = await poll_playback_status(properties)

    if status == "stopped":
        app.clear()
        return

    artist = metadata.get(ARTIST, [None])[0]
    album = metadata.get(ALBUM)
    song = metadata.get(TITLE)

    if LENGTH in metadata:
        pos = (await poll_position(properties) // 1000000)
        activity["ts_start"] = int(time.time()) - pos
        activity["ts_end"] = int(time.time()) - pos + (metadata[LENGTH] // 1000000)


    if CONFIG["cover-art"] and song_change:
        path = await upload_image(metadata[ARTURL].removeprefix("file://"))  # pyright: ignore[reportAny]
        activity["large_image"] = path if path else "error"
        song_change = False

    activity["details"] = DETAILS_TEMPLATE.safe_substitute(artist=artist, album=album, song=song) if DETAILS_TEMPLATE else None
    activity["state"] = STATE_TEMPLATE.safe_substitute(artist=artist, album=album, song=song) if STATE_TEMPLATE else None
    activity["large_text"] = LARGE_TEXT_TEMPLATE.safe_substitute(artist=artist, album=album, song=song) if LARGE_TEXT_TEMPLATE else None

    if status == "Playing":
        activity["small_image"] = "playing"
    elif status == "Paused":
        activity["small_image"] = "paused"
    else:
        activity["small_image"] = None

    res = app.set_activity(**activity)
    if res:
        logger.debug(f"Activity updated successfully, {activity=}")
    else:
        logger.error("Error setting activity")


async def on_properties_changed(_a, changed_properties: dict[str, Variant], _c):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    global song_change
    for changed, _ in changed_properties.items():
        if changed == "Metadata":
            song_change = True


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

    while True:
        try:
            await update_activity(properties)
            await asyncio.sleep(POLL_INTERVAL)
        except Exception as e:
            logger.error(f"Error: {e}")
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    # app.run()
    loop.run_until_complete(main())
