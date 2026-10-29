#!/usr/bin/env python3
"""Generate looping 48x8 face emotes as .fseq for the helmet (no audio).
python make_emotes.py OUT_DIR     write "Emote - <name>.fseq" files
python make_emotes.py --preview   print every emote's first frame as text
python make_emotes.py --selftest"""
import math, os, random, sys
from stretch_fseq import NEW_CH, H, write

W = 48
STEP_MS = 50                                   # 20 fps
MIRROR_X, FLIP_Y = True, False                 # panel chain starts on the right (Hello read backwards 2026-10-28); FLIP_Y if upside down

def canvas():
    return [[(0, 0, 0)] * W for _ in range(H)]

def stamp(c, art, x0, color, y0=0):
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            if ch == "#" and 0 <= x0 + x < W and 0 <= y0 + y < H:
                c[y0 + y][x0 + x] = color

def to_channels(c):
    out = bytearray(NEW_CH)                    # ears stay dark
    for x in range(W):
        for y in range(H):
            px, r = (W - 1 - x if MIRROR_X else x), (y if FLIP_Y else H - 1 - y)   # r = row from bottom
            p = px * H + (r if px % 2 == 0 else H - 1 - r)                       # vertical zigzag
            out[p * 3:p * 3 + 3] = bytes(c[y][x])
    return bytes(out)

def mirror(art):
    return [row[::-1] for row in art]

HEART = [".##..##.", "########", "########", "########", ".######.", "..####..", "...##...", "........"]
SMALL_HEART = ["........", "........", "..#..#..", ".######.", ".######.", "..####..", "...##...", "........"]
EYE = ["........", "..####..", ".######.", ".######.", ".######.", "..####..", "........", "........"]
SHUT = ["........", "........", "........", "........", ".######.", "........", "........", "........"]
HAPPY = ["........", "...##...", "..#..#..", ".#....#.", "#......#", "........", "........", "........"]
ANGRY = ["#.......", ".##.....", "..###...", "..#####.", "..#####.", "...###..", "........", "........"]
WIDE = ["..####..", ".#....#.", "#......#", "#......#", "#......#", "#......#", ".#....#.", "..####.."]
X_EYE = ["#......#", ".#....#.", "..#..#..", "...##...", "...##...", "..#..#..", ".#....#.", "#......#"]
SAD = ["........", "........", "#......#", ".######.", "..####..", "........", "........", "........"]
L_EYE, R_EYE = 12, 28                          # x of the two eyes

FONT = {" ": ["...", "...", "...", "...", "...", "...", "..."], "!": ["#", "#", "#", "#", "#", ".", "#"]}
for ch, rows in {"H": "#...#|#...#|#...#|#####|#...#|#...#|#...#", "E": "#####|#....|#....|####.|#....|#....|#####",
                 "L": "#....|#....|#....|#....|#....|#....|#####", "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.",
                 "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..", "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#",
                 "N": "#...#|##..#|#.#.#|#..##|#...#|#...#|#...#", "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#",
                 "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..", "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###."}.items():
    FONT[ch] = rows.split("|")

def text_art(text):
    rows = [""] * 7
    for ch in text:
        for i in range(7):
            rows[i] += FONT[ch][i] + "."
    return rows

def eyes(left, right, color, t=0):
    c = canvas()
    stamp(c, left, L_EYE, color)
    stamp(c, right, R_EYE, color)
    return c

def hsv(h, v=1.0):
    i, f = int(h * 6) % 6, h * 6 % 1
    q, t = v * (1 - f), v * f
    r, g, b = [(v, t, 0), (q, v, 0), (0, v, t), (0, q, v), (t, 0, v), (v, 0, q)][i]
    return int(r * 255), int(g * 255), int(b * 255)

# each emote: name -> list of frames (canvases); the playlist loops them
def heart():
    frames = []
    for f in range(40):
        big = f % 20 < 6                         # thump-thump once a second
        c = canvas()
        for x in (4, 20, 36):
            stamp(c, HEART if big else SMALL_HEART, x, (255, 0, 40))
        frames.append(c)
    return frames

def blink(left=EYE, right=EYE, color=(255, 255, 255), wink=False):
    frames = []
    for f in range(60):                          # open 2.7 s, shut 0.3 s
        shut = f >= 54
        frames.append(eyes(left if not shut or wink else SHUT, right if not shut else SHUT, color))
    return frames

def steady(left, right, color, n=20):
    return [eyes(left, right, color) for _ in range(n)]

def angry():
    return [eyes(ANGRY, mirror(ANGRY), (255, 0, 0) if f % 10 < 8 else (120, 0, 0)) for f in range(20)]

def sad():
    frames = []
    for f in range(40):
        c = eyes(SAD, SAD, (0, 80, 255))
        y = 5 + f // 8
        if y < H:
            c[y][L_EYE + 1] = (120, 200, 255)    # tear rolling down
        frames.append(c)
    return frames

def scroll(text, color):
    art = text_art(text)
    width = len(art[0])
    frames = []
    for x0 in range(W, -width, -1):
        c = canvas()
        stamp(c, art, x0, color)
        frames.append(c)
    return frames

def rainbow():
    frames = []
    for f in range(60):
        c = canvas()
        for x in range(W):
            for y in range(H):
                c[y][x] = hsv((x / W + y / 40 + f / 60) % 1)
        frames.append(c)
    return frames

def scanner():
    frames = []
    for f in range(48):
        pos = abs((f * 2) % 92 - 46)             # bounce 0..46
        c = canvas()
        for x in range(W):
            v = max(0, 1 - abs(x - pos) / 6)
            for y in range(H):
                c[y][x] = (int(255 * v), 0, 0)
        frames.append(c)
    return frames

def equalizer():
    rnd, frames, levels = random.Random(83), [], [0] * 12
    for f in range(80):
        levels = [max(0, min(8, l + rnd.choice((-2, -1, 1, 2)))) for l in levels]
        c = canvas()
        for i, l in enumerate(levels):
            for x in range(i * 4, i * 4 + 3):
                for y in range(H - l, H):
                    c[y][x] = hsv((H - 1 - y) / 24)   # green at the bottom, red at the top
        frames.append(c)
    return frames

EMOTES = {
    "Heart": heart,
    "Happy": lambda: steady(HAPPY, HAPPY, (255, 200, 0)),
    "Blink": blink,
    "Wink": lambda: blink(wink=True),
    "Angry": angry,
    "Surprised": lambda: steady(WIDE, WIDE, (255, 255, 255)),
    "Sad": sad,
    "KO": lambda: steady(X_EYE, X_EYE, (255, 60, 0)),
    "Hello": lambda: scroll("HELLO!", (0, 255, 255)),
    "Thank You": lambda: scroll("THANK YOU!", (255, 0, 255)),
    "Rainbow": rainbow,
    "Scanner": scanner,
    "Equalizer": equalizer,
}

def build(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for name, make in EMOTES.items():
        frames = make()
        raw = b"".join(to_channels(c) for c in frames)
        meta = dict(frames=len(frames), step=STEP_MS, minor=0, uid=os.urandom(8), var=b"")
        fn = f"Emote - {name}.fseq"
        write(os.path.join(out_dir, fn), meta, raw)
        names.append(fn)
    return names

def preview():
    for name, make in EMOTES.items():
        print(name)
        for row in make()[0 if name not in ("Hello", "Thank You") else 30]:
            print("".join("#" if sum(p) else "." for p in row))

def selftest():
    global MIRROR_X
    keep = MIRROR_X
    c = canvas(); c[H - 1][0] = (1, 2, 3); c[0][1] = (4, 5, 6)
    MIRROR_X = False
    ch = to_channels(c)
    assert ch[0:3] == bytes((1, 2, 3))          # bottom-left = pixel 1
    assert ch[8 * 3:8 * 3 + 3] == bytes((4, 5, 6))   # column 1 starts at the top (zigzag)
    MIRROR_X = True
    ch = to_channels(c)
    assert ch[(W * H - 1) * 3:W * H * 3] == bytes((1, 2, 3))   # bottom-left -> col 47, which runs downward: last face pixel
    MIRROR_X = keep
    for name, make in EMOTES.items():
        fr = make()
        assert fr and all(len(f) == H and len(f[0]) == W for f in fr), name
    print("selftest ok")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--preview" in sys.argv:
        preview()
    else:
        print("\n".join(build(sys.argv[1])))
