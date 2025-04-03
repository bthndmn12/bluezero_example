#!/usr/bin/env python3

import logging
import struct
import time
import signal
import sys

# Bluezero modules
from bluezero import async_tools
from bluezero import adapter
from bluezero import device

# --- Configuration ---
# Server details
SERVER_NAME = "CPU Monitor" # The local_name set in the server
SERVER_ADDRESS = "B8:27:EB:2F:D0:34" # Optional: Replace with server's MAC if known
#SERVER_ADDRESS = None # Set to None to scan by name/service

# UUIDs must match the server
CPU_TMP_SRVC = '12341000-1234-1234-1234-123456789abc'
CPU_TMP_CHRC = '2A6E' # Use the 16-bit short UUID for characteristics

SCAN_TIMEOUT = 15 # Seconds to scan for

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger("bz-client")

# --- Global State ---
cpu_monitor_device: device.Device = None # Will hold the found Device object
event_loop = async_tools.EventLoop()
discovery_timed_out = False

# --- Data Parsing ---
def parse_temperature(data: list[int]) -> float:
    """Parses the list of byte values into temperature."""
    try:
        byte_data = bytes(data)
        temp_value = struct.unpack('<h', byte_data)[0]
        return temp_value / 100.0
    except (struct.error, IndexError, TypeError) as e:
        log.error(f"Failed to parse temperature data: {data} - {e}")
        return float('nan') # Return Not-a-Number on error

# --- Callbacks ---
def on_device_found_callback(dev_obj: device.Device):
    """Callback triggered by Adapter when a device is discovered."""
    global cpu_monitor_device # Allow modification of the global variable
    global event_loop # To quit the discovery loop

    try:
        # Attempt to get properties (Alias might not be available immediately)
        dev_name = dev_obj.alias # Uses D-Bus Get property
        dev_addr = dev_obj.address
        log.info(f"Device Found: Address={dev_addr}, Name='{dev_name}'")

        # Check if it's the device we want
        if dev_name == SERVER_NAME:
            log.info(f"*** Target device '{SERVER_NAME}' found! ***")
            cpu_monitor_device = dev_obj # Store the found device object
            # Stop discovery (best effort, might be done by timeout too)
            try:
                 dev_obj.adapter.stop_discovery()
            except Exception:
                 pass # Ignore errors stopping discovery here
            event_loop.quit() # Stop the discovery event loop

    except Exception as e:
        # Getting properties might fail if device disappears quickly
        log.debug(f"Could not get properties for discovered device: {e}")


def on_discovery_timeout():
    """Callback if discovery timer expires before device is found."""
    global discovery_timed_out
    global event_loop
    log.warning(f"Scan timeout ({SCAN_TIMEOUT}s) reached.")
    discovery_timed_out = True
    # Ensure discovery is stopped
    try:
         adapter.Adapter().stop_discovery() # Get default adapter and stop
    except Exception:
         pass
    event_loop.quit() # Stop the event loop
    return False # Stop timer


def on_characteristic_notify(characteristic_path, changed_props):
    """Callback for characteristic notifications."""
    if 'Value' in changed_props:
        temp_bytes = changed_props['Value']
        temperature = parse_temperature(temp_bytes)
        log.info(f"NOTIFICATION received: Temp = {temperature:.2f}°C")
    else:
        log.warning(f"Notification received without 'Value': {changed_props}")


def stop_client(signum, frame):
    """Signal handler to stop the client cleanly."""
    log.info("Stop signal received. Cleaning up...")
    if cpu_monitor_device and cpu_monitor_device.connected:
        try:
            log.info("Attempting to disable notifications...")
            cpu_monitor_device.stop_notify(CPU_TMP_CHRC)
        except Exception as e:
            log.warning(f"Could not disable notifications (may not have been enabled): {e}")
        finally:
            if cpu_monitor_device.connected:
                 cpu_monitor_device.disconnect()
    event_loop.quit()
    log.info("Client stopped.")
    sys.exit(0)


# --- Main Logic ---
def main():
    global cpu_monitor_device
    global discovery_timed_out

    # ... signal handlers ...

    # Get the default adapter
    try:
        dongle = adapter.Adapter()
        log.info(f"Using adapter: {dongle.address}")
    except Exception as e:
        log.error(f"Failed to get Bluetooth adapter: {e}")
        return

    # --- Determine Target Address ---
    target_device_addr = None # Use a temporary variable for the address
    if SERVER_ADDRESS:
        log.info(f"Using provided address: {SERVER_ADDRESS}")
        target_device_addr = SERVER_ADDRESS
    else:
        # --- Scan Logic ---
        log.info(f"Starting scan for '{SERVER_NAME}' (timeout: {SCAN_TIMEOUT}s)...")
        # ... (rest of scanning logic using on_device_found_callback) ...
        event_loop.run() # Wait for scan/timeout

        if discovery_timed_out or cpu_monitor_device is None: # Check the global var set by callback
            log.error(f"Could not find device '{SERVER_NAME}'. Ensure server is running and discoverable.")
            return
        else:
             # If found via scanning, the callback already set cpu_monitor_device
             target_device_addr = cpu_monitor_device.address # Get address if needed later
             log.info(f"Device found via scan: {target_device_addr}")

    # --- Create Device Object (ONLY if address is known) ---
    if target_device_addr:
        if cpu_monitor_device is None: # Only create if not already done by scan callback
            try:
                # **** THIS IS THE CORRECT LINE AND PLACEMENT ****
                # It MUST be inside main() after dongle exists
                cpu_monitor_device = device.Device(
                    adapter_addr=dongle.address,  # Pass local adapter address
                    device_addr=target_device_addr # Pass remote device address
                )
            except Exception as e:
                 log.error(f"Failed to create Device object: {e}", exc_info=True)
                 return
    else:
         log.error("No target device address available to create Device object.")
         return

    # --- Connect using the found/created Device object ---
    if not cpu_monitor_device:
        log.error("Target device object not available.")
        return

    try:
        log.info(f"Connecting to {cpu_monitor_device.address}...")
        if not cpu_monitor_device.connect(timeout=20):
            log.error("Failed to connect.")
            return

        log.info("Connected successfully!")
        time.sleep(2.0) # Allow services to resolve internally

        # --- Interact (Read Characteristic) ---
        log.info(f"Attempting to read temperature (Characteristic: {CPU_TMP_CHRC})...")
        try:
            value_list = cpu_monitor_device.read_gatt_characteristic(CPU_TMP_CHRC)
            if value_list:
                 temperature = parse_temperature(value_list)
                 log.info(f"Initial Temperature read: {temperature:.2f}°C")
            else:
                 log.warning("Read operation returned no data (characteristic might be missing or empty).")
        except Exception as e:
            log.error(f"Failed to read characteristic {CPU_TMP_CHRC}: {e}", exc_info=True)
            if "not found" in str(e).lower() or "InvalidArguments" in str(e) or "DoesNotExist" in str(e):
                 log.error("Characteristic likely not registered correctly on the server.")
                 cpu_monitor_device.disconnect()
                 return

        # --- Interact (Enable Notifications) ---
        log.info(f"Attempting to enable notifications for {CPU_TMP_CHRC}...")
        try:
            cpu_monitor_device.enable_notify(CPU_TMP_CHRC, on_characteristic_notify)
            log.info("Notifications enabled. Waiting for updates... (Press Ctrl+C to stop)")
            # Re-run the event loop for notifications/signals
            event_loop.run()

        except Exception as e:
            log.error(f"Failed to enable notifications for {CPU_TMP_CHRC}: {e}", exc_info=True)
            if "not found" in str(e).lower() or "InvalidArguments" in str(e) or "DoesNotExist" in str(e):
                 log.error("Characteristic likely not registered correctly on the server.")
            # Cleanup happens in stop_client or final block

    except Exception as e:
        log.error(f"An error occurred during connection or interaction: {e}", exc_info=True)

    finally:
         # Ensure cleanup happens if main logic exits unexpectedly
         stop_client(None, None) # Call cleanup function


if __name__ == "__main__":
    # Suggest renaming the file if you haven't already
    main()