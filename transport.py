import asyncio
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("transport")

class BleTransport:
    def __init__(self, target_service_uuid: str, write_char_uuid: str, notify_char_uuid: str):
        self.target_service_uuid = target_service_uuid
        self.write_char_uuid = write_char_uuid
        self.notify_char_uuid = notify_char_uuid

        self._client: BleakClient | None = None
        self._receive_callback = None
        self._disconnect_callback = None

    async def connect(self, device_address: str | None = None, timeout: float = 10.0) -> bool:
        if self._client and self._client.is_connected:
            log.info("Already connected.")
            return True

        target_address = device_address
        if not target_address:
            log.info(f"Scanning for devices advertising service {self.target_service_uuid}...")
            device = await BleakScanner.find_device_by_service_uuid(self.target_service_uuid, timeout=timeout)
            if not device:
                log.error(f"Could not find device advertising service {self.target_service_uuid}")
                return False
            target_address = device.address
            log.info(f"Found device: {device.name} ({device.address})")

        log.info(f"Connecting to {target_address}...")
        self._client = BleakClient(target_address, disconnected_callback=self._handle_disconnect)
        try:
            connected = await self._client.connect(timeout=timeout)
            if connected:
                log.info("Connected successfully.")
                return True
            else:
                log.error("Failed to connect.")
                self._client = None
                return False
        except Exception as e:
            # Log more details: type, representation, message, and traceback
            log.error(
                f"Connection failed! Exception Type: {type(e)}, Representation: {repr(e)}, Message: {e}",
                exc_info=True  # This adds the full traceback to the log
            )
            self._client = None
            return False

    async def disconnect(self):
        if self._client and self._client.is_connected:
            log.info("Disconnecting...")
            await self._client.disconnect()
            log.info("Disconnected.")

    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _handle_disconnect(self, client: BleakClient):
        log.warning(f"Device disconnected: {client.address}")
        self._client = None
        if self._disconnect_callback:
            self._disconnect_callback()

    def set_disconnect_callback(self, callback):
        self._disconnect_callback = callback

    async def write_data(self, data: bytes, with_response: bool = False):
        if not self.is_connected():
            log.error("Cannot write, not connected.")
            raise BleakError("Not connected")
        try:
            await self._client.write_gatt_char(
                self.write_char_uuid,
                data,
                response=with_response
            )
        except Exception as e:
            log.error(f"Failed to write data: {e}")
            raise e

    def _handle_notification(self, sender_handle: int, data: bytearray):
        if self._receive_callback:
            self._receive_callback(data)

    async def start_notify(self, receive_callback):
        if not self.is_connected():
            log.error("Cannot start notify, not connected.")
            raise BleakError("Not connected")

        self._receive_callback = receive_callback
        try:
            log.info(f"Subscribing to notifications on {self.notify_char_uuid}...")
            await self._client.start_notify(
                self.notify_char_uuid,
                self._handle_notification
            )
            log.info("Subscribed successfully.")
        except Exception as e:
            log.error(f"Failed to subscribe to notifications: {e}")
            self._receive_callback = None
            raise e

    async def stop_notify(self):
        if not self.is_connected():
            log.warning("Cannot stop notify, not connected.")
            return

        log.info(f"Unsubscribing from notifications on {self.notify_char_uuid}...")
        try:
            await self._client.stop_notify(self.notify_char_uuid)
            log.info("Unsubscribed successfully.")
        except Exception as e:
            log.error(f"Failed to unsubscribe notifications: {e}")
        finally:
            self._receive_callback = None

    async def get_mtu(self) -> int:
        if not self.is_connected():
            raise BleakError("Not connected")
        log.warning("get_mtu() returning placeholder value.")
        return 244

    async def start_advertising(self):
        log.error("start_advertising not implemented for client role.")
        raise NotImplementedError

    async def stop_advertising(self):
        log.error("stop_advertising not implemented for client role.")
        raise NotImplementedError