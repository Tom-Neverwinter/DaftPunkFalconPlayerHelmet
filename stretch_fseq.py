#!/usr/bin/env python3
"""Stretch the 2023 helmet renders (old 32x8 face + 2 circles, 931 ch) onto the new
48x8 face + ears (1314 ch) without re-rendering in xLights.
Both faces are vertical zigzag, 8 px per column, so column C of the new face shows
old column C*32//48: same orientation, just wider.
python stretch_fseq.py IN_DIR OUT_DIR    convert every .fseq
python stretch_fseq.py --selftest"""
import os, struct, sys, zstandard

OLD_W, NEW_W, H = 32, 48, 8
NEW_CH = NEW_W * H * 3 + 162
EARS = [(849, 1152, 81), (768, 1233, 81)]   # (old start, new start, channels): Circle-2 -> Ear R, Circle -> Ear L

def pixel_map():
    """new face pixel -> old face pixel."""
    m = []
    for C in range(NEW_W):
        c = C * OLD_W // NEW_W
        for k in range(H):
            row = k if C % 2 == 0 else H - 1 - k          # physical row from the start side
            m.append(c * H + (row if c % 2 == 0 else H - 1 - row))
    return m

def channel_map():
    """new channel -> old channel (or None = dark)."""
    m = [None] * NEW_CH
    for p, q in enumerate(pixel_map()):
        for j in range(3):
            m[p * 3 + j] = q * 3 + j
    for old, new, n in EARS:
        m[new:new + n] = range(old, old + n)
    return m

def read(path):
    b = open(path, "rb").read()
    assert b[:4] == b"PSEQ" and b[7] == 2, path
    data_off, hdr_len = struct.unpack_from("<HxxH", b, 4)
    ch, frames = struct.unpack_from("<II", b, 10)
    step, comp, nblocks, nsparse = b[18], b[20] & 0x0F, b[21] | (b[20] >> 4) << 8, b[22]
    rpos = 32 + nblocks * 8                                       # sparse ranges: 3-byte start, 3-byte count
    ranges = [(int.from_bytes(b[rpos + i * 6:rpos + i * 6 + 3], "little"),
               int.from_bytes(b[rpos + i * 6 + 3:rpos + i * 6 + 6], "little")) for i in range(nsparse)] or [(0, ch)]
    fsize = sum(n for _, n in ranges)
    var = b[hdr_len:data_off]
    if comp == 0:
        raw = b[data_off:data_off + fsize * frames]
    else:
        assert comp == 1, "only zstd/uncompressed"
        raw, pos, d = bytearray(), data_off, zstandard.ZstdDecompressor()
        for i in range(nblocks):
            _, size = struct.unpack_from("<II", b, 32 + i * 8)
            if size:
                raw += d.decompressobj().decompress(b[pos:pos + size])
            pos += size
    assert len(raw) >= fsize * frames, (path, len(raw), fsize * frames)
    if ranges != [(0, ch)]:                                       # expand sparse frames to full channel space
        full = bytearray(ch * frames)
        for f in range(frames):
            o = f * fsize
            for start, n in ranges:
                full[f * ch + start:f * ch + start + n] = raw[o:o + n]; o += n
        raw = full
    return dict(ch=ch, frames=frames, step=step, minor=b[6], uid=b[24:32], var=bytes(var), raw=bytes(raw))

def write(path, s, raw):
    ch, frames = NEW_CH, s["frames"]
    per = -(-frames // 255)                                       # <= 255 zstd blocks
    c = zstandard.ZstdCompressor(level=10)
    blocks = [(f, c.compress(raw[f * ch:(f + per) * ch])) for f in range(0, frames, per)]
    var_off = 32 + len(blocks) * 8
    data_off = var_off + len(s["var"])
    hdr = b"PSEQ" + struct.pack("<HBBHIIBBBBBB", data_off, s["minor"], 2, var_off, ch, frames, s["step"], 0,
                                1 | (len(blocks) >> 8) << 4, len(blocks) & 0xFF, 0, 0) + s["uid"]
    idx = b"".join(struct.pack("<II", f, len(z)) for f, z in blocks)
    with open(path, "wb") as f:
        f.write(hdr + idx + s["var"] + b"".join(z for _, z in blocks))

def convert(src, dst):
    s = read(src)
    assert s["ch"] in (931, 932), (src, s["ch"])
    m, old, out = channel_map(), s["raw"], bytearray()
    for f in range(s["frames"]):
        fr = old[f * s["ch"]:(f + 1) * s["ch"]]
        out += bytes(fr[i] if i is not None else 0 for i in m)
    write(dst, s, bytes(out))
    back = read(dst)
    assert back["raw"][:NEW_CH * s["frames"]] == bytes(out) and back["var"] == s["var"]

def selftest():
    m = pixel_map()
    assert m[:8] == list(range(8))                    # col 0 up = old col 0 up
    assert m[8:16] == list(range(7, -1, -1))          # col 1 goes down, still old col 0 (row-matched)
    assert m[16:24] == list(range(15, 7, -1))         # col 2 up = old col 1, which runs down in the chain
    assert m[-8:] == list(range(31 * 8, 32 * 8))      # col 47 down = old col 31 (down) -> last column lands at the far edge
    assert sorted(set(p // 8 for p in m)) == list(range(32))   # every old column shows up
    cm = channel_map()
    assert cm[1152] == 849 and cm[1233] == 768 and cm[-1] == 848 and len(cm) == 1314
    print("selftest ok")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        src, dst = sys.argv[1:3]
        os.makedirs(dst, exist_ok=True)
        for n in sorted(os.listdir(src)):
            if n.endswith(".fseq"):
                convert(os.path.join(src, n), os.path.join(dst, n))
                print("ok", n)
