# multiparty_ble/client.py

import asyncio
import logging
import argparse
from multiparty_ble.transport import BleTransport
from multiparty_ble.protocol import (
    build_packet,
    parse_packet,
    PacketType,
    PacketFlags
)

TARGET_DEVICE_ADDRESS = None
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("client")

def on_data_received(data: bytearray):
    log.info(f"Received {len(data)} bytes raw: {data.hex()}")
    try:
        packet_info = parse_packet(bytes(data))
        log.info(f"Parsed Packet: {packet_info}")
    except ValueError as e:
        log.error(f"Failed to parse received packet: {e}")
    except Exception as e:
        log.error(f"Error processing received data: {e}")

def on_disconnected():
    log.warning("Connection lost.")


async def main(device_address: str | None):
    log.info("Starting BLE client...")
    transport = BleTransport(
        target_service_uuid=SERVICE_UUID,
        write_char_uuid=WRITE_CHAR_UUID,
        notify_char_uuid=NOTIFY_CHAR_UUID
    )
    transport.set_disconnect_callback(on_disconnected)

    # DO NOT PUT THE LOGGING BLOCK HERE

    try:
        log.info(f"Attempting to connect to {device_address or 'discovered device'}...")
        connected = await transport.connect(device_address=device_address, timeout=20.0)

        if not connected:
            log.error("Could not establish connection. Exiting.")
            return

        log.info("Connection established. Waiting a moment for service discovery...")
        await asyncio.sleep(2.0) # Wait after connecting

        # --- CORRECT PLACEMENT FOR LOGGING BLOCK ---
        log.info("--- Discovering Services & Characteristics ---")
        if transport._client and transport._client.is_connected:
            try:
                log.info("Listing services found by Bleak:")
                for service in transport._client.services:
                     log.info(f"  [Service] UUID: {service.uuid}, Handle: {service.handle}")
                     try:
                         for char in service.characteristics:
                             log.info(f"    [Characteristic] UUID: {char.uuid}, Handle: {char.handle}, Properties: {char.properties}")
                     except Exception as e:
                         log.error(f"    Error listing characteristics for service {service.uuid}: {e}")
            except Exception as e:
                log.error(f"  Error during service discovery iteration: {e}")
        else:
            # This warning shouldn't appear if placed here after a successful connection
            log.warning("  Client not connected or valid for service listing (unexpected).")
        log.info("--- End of Discovery Listing ---")
        # --- END LOGGING BLOCK ---

        log.info("Subscribing to notifications...") # Now attempt subscription
        try:
            await transport.start_notify(on_data_received)
        except Exception as e:
            log.error(f"Error during subscription: {e}")
            await transport.disconnect()
            return



        log.info("Sending a test DATA packet...")
        payload = b"Hello from client!"
        test_packet = build_packet(
            packet_type=PacketType.DATA,
            flags=PacketFlags.NONE,
            packet_id=1,
            total_packets=1,
            payload=payload
        )

        try:
            await transport.write_data(test_packet, with_response=False)
            log.info(f"Sent test packet ({len(test_packet)} bytes).")
        except Exception as e:
            log.error(f"Error sending test packet: {e}")

        log.info("Client running. Waiting for notifications or disconnect... (Press Ctrl+C to exit)")
        while transport.is_connected():
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        log.info("Client task cancelled.")
    except Exception as e:
        log.error(f"An unexpected error occurred in main loop: {e}")
    finally:
        log.info("Cleaning up...")
        if transport.is_connected():
            try:
                log.info("Stopping notifications...")
                await transport.stop_notify()
            except Exception as e:
                log.error(f"Error stopping notifications: {e}")
            log.info("Disconnecting...")
            await transport.disconnect()
        log.info("Client stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multiparty BLE Client")
    parser.add_argument(
        "-a", "--address",
        type=str,
        default=TARGET_DEVICE_ADDRESS,
        help="Target BLE device address (e.g., XX:XX:XX:XX:XX:XX)"
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.address))
    except KeyboardInterrupt:
        log.info("Process interrupted by user.")
