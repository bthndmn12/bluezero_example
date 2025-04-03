#!/usr/bin/env python3
import asyncio
import logging
import argparse
import sys
import struct
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

# Assuming multiparty_ble is in the same directory or installed
try:
    from multiparty_ble.protocol import build_packet, parse_packet, PacketType, PacketFlags
except ImportError:
    print("Error: 'multiparty_ble' module not found.")
    print("Ensure 'protocol.py' and 'transport.py' are in the same directory or the package is installed.")
    sys.exit(1)
# Assuming BleTransport uses bleak internally
try:
    from multiparty_ble.transport import BleTransport # Assuming this wraps BleakClient
except ImportError:
     print("Error: 'BleTransport' not found in 'multiparty_ble.transport'.")
     print("Ensure 'transport.py' exists and is correct.")
     sys.exit(1)


# --- Configuration ---
# Server uses 16-bit UUIDs but we need full UUIDs for BLE operations
SERVICE_UUID_SHORT = "FF00"  # For discovery/advertising
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"  # For GATT operations
WRITE_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
MAX_RETRIES = 3  # Maximum number of connection retries

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger("ble-client")

# --- Global State ---
client_transport = None # Hold the transport instance

# --- Callbacks ---
def handle_notification(sender: int, data: bytearray):
    """Callback invoked when a notification is received."""
    log.info(f"Notification received from handle {sender}: {len(data)} bytes: {data.hex()}")
    try:
        packet_info = parse_packet(bytes(data))
        log.info(f"Parsed Packet: Type={packet_info['type'].name}, Flags={packet_info['flags']}, ID={packet_info['packet_id']}, Total={packet_info['total_packets']}, Payload Len={len(packet_info['payload'])}")

        # --- Example: Handle ACK ---
        if packet_info['type'] == PacketType.ACK:
             # Payload should contain the original packet ID being ACKed
             original_packet_id = struct.unpack("<H", packet_info['payload'])[0]
             log.info(f"Received ACK for packet ID {original_packet_id}")
        # --- End Example ---

    except ValueError as e:
        log.error(f"Failed to parse received packet: {e}")
    except Exception as e:
        log.error(f"Error processing notification data: {e}", exc_info=True)

def handle_disconnect(client: BleakClient):
    """Callback invoked when the client disconnects."""
    # Note: BleakClient is passed directly here
    log.warning(f"Disconnected from {client.address}")
    # You might want to trigger reconnection logic here if desired
    # asyncio.create_task(main(client.address)) # Example: Simple reconnect attempt

# --- Main Client Logic ---
async def try_connect_with_retry(client, timeout=10.0, max_retries=MAX_RETRIES):
    """Attempt to connect with retries and different address types."""
    last_error = None
    address_types = ["public", "random"]  # Try both address types
    
    for address_type in address_types:
        retries = 0
        while retries < max_retries:
            try:
                log.info(f"Connection attempt {retries + 1}/{max_retries} with address_type={address_type}")
                client._address_type = address_type
                await client.connect(timeout=timeout)
                log.info(f"Successfully connected using address_type={address_type}")
                return True
            except asyncio.TimeoutError:
                log.warning(f"Connection attempt timed out with address_type={address_type}")
                last_error = "Timeout"
            except BleakError as e:
                log.warning(f"BleakError during connection with address_type={address_type}: {e}")
                last_error = str(e)
            except Exception as e:
                log.warning(f"Unexpected error during connection with address_type={address_type}: {e}")
                last_error = str(e)
            
            retries += 1
            if retries < max_retries:
                delay = min(2 ** retries, 10)  # Exponential backoff, max 10 seconds
                log.info(f"Waiting {delay} seconds before retry...")
                await asyncio.sleep(delay)
    
    log.error(f"Failed to connect after all retries. Last error: {last_error}")
    return False

async def run_client(device_address: str | None, address_type: str = "public"):
    global client_transport
    target_device = None
    services_discovered = False
    target_service = None
    target_write = None
    target_notify = None

    # --- Discovery ---
    if not device_address:
        log.info("No device address provided. Scanning for devices advertising the service...")
        try:
            # Try both short and full UUIDs during scanning
            discovered_devices = []
            for uuid in [SERVICE_UUID_SHORT, SERVICE_UUID]:
                devices = await BleakScanner.discover(
                    service_uuids=[uuid],
                    timeout=10.0
                )
                discovered_devices.extend([d for d in devices if d not in discovered_devices])
                
            if not discovered_devices:
                log.error(f"Could not find any devices advertising service {SERVICE_UUID_SHORT} or {SERVICE_UUID}")
                log.error("Ensure the server is running and advertising.")
                return
                
            # Select the first discovered device matching the service
            target_device = discovered_devices[0]
            device_address = target_device.address
            log.info(f"Found device '{target_device.name}' ({target_device.address})")
            
            # Print advertisement data for debugging
            if hasattr(target_device, 'metadata'):
                log.info("Device metadata:")
                for key, value in target_device.metadata.items():
                    log.info(f"  {key}: {value}")
                    
        except BleakError as e:
            log.error(f"Error during scanning: {e}")
            return
        except Exception as e:
            log.error(f"Unexpected error during scanning: {e}", exc_info=True)
            return
    else:
        log.info(f"Attempting to connect directly to address: {device_address}")

        # Scan for the device first to verify it's advertising
        try:
            log.info("Scanning for device...")
            discovered = False
            scanner = BleakScanner()
            scan_result = await scanner.discover(timeout=5.0)
            for device in scan_result:
                adv_data = getattr(device, "advertisement_data", None)
                if device.address.upper() == device_address.upper():
                    discovered = True
                    target_device = device
                    log.info(f"Found target device: {device.name} ({device.address})")
                    if adv_data and hasattr(adv_data, "service_uuids") and adv_data.service_uuids:
                        log.info(f"Advertised services: {adv_data.service_uuids}")
                        # Check if our desired service is in the advertised services
                        if SERVICE_UUID_SHORT in adv_data.service_uuids:
                            log.info(f"Device is advertising our target service: {SERVICE_UUID_SHORT}")
                    break
            
            if not discovered:
                log.warning("Target device not found in scan. Connection may still succeed...")
        except Exception as e:
            log.warning(f"Error during device scanning: {e}")

    # --- Initialize Client ---
    client = BleakClient(
        device_address, 
        disconnected_callback=handle_disconnect,
        address_type=address_type
    )

    try:
        # --- Connect with retry logic ---
        connected = await try_connect_with_retry(client)
        if not connected:
            return

        # --- Wait for services to be ready ---
        log.info("Connected. Waiting for services to be discovered...")
        await asyncio.sleep(2.0)  # Give time for service discovery

        # --- Discover and Verify Services ---
        log.info("\n=== Discovering Services & Characteristics ===")

        # Try a few times if service discovery initially fails
        attempts = 0
        services_discovered = False
        while attempts < 3 and not services_discovered:
            # Check if services exist and are populated without using len()
            services_list = list(client.services) if client.services else []
            if services_list:
                services_discovered = True
                log.info(f"Services discovered successfully on attempt {attempts+1}")
            else:
                log.info(f"No services found yet, attempt {attempts+1}/3... waiting")
                await asyncio.sleep(2.0)  # longer wait between attempts
                attempts += 1

        log.info(f"All available services on device {device_address}:")
        # Check if services exist without using len()
        services_list = list(client.services) if client.services else []
        if not services_list:
            log.error("No services discovered after multiple attempts!")
            log.error("This usually means BlueZ experimental features aren't enabled.")
            log.error("Add '--experimental' to 'ExecStart=/usr/lib/bluetooth/bluetoothd' in")
            log.error("/lib/systemd/system/bluetooth.service and restart the bluetooth service.")
            await client.disconnect()
            return

        # Service discovery was successful, print details
        for service in client.services:
            log.info(f"\nService: {service.uuid}")
            log.info(f"  Handle: {service.handle}")
            
            # Check both 16-bit and 128-bit versions of the service UUID
            if (service.uuid.lower() == SERVICE_UUID.lower() or
                service.uuid.lower().endswith(SERVICE_UUID_SHORT.lower())):
                log.info("  ^ Found target service!")
                target_service = service
            
            # Print all characteristics
            if service.characteristics:
                log.info("  Characteristics:")
                for char in service.characteristics:
                    log.info(f"    Characteristic: {char.uuid}")
                    log.info(f"      Handle: {char.handle}")
                    log.info(f"      Properties: {char.properties}")
                    
                    # If this is our target service, look for specific characteristics
                    if (service.uuid.lower() == SERVICE_UUID.lower() or 
                        service.uuid.lower().endswith(SERVICE_UUID_SHORT.lower())):
                        # Check for WRITE characteristic 
                        if (char.uuid.lower() == WRITE_CHAR_UUID.lower() or
                            char.uuid.lower().endswith(WRITE_CHAR_UUID[-4:].lower())):
                            log.info("      ^ Found Write characteristic!")
                            target_write = char
                        # Check for NOTIFY characteristic
                        elif (char.uuid.lower() == NOTIFY_CHAR_UUID.lower() or
                              char.uuid.lower().endswith(NOTIFY_CHAR_UUID[-4:].lower())):
                            log.info("      ^ Found Notify characteristic!")
                            target_notify = char
        
        # Verify all required components were found
        if not target_service:
            log.error(f"Target service not found!")
            log.error(f"Expected: {SERVICE_UUID} or ending with {SERVICE_UUID_SHORT}")
            log.error("Services found:")
            for service in client.services:
                log.error(f"  {service.uuid}")
            await client.disconnect()
            return
            
        if not target_write:
            log.error(f"Write characteristic not found!")
            log.error(f"Expected: {WRITE_CHAR_UUID} or ending with {WRITE_CHAR_UUID[-4:]}")
            await client.disconnect()
            return
            
        if not target_notify:
            log.error(f"Notify characteristic not found!")
            log.error(f"Expected: {NOTIFY_CHAR_UUID} or ending with {NOTIFY_CHAR_UUID[-4:]}")
            await client.disconnect()
            return
        
        # Verify properties
        if 'write-without-response' not in target_write.properties and 'write' not in target_write.properties:
            log.error("Write characteristic doesn't have required properties!")
            await client.disconnect()
            return
            
        if 'notify' not in target_notify.properties:
            log.error("Notify characteristic doesn't have required properties!")
            await client.disconnect()
            return
            
        log.info("\n=== Service Discovery Successful! All components verified. ===")
        
        # --- Subscribe to Notifications ---
        log.info(f"Subscribing to notifications on {target_notify.uuid}...")
        try:
            await client.start_notify(target_notify.uuid, handle_notification)
            log.info("Successfully subscribed to notifications.")
        except Exception as e:
            log.error(f"Failed to subscribe to notifications: {e}", exc_info=True)
            await client.disconnect()
            return
            
        # Small delay to ensure subscription is ready
        await asyncio.sleep(1.0)
        
        # --- Send Test Packet ---
        log.info("Sending test packet...")
        test_payload = b"Hello from client!"
        test_packet = build_packet(
            packet_type=PacketType.DATA,
            flags=PacketFlags.ACK_REQUIRED,
            packet_id=1,
            total_packets=1,
            payload=test_payload
        )
        
        try:
            await client.write_gatt_char(target_write.uuid, test_packet, response=False)
            log.info(f"Test packet sent successfully ({len(test_packet)} bytes)")
        except Exception as e:
            log.error(f"Failed to send test packet: {e}", exc_info=True)
            await client.disconnect()
            return
            
        # --- Keep Running ---
        log.info("\nClient running. Press Ctrl+C to exit...")
        while client.is_connected:
            await asyncio.sleep(1.0)

    except asyncio.CancelledError:
        log.info("Client task cancelled.")
    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        log.info("Cleaning up client...")
        if client and client.is_connected:
            try:
                log.info("Disconnecting...")
                # Only stop notifications if we found the notify characteristic and subscribed successfully
                if target_notify and services_discovered:
                    try:
                        await client.stop_notify(target_notify.uuid)
                        log.info("Stopped notifications.")
                    except Exception as e:
                        log.warning(f"Could not stop notifications: {e}")
                
                await client.disconnect()
            except Exception as e:
                log.error(f"Error during cleanup: {e}")
        log.info("Client stopped.")

# --- Script Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multiparty BLE Client using Bleak")
    parser.add_argument(
        "-a", "--address",
        type=str,
        default=None, # Default to None to trigger scanning
        help="Target BLE device address (e.g., B8:27:EB:2F:D0:34). If omitted, will scan."
    )
    parser.add_argument(
        "-t", "--address-type",
        type=str,
        choices=["public", "random"],
        default="public",
        help="BLE address type: 'public' (default) or 'random'"
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_client(args.address, args.address_type))
    except KeyboardInterrupt:
        log.info("Process interrupted by user.")


