import asyncio
import time
from typing import Any
from dbus_fast.aio.proxy_object import Variant  # pyright: ignore[reportPrivateImportUsage]
from dbus_fast.errors import DBusError
from discordrpc import RPC, Button, Activity  # pyright: ignore[reportMissingTypeStubs]
from dbus_fast.aio import MessageBus, ProxyInterface
import logging
from string import Template
from config import get_config  # pyright: ignore[reportMissingTypeStubs]
import requests

logger = logging.getLogger(__name__)
logger.level = logging.INFO

POLL_INTERVAL = 2

# Track song changing so we aren't uploading art every 2 seconds
song_change = True

CONFIG = get_config()

level = CONFIG["general"].get("log-level")
if level:
    logger.level = level

LARGE_TEXT_TEMPLATE = (
    Template(CONFIG["image"]["text"]) if CONFIG["image"]["text"] else None  # pyright: ignore[reportAny]
)
DETAILS_TEMPLATE = (
    Template(CONFIG["details"]["text"]) if CONFIG["details"]["text"] else None  # pyright: ignore[reportAny]
)
STATE_TEMPLATE = Template(CONFIG["state"]["text"]) if CONFIG["state"]["text"] else None  # pyright: ignore[reportAny]

buttons = []

for button in CONFIG["buttons"].values():  # pyright: ignore[reportAny]
    if all(button.values()):  # pyright: ignore[reportAny]
        buttons.append(Button(**button))  # pyright: ignore[reportUnknownMemberType, reportAny]

# Dictionary keys that mpris metadata query returns
ARTIST = "xesam:artist"
ALBUM = "xesam:album"
TITLE = "xesam:title"
ARTURL = "mpris:artUrl"
LENGTH = "mpris:length"

loop = asyncio.get_event_loop()

activity: dict[str, Any] = {  # pyright: ignore[reportExplicitAny]
    "state": None,
    "state_url": CONFIG["state"]["url"] if CONFIG["state"]["url"] else None,
    "details": None,
    "details_url": CONFIG["details"]["url"] if CONFIG["details"]["url"] else None,
    "act_type": Activity.Listening,
    "large_image": None,
    "large_url": CONFIG["image"]["url"] if CONFIG["image"]["url"] else None,
    "large_text": None,
    "small_image": None,
    "small_text": None,
    "ts_start": None,
    "ts_end": None,
    "buttons": buttons,
}


def get_app() -> RPC:
    while True:
        try:
            logger.info("Attempting to connect to Discord RPC socket.")
            app = RPC(
                app_id=CONFIG["general"].get("appid") or 1436573238636576891,
                exit_if_discord_close=False,
                exit_on_disconnect=False,
            )
            logger.info("Connection success!")
            break
        except ConnectionRefusedError:
            logger.info("Connection failure, retrying in 2s.")
            time.sleep(2)
    return app


async def poll_position(properties) -> float:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    """Poll current playback position in microseconds"""
    try:
        position = await properties.call_get(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            "org.mpris.MediaPlayer2.Player", "Position"
        )
        return position.value if hasattr(position, "value") else position  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
    except Exception as e:
        logger.error(f"Error polling position: {e}")
        return 0


async def poll_metadata(properties) -> dict[str, Any]:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType, reportExplicitAny]
    """Poll current track metadata"""
    try:
        metadata = await properties.call_get(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            "org.mpris.MediaPlayer2.Player", "Metadata"
        )
        return {key: val.value for key, val in metadata.value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    except Exception as e:
        logger.error(f"Error polling metadata: {e}")
        return {}


async def poll_playback_status(properties) -> str:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    """Poll current playback status (Playing, Paused, Stopped)"""
    try:
        status = await properties.call_get(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            "org.mpris.MediaPlayer2.Player", "PlaybackStatus"
        )
        return status.value if hasattr(status, "value") else status  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
    except Exception as e:
        logger.error(f"Error polling playback status: {e=}")
        return "Stopped"


async def update_activity(properties: ProxyInterface, app: RPC):
    global song_change
    metadata = await poll_metadata(properties)
    status = await poll_playback_status(properties)

    if status == "Stopped":
        app.clear()
        return

    artist = metadata.get(ARTIST, [None])[0]  # pyright: ignore[reportAny]
    album = metadata.get(ALBUM)
    song = metadata.get(TITLE)

    if LENGTH in metadata and CONFIG["general"]["show-time"]:
        pos = await poll_position(properties) // 1000000
        curr_time = int(time.time())
        length = metadata[LENGTH] // 1000000  # pyright: ignore[reportAny]
        activity["ts_start"] = curr_time - pos
        activity["ts_end"] = curr_time - pos + length
        logger.debug(f"{curr_time=}, {pos=}, {length=}")

    if CONFIG["general"]["cover-art"] and song_change:
        path = await upload_image(metadata[ARTURL].removeprefix("file://"))  # pyright: ignore[reportAny]
        activity["large_image"] = path if path else "error"
        song_change = False

    activity["details"] = (
        DETAILS_TEMPLATE.safe_substitute(artist=artist, album=album, song=song)  # pyright: ignore[reportAny]
        if DETAILS_TEMPLATE
        else None
    )
    activity["state"] = (
        STATE_TEMPLATE.safe_substitute(artist=artist, album=album, song=song)  # pyright: ignore[reportAny]
        if STATE_TEMPLATE
        else None
    )
    activity["large_text"] = (
        LARGE_TEXT_TEMPLATE.safe_substitute(artist=artist, album=album, song=song)  # pyright: ignore[reportAny]
        if LARGE_TEXT_TEMPLATE
        else None
    )

    if status == "Playing":
        activity["small_image"] = "playing"
    elif status == "Paused":
        activity["small_image"] = "paused"
    else:
        activity["small_image"] = None

    activity["small_text"] = status

    res = app.set_activity(**activity)  # pyright: ignore[reportUnknownMemberType, reportAny]
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
        files = {"fileToUpload": f}
        data = {"reqtype": "fileupload", "time": "1h"}
        resp = requests.post(
            url="https://litterbox.catbox.moe/resources/internals/api.php",
            files=files,
            data=data,
        )
        resp.raise_for_status()
        if resp.text.startswith("https://"):
            return resp.text.strip()
    return None


async def main():
    while True:
        try:
            logger.info("Connecting to player")
            bus = await MessageBus().connect()
            introspection = await bus.introspect(
                "org.mpris.MediaPlayer2.com.github.neithern.g4music",
                "/org/mpris/MediaPlayer2",
            )
            obj = bus.get_proxy_object(
                "org.mpris.MediaPlayer2.com.github.neithern.g4music",
                "/org/mpris/MediaPlayer2",
                introspection,
            )
            properties = obj.get_interface("org.freedesktop.DBus.Properties")
            break
        except DBusError:
            logger.warning("No player detected, retrying connection.")
            await asyncio.sleep(2)

    properties.on_properties_changed(on_properties_changed)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]

    app = get_app()

    while True:
        try:
            await update_activity(properties, app)
            await asyncio.sleep(POLL_INTERVAL)
        except Exception as e:
            logger.error(f"Error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


def run():
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.debug("User exit")
        exit(0)


if __name__ == "__main__":
    run()
