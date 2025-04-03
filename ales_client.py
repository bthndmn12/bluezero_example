import asyncio
import zlib
import struct
from bleak import BleakScanner, BleakClient
import binascii


address = "B8:27:EB:2F:D0:34"
uuidWrite = ""
uuidTimer = ""

MTU = 517
PACKET_SIZE = MTU - 5 - 3 # bytes, ajustado de acuerdo a la capacidad MTU del dispositivo, dejando espacio para el header (5B) y otros datos (3B)

def xor_checksum(data: bytes) -> int:
        checksum = 0
        for byte in data:
                checksum ^= byte  # XOR all bytes together
        return checksum

async def main():
    devices = await BleakScanner.discover()
    found = False
    for d in devices:
        print(d.address, d.name)
        if d.address.upper() == address.upper():
            found = True
            print("Peripheral found, attempting connection...")
            break

    if not found:
        print("Peripheral not found. Ensure it’s advertising.")
        return

    async with BleakClient(address) as client:
        try:
            await client.connect()
            print("Connected:", client.is_connected)
            # Your existing logic...
        except Exception as e:
            print("Connection error:", e)
