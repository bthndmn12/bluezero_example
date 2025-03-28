# test_bleak_scan.py
import asyncio
from bleak import BleakScanner

async def main():
    devices = await BleakScanner.discover(adapter="hci0")
    for d in devices:
        print(d)

if __name__ == "__main__":
    asyncio.run(main())

# # test_bleak.py
# import asyncio
# import logging
# from bleak import BleakClient

# # !! Make sure this is the CORRECT address of your Raspberry Pi !!
# ADDRESS = "08:9D:F4:CA:14:5C"

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# log = logging.getLogger("minimal_bleak_test")

# async def main():
#     log.info(f"Attempting to connect to {ADDRESS} using bleak directly...")
#     try:
#         # Use a longer timeout just in case
#         async with BleakClient(ADDRESS, timeout=20.0) as client:
#             if client.is_connected:
#                 log.info(f"Successfully connected to {ADDRESS}!")
#                 log.info("Attempting to list services...")
#                 try:
#                     services = await client.get_services()
#                     log.info("Services discovered:")
#                     for service in services:
#                         log.info(f"  Service: {service.uuid}")
#                         for char in service.characteristics:
#                             log.info(f"    Characteristic: {char.uuid} ({', '.join(char.properties)})")
#                 except Exception as service_err:
#                     log.error(f"Error discovering services: {service_err}", exc_info=True)
#             else:
#                 # This state should ideally not be reached if the context manager enters without error
#                 log.warning("Client context entered but connection flag is false?")
#     except Exception as e:
#         log.error(f"Direct bleak connection failed! Type: {type(e)}, Repr: {repr(e)}, Msg: {e}", exc_info=True)
#     log.info("Minimal test finished.")

# if __name__ == "__main__":
#     # On Windows, you might need this ProactorEventLoop policy for bleak
#     # import platform
#     # if platform.system() == "Windows":
#     #     asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
#     asyncio.run(main())