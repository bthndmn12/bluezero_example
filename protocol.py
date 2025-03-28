# multiparty_ble/protocol.py

from enum import IntFlag, Enum
import struct

class PacketFlags(IntFlag):
    NONE = 0
    LAST_PACKET = 1 << 0
    ACK_REQUIRED = 1 << 1
    METADATA = 1 << 2
    BASE64_ENCODED = 1 << 3
    COMPRESSED = 1 << 4

class PacketType(Enum):
    DATA = 0x01
    ACK = 0x02
    CHECKSUM = 0x03
    METADATA = 0x04

HEADER_FORMAT = "<BBHHH"  # type, flags, packet_id, total_packets, payload_length
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

def build_packet(packet_type: PacketType, flags: PacketFlags, packet_id: int, total_packets: int, payload: bytes) -> bytes:
    header = struct.pack(
        HEADER_FORMAT,
        packet_type.value,
        flags,
        packet_id,
        total_packets,
        len(payload)
    )
    return header + payload

def parse_packet(packet: bytes):
    if len(packet) < HEADER_SIZE:
        raise ValueError("Invalid packet size")
    header = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
    payload = packet[HEADER_SIZE:]
    return {
        "type": PacketType(header[0]),
        "flags": PacketFlags(header[1]),
        "packet_id": header[2],
        "total_packets": header[3],
        "payload_length": header[4],
        "payload": payload,
    }
