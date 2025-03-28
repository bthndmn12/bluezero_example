#!/usr/bin/env python3
from bluezero import peripheral
import struct
import logging
import signal
from multiparty_ble.checksum import compute_checksum, verify_checksum


from multiparty_ble.protocol import build_packet, parse_packet, PacketType, PacketFlags

# --- Configuration ---
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

# Update this with your Raspberry Pi’s BLE adapter MAC address.
ADAPTER_ADDR = "B8:27:EB:2F:D0:34" 

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

# Global peripheral instance
ble_peripheral = None

# Global buffer for reassembled data
received_data = bytearray()

def write_callback(value, options):
    global received_data
    log.info(f"Received {len(value)} bytes: {bytes(value).hex()}")
    try:
        packet_info = parse_packet(bytes(value))
        log.info(f"Parsed Packet: {packet_info}")

        pkt_type = packet_info["type"]

        if pkt_type == PacketType.DATA:
            received_data += packet_info["payload"]
            if PacketFlags.ACK_REQUIRED in packet_info["flags"]:
                log.info(f"ACK required for packet_id {packet_info['packet_id']}. Sending ACK.")
                ack_payload = struct.pack("<H", packet_info["packet_id"])
                ack_packet = build_packet(
                    packet_type=PacketType.ACK,
                    flags=PacketFlags.LAST_PACKET,
                    packet_id=0,
                    total_packets=1,
                    payload=ack_payload,
                )
                send_notification(ack_packet)

        elif pkt_type == PacketType.CHECKSUM:
            received_checksum = int.from_bytes(packet_info["payload"], byteorder="little")
            log.info(f"Received checksum packet: {received_checksum:#010x}")
            valid = verify_checksum(received_data, received_checksum)
            if valid:
                log.info("✅ Checksum valid. Data transfer successful.")
            else:
                log.error("❌ Checksum mismatch. Data may be corrupted.")
            received_data = bytearray()  # Reset buffer after validation

        else:
            log.warning(f"Unhandled packet type: {pkt_type}")

    except Exception as e:
        log.error(f"Error in write_callback: {e}")

def read_callback():
    """
    Callback for read requests on the NOTIFY characteristic.
    """
    log.info("Read request received (not implemented).")
    return bytearray(b"ReadNotSupported")
def send_notification(data: bytes):
    global ble_peripheral
    if ble_peripheral is None:
        log.error("Peripheral not initialized.")
        return
    try:
        notify_char = ble_peripheral.get_characteristic(NOTIFY_CHAR_UUID)
        if notify_char:
            notify_char.set_value(list(data))
            notify_char.send_notify()
            log.info(f"Notification sent ({len(data)} bytes).")
        else:
            log.error("Notify characteristic not found.")
    except Exception as e:
        log.error(f"Failed to send notification: {e}")

def main():
    global ble_peripheral
    log.info("Starting BLE peripheral using Bluezero...")

    if not ADAPTER_ADDR or ADAPTER_ADDR.startswith("XX"):
        log.error("ADAPTER_ADDR is not defined correctly. Please update it.")
        return

    try:
        ble_peripheral = peripheral.Peripheral(ADAPTER_ADDR, local_name="MultipartyPi")

        ble_peripheral.add_service(srv_id=1, uuid=SERVICE_UUID, primary=True)
        log.info(f"Added service {SERVICE_UUID}")

        ble_peripheral.add_characteristic(
            srv_id=1,
            chr_id=1,
            uuid=WRITE_CHAR_UUID,
            value=[],
            notifying=False,
            flags=['write', 'write-without-response'],
            write_callback=write_callback,
        )
        log.info(f"Added WRITE characteristic {WRITE_CHAR_UUID}")

        ble_peripheral.add_characteristic(
            srv_id=1,
            chr_id=2,
            uuid=NOTIFY_CHAR_UUID,
            value=[],
            notifying=False,
            flags=['notify', 'read'],
            read_callback=read_callback,
        )
        log.info(f"Added NOTIFY characteristic {NOTIFY_CHAR_UUID}")

        ble_peripheral.publish()
        log.info(f"Peripheral published and advertising as 'MultipartyPi' on {ADAPTER_ADDR}. Waiting for connections...")

        signal.pause()

    except KeyboardInterrupt:
        log.info("Peripheral stopping due to KeyboardInterrupt.")
    except Exception as e:
        log.error(f"Peripheral error: {e}", exc_info=True)
    finally:
        log.info("Peripheral cleanup complete.")

if __name__ == "__main__":
    main()



# #!/usr/bin/env python3
# from bluezero import peripheral
# import logging
# import signal
# from multiparty_ble.protocol import build_packet, parse_packet, PacketType, PacketFlags

# SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
# WRITE_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
# NOTIFY_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
# ADAPTER_ADDR = "B8:27:EB:2F:D0:34"

# logging.basicConfig(level=logging.INFO)
# log = logging.getLogger("server")

# ble_peripheral = None

# def write_callback(value, options):
#     log.info(f"Received {len(value)} bytes: {bytes(value).hex()}")
#     packet_info = parse_packet(bytes(value))
#     log.info(f"Parsed packet: {packet_info}")

#     if PacketFlags.ACK_REQUIRED in packet_info["flags"]:
#         ack_payload = struct.pack("<H", packet_info["packet_id"])
#         ack_packet = build_packet(PacketType.ACK, PacketFlags.LAST_PACKET, 0, 1, ack_payload)
#         send_notification(ack_packet)

# def send_notification(data: bytes):
#     global ble_peripheral
#     if ble_peripheral is None:
#         log.error("Peripheral not initialized.")
#         return
#     notify_char = ble_peripheral.get_characteristic(NOTIFY_CHAR_UUID)
#     if notify_char:
#         notify_char.set_value(list(data))
#         notify_char.send_notify()
#         log.info(f"Notification sent ({len(data)} bytes).")
#     else:
#         log.error("Notify characteristic not found.")

# def main():
#     global ble_peripheral
#     ble_peripheral = peripheral.Peripheral(ADAPTER_ADDR, local_name="MultipartyPi")

#     ble_peripheral.add_service(srv_id=1, uuid=SERVICE_UUID, primary=True)

#     # WRITE characteristic
#     ble_peripheral.add_characteristic(
#         srv_id=1,
#         chr_id=1,
#         uuid=WRITE_CHAR_UUID,
#         value=[],
#         notifying=False,  # explicitly required
#         flags=['write'],
#         write_callback=write_callback
#     )

#     # NOTIFY characteristic
#     ble_peripheral.add_characteristic(
#         srv_id=1,
#         chr_id=2,
#         uuid=NOTIFY_CHAR_UUID,
#         value=[],
#         notifying=False,  # explicitly required (managed manually)
#         flags=['notify']
#     )

#     ble_peripheral.publish()
#     log.info("Peripheral published and advertising...")
#     signal.pause()


# if __name__ == "__main__":
#     main()




# #!/usr/bin/env python3
# from bluezero import peripheral
# import struct
# import logging
# import signal

# from multiparty_ble.protocol import build_packet, parse_packet, PacketType, PacketFlags

# # --- Configuration ---
# SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
# WRITE_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
# NOTIFY_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

# # Update this with your Raspberry Pi’s BLE adapter MAC address.
# ADAPTER_ADDR = "B8:27:EB:2F:D0:34" 

# logging.basicConfig(level=logging.INFO)
# log = logging.getLogger("server")

# # Global peripheral instance
# ble_peripheral = None

# def write_callback(value, options):
#     """
#     Callback invoked when a write request is received on the WRITE characteristic.
#     """
#     log.info(f"Received {len(value)} bytes: {bytes(value).hex()}")
#     try:
#         packet_info = parse_packet(bytes(value))
#         log.info(f"Parsed Packet: {packet_info}")
#         # If the packet requests an ACK, build and send an ACK packet.
#         if PacketFlags.ACK_REQUIRED in packet_info["flags"]:
#             log.info(f"ACK required for packet_id {packet_info['packet_id']}. Sending ACK.")
#             ack_payload = struct.pack("<H", packet_info["packet_id"])
#             ack_packet = build_packet(
#                 packet_type=PacketType.ACK,
#                 flags=PacketFlags.LAST_PACKET,
#                 packet_id=0,
#                 total_packets=1,
#                 payload=ack_payload,
#             )
#             send_notification(ack_packet)
#     except Exception as e:
#         log.error(f"Error in write_callback: {e}")

# def read_callback():
#     """
#     Callback for read requests on the NOTIFY characteristic.
#     """
#     log.info("Read request received (not implemented).")
#     return bytearray(b"ReadNotSupported")

# def send_notification(data: bytes):
#     global ble_peripheral
#     if ble_peripheral is None:
#         log.error("Peripheral not initialized.")
#         return
#     try:
#         notify_char = ble_peripheral.get_characteristic(NOTIFY_CHAR_UUID)
#         if notify_char:
#             notify_char.set_value(list(data))
#             notify_char.send_notify()  # <-- explicitly send notification
#             log.info(f"Notification sent ({len(data)} bytes).")
#         else:
#             log.error("Notify characteristic not found.")
#     except Exception as e:
#         log.error(f"Failed to send notification: {e}")

# def main():
#     global ble_peripheral
#     log.info("Starting BLE peripheral using Bluezero...")

#     # --- Ensure ADAPTER_ADDR is correctly set ---
#     # (Keep the check from previous versions)
#     if 'ADAPTER_ADDR' not in globals() or ADAPTER_ADDR == "XX:XX:XX:XX:XX:XX" or ADAPTER_ADDR == "B8:27:EB:XX:XX:XX": # Refined check
#         log.error("ADAPTER_ADDR is not defined or not updated. Please define it globally with your actual adapter's MAC address found via 'hciconfig'.")
#         return

#     # Create peripheral object
#     try:
#         ble_peripheral = peripheral.Peripheral(ADAPTER_ADDR,
#                                                local_name="MultipartyPi")
#     except Exception as e:
#         log.error(f"Failed to initialize Peripheral: {e}", exc_info=True)
#         log.error("Ensure bluez service is running, the adapter address is correct, and the adapter is up ('sudo hciconfig hci0 up').")
#         return

#     # Add service
#     try:
#         ble_peripheral.add_service(srv_id=1, uuid=SERVICE_UUID, primary=True)
#         log.info(f"Added service {SERVICE_UUID} with srv_id=1")
#     except Exception as e:
#         log.error(f"Failed to add service: {e}", exc_info=True)
#         return

#     # Add WRITE characteristic
#     try:
#         ble_peripheral.add_characteristic(
#             srv_id=1,
#             chr_id=1,
#             uuid=WRITE_CHAR_UUID,
#             value=[],
#             notifying=False,
#             flags=['write', 'write-without-response'],
#             write_callback=write_callback,
#         )
#         log.info(f"Added WRITE characteristic {WRITE_CHAR_UUID} with chr_id=1 to srv_id=1")
#     except Exception as e:
#         log.error(f"Failed to add WRITE characteristic: {e}", exc_info=True)
#         return

#     # Add NOTIFY characteristic
#     try:
#         ble_peripheral.add_characteristic(
#             srv_id=1,
#             chr_id=2,
#             uuid=NOTIFY_CHAR_UUID,
#             value=[],
#             notifying=False,
#             flags=['notify'],
#             #read_callback=read_callback,
#         )
#         log.info(f"Added NOTIFY characteristic {NOTIFY_CHAR_UUID} with chr_id=2 to srv_id=1")
#     except Exception as e:
#         log.error(f"Failed to add NOTIFY characteristic: {e}", exc_info=True)
#         return

#     # --- Use publish() and remove stop() ---
#     log.info("Publishing BLE peripheral and starting advertisement...") # Updated log message
#     try:
#         # --- CORRECTED LINE ---
#         # Use publish() instead of start()
#         ble_peripheral.publish()
#         log.info(f"Peripheral published and advertising as 'MultipartyPi' on adapter {ADAPTER_ADDR}. Waiting for connections...")

#         # Keep the main thread alive using signal.pause() to wait for interrupts
#         signal.pause()

#     except KeyboardInterrupt:
#         log.info("Peripheral stopping due to KeyboardInterrupt.")
#     except Exception as e:
#         log.error(f"Error during peripheral operation: {e}", exc_info=True)
#     finally:
#         # --- CORRECTED BLOCK ---
#         # Remove the call to ble_peripheral.stop() as it doesn't exist
#         if ble_peripheral:
#             log.info("Cleaning up peripheral (automatic D-Bus unregister on exit)...")
#             # No explicit stop() method available
#         log.info("Peripheral script finished.") # Updated log message


# # --- Keep the rest of your code (imports, callbacks, ADAPTER_ADDR definition, etc.) ---

# if __name__ == "__main__":
#     main()