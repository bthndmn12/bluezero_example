# multiparty_ble/checksum.py

import zlib

def compute_checksum(data: bytes) -> int:
    """
    Compute a 32-bit checksum using CRC32.
    """
    return zlib.crc32(data) & 0xFFFFFFFF

def verify_checksum(data: bytes, expected_checksum: int) -> bool:
    """
    Verify the checksum of the given data.
    """
    return compute_checksum(data) == expected_checksum
