# websocket_server.py
import asyncio
import json
import time
import websockets

from db import update_product_name, save_image_for_ean

connected_clients = set()
last_article = None
WS_LOOP = None


async def broadcast(message_dict: dict):
    if not connected_clients:
        return
    data = json.dumps(message_dict)
    dead = []
    for ws in connected_clients:
        try:
            await ws.send(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.discard(ws)


def broadcast_from_anywhere(message_dict: dict):
    global WS_LOOP
    if WS_LOOP and WS_LOOP.is_running():
        asyncio.run_coroutine_threadsafe(broadcast(message_dict), WS_LOOP)
    else:
        print("[broadcast_from_anywhere] WS_LOOP läuft nicht:", message_dict)


async def ws_handler(websocket):
    global last_article
    connected_clients.add(websocket)
    print("[ws_handler] Client verbunden")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                print("[ws_handler] JSONDecodeError, Nachricht ignoriert")
                continue

            msg_type = data.get("type")
            print(f"[ws_handler] msg_type = {msg_type}")

            if msg_type == "set_article":
                ean = (data.get("ean") or "").strip()
                name = (data.get("name") or "").strip()
                last_article = {"ean": ean, "name": name}
                await broadcast({"type": "current_article", **last_article})

            elif msg_type == "request_current_article":
                if last_article:
                    await websocket.send(json.dumps({
                        "type": "current_article",
                        **last_article
                    }))

            elif msg_type == "upload_image":
                ean = (data.get("ean") or "").strip()
                image_b64 = data.get("image_base64", "")
                if not ean or not image_b64:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "ean und image_base64 erforderlich"
                    }))
                    continue
                filepath = save_image_for_ean(ean, image_b64)
                await broadcast({
                    "type": "image_updated",
                    "ean": ean,
                    "image_path": filepath,
                    "timestamp": int(time.time())
                })

            elif msg_type == "image_uploaded":
                ean = (data.get("ean") or "").strip()
                if not ean:
                    continue
                await broadcast({
                    "type": "image_updated",
                    "ean": ean,
                    "timestamp": int(time.time())
                })

            elif msg_type == "save_name":
                ean = (data.get("ean") or "").strip()
                name = (data.get("name") or "").strip()
                if not ean:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "ean erforderlich"
                    }))
                    continue
                update_product_name(ean, name)
                last_article = {"ean": ean, "name": name}
                await broadcast({
                    "type": "current_article",
                    "ean": ean,
                    "name": name,
                })

            else:
                print(f"[ws_handler] Unbekannter msg_type: {msg_type}")

    finally:
        connected_clients.discard(websocket)
        print("[ws_handler] Client getrennt")


def start_ws_server():
    async def main_ws():
        print("WS-Server auf ws://0.0.0.0:8765")
        async with websockets.serve(
            ws_handler,
            "0.0.0.0",
            8765,
            max_size=None,
        ):
            await asyncio.Future()

    global WS_LOOP
    WS_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(WS_LOOP)
    WS_LOOP.run_until_complete(main_ws())
