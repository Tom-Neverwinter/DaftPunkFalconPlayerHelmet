#!/usr/bin/env python3
"""Technologic Deck: an Elgato Stream Deck remote for Falcon Player (FPP).
Runs on the FPP box (e.g. a Pi inside a costume or prop); keys call the local FPP API.
Top row: PLAY STOP NEXT VOL+ VOL-. Bottom row: < BACK, folder switch (middle), FWD >.
Two folders, each with its own pages:
  SONGS   every sequence in the FPP playlists: tap = select (blue), PLAY plays it.
  EMOTES  the sequences in the "Emotes" playlist: tap = play now, loops until STOP.
Green = playing now. NEXT = play the next item in the open folder.
python3 technologic_deck.py            run (systemd service)
python3 technologic_deck.py --selftest check the key layout logic, no hardware needed"""
import json, sys, textwrap, threading, time, urllib.parse, urllib.request

FPP = "http://127.0.0.1"
DECK_BRIGHTNESS = 40          # % backlight; it's on a wrist, keep it dim at night
VOL_STEP = 5
CONTROLS = ["PLAY", "STOP", "NEXT", "VOL +", "VOL -"]
EMOTE_PLAYLIST = "Emotes"
FOLDERS = ["SONGS", "EMOTES"]
INSTANT = {"EMOTES"}          # folders where a tap plays right away, on repeat
COLORS = {"playing": "#0a6", "selected": "#036", "STOP": "#300", "PLAY": "#030", "nav": "#222", "FOLDER": "#530"}

def api(path, body=None):
    # FPP's PHP API crashes on a GET that carries a JSON Content-Type, so only send it with a body
    req = urllib.request.Request(FPP + path) if body is None else urllib.request.Request(
        FPP + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return r.read().decode()

def command(name, args):
    api("/api/command", {"command": name, "args": args})

def library():
    """{folder: [sequence, ...]} from the FPP playlists, in playlist order, no repeats."""
    out = {f: [] for f in FOLDERS}
    for pl in json.loads(api("/api/playlists")):
        folder = "EMOTES" if pl == EMOTE_PLAYLIST else "SONGS"
        for e in json.loads(api("/api/playlist/" + urllib.parse.quote(pl))).get("mainPlaylist", []):
            s = e.get("sequenceName")
            if s and s not in out[folder]:
                out[folder].append(s)
    return out

def layout(n_items, rows, cols, page):
    """-> (keys, pages, per). keys[i] = control name, 'BACK'/'FOLDER'/'FWD', ('ITEM', index) or None (blank)."""
    keys = (CONTROLS + [None] * cols)[:cols] + [None] * (rows - 1) * cols
    keys[-cols], keys[-cols + cols // 2], keys[-1] = "BACK", "FOLDER", "FWD"
    slots = [i for i, k in enumerate(keys) if i >= cols and k is None]
    per = len(slots)
    pages = max(1, -(-n_items // per))
    first = (page % pages) * per
    for slot, idx in zip(slots, range(first, min(first + per, n_items))):
        keys[slot] = ("ITEM", idx)
    return keys, pages, per

def next_index(names, playing, selected):
    base = names.index(playing) if playing in names else (selected if selected is not None else -1)
    return (base + 1) % len(names)

def label_of(key, names, folder, page, pages):
    if key is None:
        return ""
    if key in ("BACK", "FWD"):
        where = f"{folder} {page % pages + 1}/{pages}"
        return f"< BACK\n{where}" if key == "BACK" else f"FWD >\n{where}"
    if key == "FOLDER":
        return "GO TO\n" + FOLDERS[(FOLDERS.index(folder) + 1) % len(FOLDERS)]
    if isinstance(key, tuple):
        return names[key[1]].removesuffix(".fseq").removeprefix("Emote - ")
    return key

_font = None
def font():
    global _font
    if _font is None:
        from PIL import ImageFont
        try:
            _font = ImageFont.truetype("DejaVuSans-Bold.ttf", 12)
        except OSError:
            _font = ImageFont.load_default()
    return _font

def render(deck, text, bg):
    from PIL import ImageDraw
    from StreamDeck.ImageHelpers import PILHelper
    # Debian's 0.9.1 lib has create_image/to_native_format; newer ones renamed them *_key_*
    create = getattr(PILHelper, "create_key_image", None) or PILHelper.create_image
    native = getattr(PILHelper, "to_native_key_format", None) or PILHelper.to_native_format
    img = create(deck, background=bg)
    lines = "\n".join(l for part in text.split("\n") for l in textwrap.wrap(part, 9)[:4])
    ImageDraw.Draw(img).multiline_text((img.width / 2, img.height / 2), lines, font=font(),
                                       fill="white", anchor="mm", align="center")
    return native(deck, img)

def run():
    from StreamDeck.DeviceManager import DeviceManager
    while True:
        decks = DeviceManager().enumerate()
        if not decks:
            time.sleep(3)                     # wrist cable unplugged: wait for it
            continue
        deck = decks[0]
        deck.open(); deck.reset(); deck.set_brightness(DECK_BRIGHTNESS)
        rows, cols = deck.key_layout()
        st = {"folder": FOLDERS[0], "page": {f: 0 for f in FOLDERS}, "selected": {f: None for f in FOLDERS},
              "lib": {f: [] for f in FOLDERS}, "playing": None, "keys": [], "drawn": None}
        lock = threading.Lock()

        def play(i):
            f = st["folder"]
            st["selected"][f], st["page"][f] = i, i // layout(len(st["lib"][f]), rows, cols, 0)[2]
            command("Start Playlist", [st["lib"][f][i], "true" if f in INSTANT else "false", "false"])

        def redraw():
            f = st["folder"]
            names = st["lib"][f]
            keys, pages, _ = layout(len(names), rows, cols, st["page"][f])
            looks = []
            for k in keys:
                bg = COLORS.get(k, COLORS["nav"] if k in ("BACK", "FWD") else "black")
                if isinstance(k, tuple):
                    bg = COLORS["playing"] if names[k[1]] == st["playing"] else \
                         COLORS["selected"] if k[1] == st["selected"][f] else "black"
                looks.append((label_of(k, names, f, st["page"][f], pages), bg))
            st["keys"] = keys
            if looks == st["drawn"]:
                return
            for i, look in enumerate(looks):
                if st["drawn"] is None or st["drawn"][i] != look:
                    deck.set_key_image(i, render(deck, *look))
            st["drawn"] = looks

        def pressed(_deck, key, down):
            if not down:
                return
            with lock:
                k = st["keys"][key] if key < len(st["keys"]) else None
                f = st["folder"]
                try:
                    if isinstance(k, tuple):
                        st["selected"][f] = k[1]
                        if f in INSTANT:
                            play(k[1])
                    elif k in ("BACK", "FWD"):
                        st["page"][f] += 1 if k == "FWD" else -1
                    elif k == "FOLDER":
                        st["folder"] = FOLDERS[(FOLDERS.index(f) + 1) % len(FOLDERS)]
                    elif k == "PLAY" and st["selected"][f] is not None:
                        play(st["selected"][f])
                    elif k == "STOP":
                        command("Stop Now", [])
                    elif k == "NEXT" and st["lib"][f]:
                        play(next_index(st["lib"][f], st["playing"], st["selected"][f]))
                    elif k in ("VOL +", "VOL -"):
                        command("Volume Adjust", [str(VOL_STEP if k == "VOL +" else -VOL_STEP)])
                    redraw()
                except Exception as e:
                    print("key failed:", k, e, flush=True)

        deck.set_key_callback(pressed)
        tick = 0
        try:
            while deck.is_open():
                try:
                    if tick % 30 == 0:        # playlists rarely change; don't hammer the Pi
                        st["lib"] = library()
                    status = json.loads(api("/api/fppd/status"))
                    st["playing"] = status.get("current_sequence") or None
                except Exception:
                    st["playing"] = None      # FPP restarting: keys still draw
                with lock:
                    redraw()
                tick += 1
                time.sleep(1)
        except Exception as e:                # deck unplugged mid-show
            print("deck lost:", e, flush=True)
        finally:
            try: deck.close()
            except Exception: pass

def selftest():
    keys, pages, per = layout(49, 3, 5, 0)                        # original/MK.2 15-key
    assert keys[:5] == CONTROLS and keys[10] == "BACK" and keys[12] == "FOLDER" and keys[14] == "FWD"
    assert per == 7 and pages == 7
    assert [k[1] for k in keys if isinstance(k, tuple)] == list(range(7))
    keys, _, _ = layout(13, 3, 5, 1)                              # 13 emotes: page 2 = 6 items, 1 blank
    assert [k[1] for k in keys if isinstance(k, tuple)] == list(range(7, 13)) and keys[13] is None
    assert layout(49, 3, 5, 7)[0] == layout(49, 3, 5, 0)[0]       # FWD wraps around
    assert layout(49, 3, 5, -1)[0] == layout(49, 3, 5, 6)[0]      # BACK wraps around
    assert layout(0, 3, 5, 0)[1] == 1                             # empty folder still draws
    names = ["a.fseq", "b.fseq", "c.fseq"]
    assert next_index(names, "b.fseq", 0) == 2                    # follows what's playing
    assert next_index(names, None, 2) == 0                        # else the selection, wrapping
    assert next_index(names, None, None) == 0
    assert label_of(("ITEM", 0), ["Emote - Heart.fseq"], "EMOTES", 0, 1) == "Heart"
    assert label_of("FOLDER", [], "SONGS", 0, 1) == "GO TO\nEMOTES"
    assert label_of("FOLDER", [], "EMOTES", 0, 1) == "GO TO\nSONGS"
    assert label_of("BACK", [], "SONGS", 2, 7) == "< BACK\nSONGS 3/7"
    print("selftest ok")

if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else run()
