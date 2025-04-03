#!/usr/bin/env python3
import logging
import signal
import struct
import time
import sys # Import sys for platform check

from bluezero import peripheral
# Assuming multiparty_ble is in the same directory or installed
try:
    from multiparty_ble.protocol import build_packet, parse_packet, PacketType, PacketFlags
except ImportError:
    print("Error: 'multiparty_ble' module not found.")
    print("Ensure 'protocol.py' is in the same directory or the package is installed.")
    sys.exit(1)

# --- Configuration ---
# Using standardized 16-bit UUIDs for better BlueZero compatibility
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"  # Full UUID format
WRITE_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

# !!! CRITICAL: Update this with your Raspberry Pi's actual BLE adapter MAC address !!!
# Find it using `hciconfig` in the terminal. Don't leave the placeholder.
ADAPTER_ADDR = "B8:27:EB:2F:D0:34" # <-- Make sure this is correct!

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger("ble-server")

# --- Global State ---
ble_peripheral = None
notify_characteristic = None # Store notify characteristic globally for easier access

# --- Callbacks ---
def write_callback(value, options):
    """Callback for WRITE characteristic write requests."""
    device_address = options.get('device', 'unknown device')
    log.info(f"Write request received from {device_address}: {len(value)} bytes: {bytes(value).hex()}")
    try:
        packet_info = parse_packet(bytes(value))
        log.info(f"Parsed Packet: Type={packet_info['type'].name}, Flags={packet_info['flags']}, ID={packet_info['packet_id']}, Total={packet_info['total_packets']}, Payload Len={len(packet_info['payload'])}")

        # If the packet requires an ACK, build and send an ACK packet.
        if PacketFlags.ACK_REQUIRED in packet_info["flags"]:
            log.info(f"ACK required for packet_id {packet_info['packet_id']}. Sending ACK.")
            # ACK payload contains the packet ID being acknowledged
            ack_payload = struct.pack("<H", packet_info["packet_id"])
            ack_packet = build_packet(
                packet_type=PacketType.ACK,
                flags=PacketFlags.LAST_PACKET, # ACK is always a single packet
                packet_id=0, # ACK itself doesn't need an ID usually, or use a dedicated counter
                total_packets=1,
                payload=ack_payload,
            )
            send_notification(ack_packet)
        else:
            log.info("No ACK required for this packet.")

    except ValueError as e:
        log.error(f"Failed to parse packet: {e}")
    except Exception as e:
        log.error(f"Error processing write_callback: {e}", exc_info=True)

def read_callback():
    """Callback for read requests on the NOTIFY characteristic (optional)."""
    log.info("Read request received on Notify characteristic (returning empty).")
    return [] # Return empty list or specific value if needed

def on_connect(device_address):
    """Callback when a device connects."""
    log.info(f"Device connected: {device_address}")

def on_disconnect(device_address):
    """Callback when a device disconnects."""
    log.info(f"Device disconnected: {device_address}")

# --- Notification Function ---
def send_notification(data: bytes):
    """Sends data via the NOTIFY characteristic."""
    global notify_characteristic
    if notify_characteristic is None:
        log.error("Notify characteristic not available or peripheral not ready.")
        return
    try:
        # Bluezero expects a list of integers for the value
        value_list = list(data)
        notify_characteristic.set_value(value_list)
        log.info(f"Notification value set ({len(data)} bytes): {data.hex()}")
    except Exception as e:
        log.error(f"Failed to set notification value: {e}", exc_info=True)

# --- Main Function ---
def main():
    global ble_peripheral, notify_characteristic

    log.info("Starting BLE peripheral using Bluezero...")

    # --- Critical Check: Adapter Address ---
    if not ADAPTER_ADDR or ADAPTER_ADDR == "XX:XX:XX:XX:XX:XX" or ADAPTER_ADDR == "00:00:00:00:00:00":
        log.error("---------------------------------------------------------")
        log.error("CRITICAL: ADAPTER_ADDR is not set or is a placeholder!")
        log.error(f"          Current value: '{ADAPTER_ADDR}'")
        log.error("          Please edit the script and set ADAPTER_ADDR")
        log.error("          to your Raspberry Pi's Bluetooth MAC address.")
        log.error("          Find it using the command: `hciconfig`")
        log.error("---------------------------------------------------------")
        return

    # --- Check Platform ---
    if not sys.platform.startswith('linux'):
        log.error("Bluezero library is designed for Linux (typically Raspberry Pi with BlueZ).")
        log.error("This script might not work correctly on other operating systems.")

    # --- Ensure Bluetooth is Ready ---
    try:
        # Check BlueZ version
        import subprocess
        result = subprocess.run(['bluetoothd', '-v'], stdout=subprocess.PIPE, text=True)
        log.info(f"BlueZ version: {result.stdout.strip()}")
        
        # Run hciconfig to check Bluetooth status
        result = subprocess.run(['hciconfig'], stdout=subprocess.PIPE, text=True)
        log.info(f"Bluetooth adapter status:\n{result.stdout}")
        
        # Check if experimental features are enabled
        result = subprocess.run(['ps', '-ef'], stdout=subprocess.PIPE, text=True)
        if '--experimental' not in result.stdout:
            log.warning("BlueZ experimental features may not be enabled.")
            log.warning("For local GATT server support, edit /lib/systemd/system/bluetooth.service")
            log.warning("and add --experimental to ExecStart line, then restart bluetooth service.")
        
        # Minimal Bluetooth setup - avoid extensive manual configuration
        # Just ensure the adapter is up and unblocked
        subprocess.run(['sudo', 'rfkill', 'unblock', 'bluetooth'], check=False)
        
        # Verify final adapter status
        result = subprocess.run(['hciconfig', 'hci0'], stdout=subprocess.PIPE, text=True)
        log.info(f"Final adapter status:\n{result.stdout}")
        
    except Exception as e:
        log.warning(f"Could not check/reset Bluetooth adapter: {e}")

    # --- Initialize Peripheral ---
    try:
        log.info(f"Initializing Peripheral on adapter: {ADAPTER_ADDR}")
        
        # Initialize peripheral with correct parameter names
        ble_peripheral = peripheral.Peripheral(
            adapter_address=ADAPTER_ADDR,  # Changed from adapter_addr to adapter_address
            local_name="MultipartyPi",
            appearance=0x0000  # Generic appearance
        )

        # Register connection/disconnection callbacks
        ble_peripheral.on_connect = on_connect
        ble_peripheral.on_disconnect = on_disconnect

        # Configure advertisement with explicit service UUID
        log.info("Configuring advertisement...")
        ble_peripheral.advert.local_name = "MultipartyPi"
        ble_peripheral.advert.service_UUIDs = [SERVICE_UUID]
        ble_peripheral.advert.discoverable = True
        
        # Add service with full UUID
        log.info(f"Adding service: {SERVICE_UUID}")
        srv_id = 1
        ble_peripheral.add_service(
            srv_id=srv_id,
            uuid=SERVICE_UUID,
            primary=True
        )
        
        # Ensure service UUID is in primary services
        if SERVICE_UUID not in ble_peripheral.primary_services:
            ble_peripheral.primary_services.append(SERVICE_UUID)
        
        # Add write characteristic with explicit configuration
        log.info(f"Adding WRITE characteristic: {WRITE_CHAR_UUID}")
        write_char = ble_peripheral.add_characteristic(
            srv_id=srv_id,
            chr_id=1,
            uuid=WRITE_CHAR_UUID,
            value=[],
            notifying=False,
            flags=['write', 'write-without-response'],
            write_callback=write_callback,
            read_callback=None  # No read callback needed for write characteristic
        )
        
        # Add notify characteristic with explicit configuration
        log.info(f"Adding NOTIFY characteristic: {NOTIFY_CHAR_UUID}")
        notify_characteristic = ble_peripheral.add_characteristic(
            srv_id=srv_id,
            chr_id=2,
            uuid=NOTIFY_CHAR_UUID,
            value=[0],  # Initial value
            notifying=True,
            flags=['notify', 'read'],  # Add read flag for compatibility
            write_callback=None,  # No write callback needed for notify characteristic
            read_callback=read_callback
        )

        # Print registered characteristics and verify their properties
        log.info("Registered characteristics:")
        for char in ble_peripheral.characteristics:
            log.info(f"  Characteristic: {char}")
            # Get characteristic path which contains the UUID info
            char_path = str(char)
            log.info(f"    Path: {char_path}")
            log.info(f"    Flags: {char.flags if hasattr(char, 'flags') else 'N/A'}")
            log.info(f"    Properties: {[prop for prop in dir(char) if not prop.startswith('_')]}")

        # Start advertising
        log.info("Publishing peripheral...")
        ble_peripheral.publish()
        
        log.info(f"Server running. Waiting for connections on {ADAPTER_ADDR}...")
        
        # Keep the main thread alive
        signal.pause()

    except Exception as e:
        log.error(f"Error during peripheral setup: {e}", exc_info=True)
    finally:
        log.info("Cleaning up...")
        if ble_peripheral:
            log.info("Peripheral resources will be released by D-Bus upon script exit.")
        log.info("Server script finished.")

# --- Script Entry Point ---
if __name__ == "__main__":
    main()