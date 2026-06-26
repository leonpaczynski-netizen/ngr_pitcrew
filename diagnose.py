"""Run this while SimHub is running to see what's actually arriving on port 33741.
   python diagnose.py
"""
import socket, struct, time

PORT = 33741
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", PORT))
sock.settimeout(5.0)

print(f"Listening on 0.0.0.0:{PORT} — drive in GT7 to generate packets...\n")

for i in range(5):
    try:
        data, addr = sock.recvfrom(8192)
    except socket.timeout:
        print("No packet received within 5 seconds — SimHub not sending here.")
        break

    print(f"=== Packet {i+1} from {addr} ===")
    print(f"  Length : {len(data)} bytes")
    print(f"  First 4: {data[0:4]}  (hex: {data[0:4].hex(' ')})")
    print(f"  First 16 bytes hex:")
    print("  " + " ".join(f"{b:02X}" for b in data[:16]))
    if len(data) >= 16:
        print(f"  First 16 bytes ASCII: {data[:16]}")

    # Try little-endian int32 of first 4 bytes
    if len(data) >= 4:
        le_magic = struct.unpack('<i', data[:4])[0]
        be_magic = struct.unpack('>i', data[:4])[0]
        print(f"  First 4 as LE int32 : 0x{le_magic & 0xFFFFFFFF:08X}")
        print(f"  First 4 as BE int32 : 0x{be_magic & 0xFFFFFFFF:08X}")

    # Check for known GT7 magic
    if data[0:4] in (b'G7S0', b'G7S1', b'G7S~', b'G7SC'):
        print("  >> MATCHES expected GT7 magic (decrypted) ✓")
    elif len(data) == 296:
        print("  >> Length is 296 — could be encrypted GT7 packet")
        # Try to detect if it's encrypted (encrypted packets have random-looking first bytes)
        print("  >> First 4 bytes don't match G7S0/G7S1 — packet may be encrypted")
        print("     Check if SimHub's 'Share UDP data' is set to forward RAW game data")
    else:
        print(f"  >> Unknown format (length {len(data)} ≠ 296, magic not G7S*)")

    print()

sock.close()
print("Done. Share this output to diagnose the issue.")
