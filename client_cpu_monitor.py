#!/usr/bin/env python3
import asyncio
import logging
import argparse
import struct
import sys
from typing import Optional

# Bleak - BLE client library
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic

# --- Configuration ---
# These MUST match the server's UUIDs exactly
# Service UUID from the bluezero server
CPU_TMP_SRVC = '12341000-1234-1234-1234-123456789abc'
# Standard Bluetooth SIG adopted UUID for Temperature characteristic (used by server)
# Bleak generally requires the full 128-bit UUID for GATT operations
CPU_TMP_CHRC = '00002a6e-0000-1000-8000-00805f9b34fb'
# Optional: You can also define the server's advertised name for discovery fallback
SERVER_NAME = "CPU Monitor"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S' # Added date format
)
log = logging.getLogger("ble-client")

# --- Data Parsing ---
def parse_temperature(data: bytearray) -> Optional[float]:
    """
    Parses the 2-byte signed integer temperature value received from the
    CPU Monitor characteristic.
    Expected format: signed 16-bit little-endian integer representing Temp * 100.
    """
    if len(data) != 2:
        log.error(f"Received unexpected data length: {len(data)} bytes (expected 2)")
        return None
    try:
        # '<h' means little-endian signed short (16-bit integer)
        temp_value_times_100 = struct.unpack('<h', data)[0]
        # Divide by 100.0 to get the actual temperature
        return temp_value_times_100 / 100.0
    except (struct.error, TypeError) as e:
        log.error(f"Failed to parse temperature data: {data.hex()} - {e}")
        return None

# --- Callbacks ---
def handle_notification(characteristic: BleakGATTCharacteristic, data: bytearray):
    """Callback invoked by Bleak when a notification is received."""
    temperature = parse_temperature(data)
    if temperature is not None:
        log.info(f"NOTIFICATION: Temp = {temperature:.2f}°C")
    else:
        log.warning(f"Received notification with unparseable data: {data.hex()}")

def handle_disconnect(client: BleakClient):
    """Callback invoked by Bleak when the client disconnects."""
    log.warning(f"Disconnected from {client.address}")
    # You could trigger reconnection logic here if needed


# --- Main Client Logic ---
async def run_client(target_address: Optional[str], scan_timeout: float = 10.0, connect_timeout: float = 15.0):
    """Scans for, connects to, and interacts with the CPU Monitor peripheral."""
    target_device = None
    notify_characteristic_obj = None # To store the characteristic object

    log.info("Attempting to find the CPU Monitor device...")
    try:
        if target_address:
            # If address provided, try finding it directly first
            log.info(f"Trying to find device by address: {target_address}")
            target_device = await BleakScanner.find_device_by_address(
                target_address, timeout=scan_timeout
            )
            if not target_device:
                 log.warning(f"Device {target_address} not found directly.")

        if not target_device:
             # Scan using the specific service UUID
             log.info(f"Scanning for devices advertising service UUID: {CPU_TMP_SRVC}")
             # BleakScanner.discover returns a list, find_device_by_filter returns one or None
             target_device = await BleakScanner.find_device_by_filter(
                 lambda d, ad: CPU_TMP_SRVC in ad.service_uuids,
                 timeout=scan_timeout
             )
             if target_device:
                 log.info(f"Found device by service UUID: '{target_device.name}' ({target_device.address})")
             else:
                 # Fallback: Scan by name
                 log.warning(f"Could not find device by service UUID {CPU_TMP_SRVC}.")
                 log.info(f"Scanning for device named '{SERVER_NAME}'...")
                 target_device = await BleakScanner.find_device_by_name(
                     SERVER_NAME, timeout=scan_timeout
                 )
                 if target_device:
                     log.info(f"Found device by name: '{target_device.name}' ({target_device.address})")

        if not target_device:
            log.error("Could not find the CPU Monitor device. Ensure it's running and advertising.")
            return

    except BleakError as e:
        log.error(f"Error during scanning: {e}")
        return
    except Exception as e:
        log.error(f"Unexpected error during scanning: {e}", exc_info=True)
        return

    # --- Connect ---
    log.info(f"Connecting to {target_device.name or 'device'} ({target_device.address})...")
    # Use 'async with' for automatic disconnection handling
    async with BleakClient(
        target_device.address,
        disconnected_callback=handle_disconnect,
        timeout=connect_timeout
    ) as client:
        try:
            log.info(f"Connected successfully: {client.is_connected}")

            # It's often good practice to wait briefly for services to resolve
            await asyncio.sleep(1.0)

            # --- Find the Target Characteristic ---
            log.info(f"Looking for characteristic {CPU_TMP_CHRC}...")
            # Iterate through services to find the characteristic
            for service in client.services:
                if service.uuid.lower() == CPU_TMP_SRVC.lower():
                    log.info(f"Found service {service.uuid}")
                    for char in service.characteristics:
                        if char.uuid.lower() == CPU_TMP_CHRC.lower():
                            notify_characteristic_obj = char
                            log.info(f"Found characteristic {char.uuid} (Handle: {char.handle})")
                            break # Stop searching once found
                if notify_characteristic_obj:
                    break # Stop searching services

            if not notify_characteristic_obj:
                log.error(f"Characteristic {CPU_TMP_CHRC} not found within service {CPU_TMP_SRVC}!")
                log.error("Available services and characteristics:")
                for service in client.services:
                     log.error(f"  Service: {service.uuid}")
                     for char in service.characteristics:
                         log.error(f"    Char: {char.uuid}")
                return # Exit if characteristic not found

            # Check properties
            if "read" not in notify_characteristic_obj.properties:
                 log.error(f"Characteristic {CPU_TMP_CHRC} does not support 'read'!")
                 # Continue to try notifications if supported
            if "notify" not in notify_characteristic_obj.properties:
                 log.error(f"Characteristic {CPU_TMP_CHRC} does not support 'notify'!")
                 return # Exit if notifications aren't supported

            # --- Read Initial Value ---
            if "read" in notify_characteristic_obj.properties:
                log.info(f"Attempting to read initial temperature...")
                try:
                    value_bytes = await client.read_gatt_char(notify_characteristic_obj.uuid)
                    temperature = parse_temperature(value_bytes)
                    if temperature is not None:
                        log.info(f"Initial Temperature read: {temperature:.2f}°C")
                except BleakError as e:
                    log.error(f"Failed to read characteristic: {e}")
                except Exception as e:
                    log.error(f"Error processing read value: {e}", exc_info=True)

            # --- Subscribe to Notifications ---
            if "notify" in notify_characteristic_obj.properties:
                log.info(f"Subscribing to temperature notifications...")
                try:
                    await client.start_notify(
                        notify_characteristic_obj.uuid,
                        handle_notification
                    )
                    log.info("Successfully subscribed. Waiting for notifications... (Press Ctrl+C to exit)")

                    # Keep the script running to receive notifications
                    while client.is_connected:
                        await asyncio.sleep(1.0) # Keep main task alive

                except BleakError as e:
                    log.error(f"Failed to start notifications: {e}")
                except Exception as e:
                    log.error(f"Error during notification handling: {e}", exc_info=True)
                finally:
                    # Attempt to stop notifications before exiting the 'with' block
                    # Check if still connected before trying to stop
                    if client.is_connected:
                        log.info("Stopping notifications...")
                        try:
                            await client.stop_notify(notify_characteristic_obj.uuid)
                        except BleakError as e:
                            log.warning(f"Failed to stop notifications cleanly: {e}")
            else:
                 log.warning("Notifications not supported by characteristic. Exiting.")


        except BleakError as e:
            log.error(f"Bluetooth connection error: {e}")
        except Exception as e:
            log.error(f"An unexpected error occurred: {e}", exc_info=True)

    log.info("Client has disconnected.")


# --- Script Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bleak Client for Bluezero CPU Monitor Peripheral"
    )
    parser.add_argument(
        "-a", "--address",
        type=str,
        help=f"Optional Bluetooth address of the target device (e.g., B8:27:EB:2F:D0:34)"
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_client(target_address=args.address))
    except KeyboardInterrupt:
        log.info("Process interrupted by user.")
    except Exception as e:
        # Catch any other unexpected exceptions during setup/shutdown
        log.error(f"Unhandled exception occurred: {e}", exc_info=True)