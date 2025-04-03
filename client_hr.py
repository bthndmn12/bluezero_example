import asyncio
import logging
from multiparty_ble.transport import BleTransport
from multiparty_ble.protocol import PacketType, PacketFlags

SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "00002a39-0000-1000-8000-00805f9b34fb"  # Control Point (for writing)
NOTIFY_CHAR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"  # HR Measurement (notifications)


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hr-client")

def parse_hr_measurement(data: bytearray):
    flags = data[0]
    hr_format = flags & 0x01
    ee_present = flags & 0x08
    sc_status = (flags >> 1) & 0x03

    index = 1
    if hr_format == 0:
        hr = data[index]
        index += 1
    else:
        hr = data[index] + (data[index+1] << 8)
        index += 2

    ee = None
    if ee_present:
        ee = data[index] + (data[index+1] << 8)

    log.info(f"Heart Rate: {hr} bpm, Sensor Contact: {sc_status}, Energy Expended: {ee}")

def on_notify(data: bytearray):
    log.info(f"Notification received: {data.hex()}")
    parse_hr_measurement(data)

async def main():
    transport = BleTransport(
        target_service_uuid=SERVICE_UUID,
        write_char_uuid=WRITE_CHAR_UUID,
        notify_char_uuid=NOTIFY_CHAR_UUID
    )

    connected = await transport.connect(timeout=15.0)
    if not connected:
        log.error("Failed to connect")
        return

    await transport.start_notify(on_notify)

    log.info("Listening for HR notifications. Press Ctrl+C to stop.")
    try:
        while transport.is_connected():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
    finally:
        await transport.stop_notify()
        await transport.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
