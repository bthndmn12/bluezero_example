import asyncio
import logging
import zlib
import time
import argparse
from multiparty_ble.transport import BleTransport
from multiparty_ble.checksum import compute_checksum
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

MAX_IN_FLIGHT = 5  # Sliding window size
COMPRESSION_THRESHOLD = 64  # Compress if payload is bigger than this (bytes)

async def optimized_transfer(transport: BleTransport, data: bytes):
    mtu = await transport.get_mtu()
    max_payload = mtu - 7  # HEADER_SIZE = 7

    log.info(f"MTU: {mtu}, max payload size: {max_payload}")

    # Optional compression
    if len(data) > COMPRESSION_THRESHOLD:
        compressed = zlib.compress(data)
        if len(compressed) < len(data):
            data = compressed
            flags = PacketFlags.COMPRESSED
            log.info(f"Payload compressed to {len(data)} bytes.")
        else:
            flags = PacketFlags.NONE
    else:
        flags = PacketFlags.NONE

    # Split data into packets
    packets = []
    total_packets = (len(data) + max_payload - 1) // max_payload
    for i in range(total_packets):
        start = i * max_payload
        end = min(start + max_payload, len(data))
        chunk = data[start:end]

        pkt_flags = flags
        if i == total_packets - 1:
            pkt_flags |= PacketFlags.LAST_PACKET
        if (i + 1) % MAX_IN_FLIGHT == 0:
            pkt_flags |= PacketFlags.ACK_REQUIRED

        packet = build_packet(
            packet_type=PacketType.DATA,
            flags=pkt_flags,
            packet_id=i + 1,
            total_packets=total_packets,
            payload=chunk
        )
        packets.append(packet)

    # Send packets with sliding window
    sent_count = 0
    start_time = time.time()
    for pkt in packets:
        await transport.write_data(pkt, with_response=False)
        sent_count += 1
        log.info(f"Sent packet {sent_count}/{total_packets}")
        await asyncio.sleep(0.01)  # Optional small delay to avoid buffer overflow

    # Send checksum packet at the end
    checksum = compute_checksum(data)
    checksum_payload = checksum.to_bytes(4, byteorder="little")
    checksum_packet = build_packet(
        packet_type=PacketType.CHECKSUM,
        flags=PacketFlags.LAST_PACKET,
        packet_id=0,
        total_packets=1,
        payload=checksum_payload
    )
    await transport.write_data(checksum_packet, with_response=False)
    log.info(f"Sent checksum packet: {checksum:#010x}")

    elapsed = time.time() - start_time
    throughput = len(data) / elapsed
    log.info(f"Transfer complete. Time: {elapsed:.2f}s, Throughput: {throughput:.2f} bytes/s")

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

    try:
        log.info(f"Attempting to connect to {device_address or 'discovered device'}...")
        connected = await transport.connect(device_address=device_address, timeout=20.0, adapter = 'hci0')

        if not connected:
            log.error("Could not establish connection. Exiting.")
            return

        log.info("Connection established. Waiting a moment for service discovery...")
        await asyncio.sleep(2.0)

        log.info("Subscribing to notifications...")
        try:
            await transport.start_notify(on_data_received)
        except Exception as e:
            log.error(f"Error during subscription: {e}")
            await transport.disconnect()
            return

        log.info("Sending an optimized test transfer...")
        test_data = b"Hello from client! " * 10
        await optimized_transfer(transport, test_data)

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



# # multiparty_ble/client.py

# import asyncio
# import logging
# import argparse
# from multiparty_ble.transport import BleTransport
# from multiparty_ble.protocol import (
#     build_packet,
#     parse_packet,
#     PacketType,
#     PacketFlags
# )

# TARGET_DEVICE_ADDRESS = None
# SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
# WRITE_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
# NOTIFY_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

# logging.basicConfig(level=logging.INFO)
# log = logging.getLogger("client")

# def on_data_received(data: bytearray):
#     log.info(f"Received {len(data)} bytes raw: {data.hex()}")
#     try:
#         packet_info = parse_packet(bytes(data))
#         log.info(f"Parsed Packet: {packet_info}")
#     except ValueError as e:
#         log.error(f"Failed to parse received packet: {e}")
#     except Exception as e:
#         log.error(f"Error processing received data: {e}")

# def on_disconnected():
#     log.warning("Connection lost.")

# async def main(device_address: str | None):
#     log.info("Starting BLE client...")
#     transport = BleTransport(
#         target_service_uuid=SERVICE_UUID,
#         write_char_uuid=WRITE_CHAR_UUID,
#         notify_char_uuid=NOTIFY_CHAR_UUID
#     )
#     transport.set_disconnect_callback(on_disconnected)

#     try:
#         log.info(f"Attempting to connect to {device_address or 'discovered device'}...")
#         connected = await transport.connect(device_address=device_address, timeout=20.0)

#         if not connected:
#             log.error("Could not establish connection. Exiting.")
#             return

#         log.info("Connection established. Waiting a moment for service discovery...")
#         await asyncio.sleep(2.0) # <--- ADD THIS DELAY (e.g., 2 seconds)

#         log.info("Subscribing to notifications...")
#         try:
#             await transport.start_notify(on_data_received) # Now try subscribing
#         except Exception as e:
#             log.error(f"Error during subscription: {e}") # Add specific logging here
#             # Maybe handle the error more gracefully or log more details
#             # Consider disconnecting if subscription fails critically
#             await transport.disconnect()
#             return


#         log.info("Sending a test DATA packet...")
#         payload = b"Hello from client!"
#         test_packet = build_packet(
#             packet_type=PacketType.DATA,
#             flags=PacketFlags.NONE,
#             packet_id=1,
#             total_packets=1,
#             payload=payload
#         )

#         try:
#             await transport.write_data(test_packet, with_response=False)
#             log.info(f"Sent test packet ({len(test_packet)} bytes).")
#         except Exception as e:
#             log.error(f"Error sending test packet: {e}")

#         log.info("Client running. Waiting for notifications or disconnect... (Press Ctrl+C to exit)")
#         while transport.is_connected():
#             await asyncio.sleep(1)

#     except asyncio.CancelledError:
#         log.info("Client task cancelled.")
#     except Exception as e:
#         log.error(f"An unexpected error occurred in main loop: {e}")
#     finally:
#         log.info("Cleaning up...")
#         if transport.is_connected():
#             try:
#                 log.info("Stopping notifications...")
#                 await transport.stop_notify()
#             except Exception as e:
#                 log.error(f"Error stopping notifications: {e}")
#             log.info("Disconnecting...")
#             await transport.disconnect()
#         log.info("Client stopped.")

# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Multiparty BLE Client")
#     parser.add_argument(
#         "-a", "--address",
#         type=str,
#         default=TARGET_DEVICE_ADDRESS,
#         help="Target BLE device address (e.g., XX:XX:XX:XX:XX:XX)"
#     )
#     args = parser.parse_args()

#     try:
#         asyncio.run(main(args.address))
#     except KeyboardInterrupt:
#         log.info("Process interrupted by user.")
