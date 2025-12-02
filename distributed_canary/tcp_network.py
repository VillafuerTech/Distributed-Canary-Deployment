"""TCP-based mesh network for inter-node communication."""

from __future__ import annotations

import asyncio
import json
from typing import Dict, Tuple

from .messages import Message, MessageType


class TCPNetwork:
    """Handles TCP communication between distributed nodes."""

    def __init__(self, node_peers: Dict[str, Tuple[str, int]]) -> None:
        """Initialize with peer addresses.

        Args:
            node_peers: Dict mapping node_id to (hostname, port) tuple.
        """
        self.node_peers = node_peers
        self.writers: Dict[str, asyncio.StreamWriter] = {}
        self.readers: Dict[str, asyncio.StreamReader] = {}

    async def send(self, target_id: str, message: Message) -> None:
        """Send a message to a target node via TCP."""
        if target_id not in self.node_peers:
            return

        if target_id not in self.writers or self.writers[target_id].is_closing():
            await self._connect_to_peer(target_id)

        writer = self.writers.get(target_id)
        if writer and not writer.is_closing():
            try:
                payload = json.dumps(
                    {
                        "msg_type": message.msg_type.value,
                        "sender": message.sender,
                        "payload": message.payload,
                    }
                ).encode("utf-8")
                writer.write(len(payload).to_bytes(4, "big"))
                writer.write(payload)
                await writer.drain()
            except Exception as e:
                print(f"Failed to send message to {target_id}: {e}")
                self.writers.pop(target_id, None)

    async def _connect_to_peer(self, target_id: str) -> None:
        """Establish a TCP connection to a peer."""
        if target_id not in self.node_peers:
            return
        host, port = self.node_peers[target_id]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                reader, writer = await asyncio.open_connection(host, port)
                self.writers[target_id] = writer
                self.readers[target_id] = reader
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    print(f"Failed to connect to {target_id} at {host}:{port}: {e}")

    async def start_listening(
        self, host: str, port: int, on_message_callback
    ) -> None:
        """Start listening for incoming peer connections."""
        server = await asyncio.start_server(
            lambda r, w: self._handle_peer_connection(r, w, on_message_callback),
            host,
            port,
        )
        print(f"Listening for peer connections on {host}:{port}")
        async with server:
            await server.serve_forever()

    async def _handle_peer_connection(self, reader, writer, on_message_callback) -> None:
        """Handle incoming connection from a peer."""
        try:
            while True:
                length_bytes = await reader.readexactly(4)
                if not length_bytes:
                    break
                msg_length = int.from_bytes(length_bytes, "big")

                msg_data = await reader.readexactly(msg_length)
                message_dict = json.loads(msg_data.decode("utf-8"))

                message = Message(
                    msg_type=MessageType(message_dict["msg_type"]),
                    sender=message_dict["sender"],
                    payload=message_dict["payload"],
                )
                await on_message_callback(message)
        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            print(f"Error in peer connection handler: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
