"""
MNMLST : LAB AD v9 - MUSIC ONLY, fast modular hardware spot, ~60 seconds.
Built from the supplied v8 script: distinct modular hardware, pogo-pin carrier, matte display,
off-white recycled shell, cat-ear rear logo, rapid swaps and exploded-view shot.
Blender 3.6 - 5.x: Scripting tab -> Open this file -> Run Script (Alt+P).
AUTO_RENDER=True means it automatically renders the final MP4 after setup.
No external assets are required.
"""
import bpy, bmesh, math, os, wave, random, traceback
from mathutils import Matrix

THEME = "light"      # "light" or "dark"
BPM = 128
BARS = 32            # keep 32: the story is laid out for 32 bars
AUDIO_PATH = ""      # empty = use the built-in beat. Or your own track path.
LIGHT_POWER = 300
PREVIEW = False      # True = half resolution, fewer samples
AUTO_RENDER = True

FPS = 24
FPB = FPS * 60.0 / BPM
# Keep a dedicated source scene for the model and the final composited delivery scene.
sc = bpy.data.scenes.get("MNMLST_AD_SOURCE")
if sc is None:
    sc = bpy.context.scene
    sc.name = "MNMLST_AD_SOURCE"

def F(bar, beat=1):
    return int(round(1 + ((bar - 1) * 4 + (beat - 1)) * FPB))

def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def hexcol(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (lin(r), lin(g), lin(b), 1.0)

def try_set(o, a, v):
    try:
        setattr(o, a, v)
    except (AttributeError, TypeError):
        pass

def link(o):
    sc.collection.objects.link(o)
    return o

def fresh_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return m, nt, nt.nodes.new("ShaderNodeOutputMaterial")

def emit(name, col):
    m, nt, out = fresh_mat(name)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = col
    nt.links.new(e.outputs["Emission"], out.inputs["Surface"])
    return m

def principled(name, col, rough, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m

def to_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return link(bpy.data.objects.new(name, me))

def quad(name, sx, sy, z=0.0):
    bm = bmesh.new()
    vs = [bm.verts.new((x * sx / 2, y * sy / 2, z)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    bm.faces.new(vs)
    return to_obj(name, bm)

def outline(w, h, r, seg=8):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts

def prism(name, w, h, t, r, soft=0.0):
    r = min(r, min(w, h) / 2 * 0.98)
    bm = bmesh.new()
    f = bm.faces.new([bm.verts.new((x, y, -t / 2)) for x, y in outline(w, h, r)])
    ex = bmesh.ops.extrude_face_region(bm, geom=[f])
    vv = [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, t), verts=vv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = to_obj(name, bm)
    if soft:
        try:
            m = o.modifiers.new("Soft", "BEVEL")
            m.width, m.segments, m.limit_method = soft, 2, "ANGLE"
        except Exception:
            pass
    return o

def ring(name, w, h, r, inset, t):  # hollow rounded frame
    po, pi = outline(w, h, r, 6), outline(w - 2 * inset, h - 2 * inset, max(r - inset, 0.02), 6)
    bm = bmesh.new()
    ot = [bm.verts.new((x, y, t / 2)) for x, y in po]
    ob = [bm.verts.new((x, y, -t / 2)) for x, y in po]
    it = [bm.verts.new((x, y, t / 2)) for x, y in pi]
    ib = [bm.verts.new((x, y, -t / 2)) for x, y in pi]
    for i in range(len(po)):
        j = (i + 1) % len(po)
        bm.faces.new([ot[i], ot[j], it[j], it[i]])
        bm.faces.new([ob[i], ib[i], ib[j], ob[j]])
        bm.faces.new([ot[i], ob[i], ob[j], ot[j]])
        bm.faces.new([it[i], it[j], ib[j], ib[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return to_obj(name, bm)

def pins(name):  # grid of pogo pins, built along z
    bm = bmesh.new()
    for ix in range(-6, 7):
        for iy in range(-13, 14):
            mt = Matrix.Translation((ix * 0.05, iy * 0.05, 0))
            try:
                bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.007, radius2=0.007, depth=0.01, matrix=mt)
            except TypeError:
                bmesh.ops.create_cone(bm, cap_ends=True, segments=8, diameter1=0.014, diameter2=0.014, depth=0.01, matrix=mt)
    return to_obj(name, bm)

def detail_box(name, parent, w, h, depth, loc, mat, bevel=0.001):
    """Small bevelled detail attached to a module; z<0 is the visible rear face."""
    r = min(bevel, w * 0.22, h * 0.22)
    o = prism(name, w, h, depth, max(0.001, r), min(r, depth * 0.35))
    o.data.materials.append(mat)
    o.parent = parent
    o.location = loc
    return o

def detail_disc(name, parent, radius, depth, loc, mat, segments=24):
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(bm, cap_ends=True, segments=segments,
                              radius1=radius, radius2=radius, depth=depth)
    except TypeError:
        bmesh.ops.create_cone(bm, cap_ends=True, segments=segments,
                              diameter1=radius * 2, diameter2=radius * 2, depth=depth)
    o = to_obj(name, bm)
    o.data.materials.append(mat)
    o.parent = parent
    o.location = loc
    return o

def detail_ring(name, parent, w, h, radius, inset, depth, loc, mat):
    o = ring(name, w, h, radius, inset, depth)
    o.data.materials.append(mat)
    o.parent = parent
    o.location = loc
    return o

def bar(name):  # unit hairline from x=0 to x=1
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x += 0.5
        v.co.y *= 0.004
        v.co.z *= 0.004
    return to_obj(name, bm)

FONT = None
for p in ("C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf",
          "/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Courier.ttc",
          "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
          "/usr/share/fonts/TTF/DejaVuSansMono.ttf"):
    if os.path.exists(p):
        try:
            FONT = bpy.data.fonts.load(p)
            break
        except Exception:
            pass

def text(body, size, loc, mat, hud=None, align="LEFT", parent=None):
    cu = bpy.data.curves.new("t", "FONT")
    cu.body, cu.size = body, size
    cu.align_x = align
    if FONT:
        cu.font = FONT
    cu.materials.append(mat)
    o = link(bpy.data.objects.new("t", cu))
    if hud:
        o.parent = hud
        o.location = (loc[0], loc[1], -3)
    elif parent:
        o.parent = parent
        o.location = loc
    else:
        o.location = loc
        o.rotation_euler = (math.radians(90), 0, 0)
    return o

def rounded(pts, d=6.0, n=5):
    """Round the corners of a polyline with small curves."""
    def toward(a, b, dist):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = min(dist, L / 2) / L
        return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, p, c = toward(pts[i], pts[i - 1], d), pts[i], toward(pts[i], pts[i + 1], d)
        for j in range(n + 1):
            t = j / n
            out.append(((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * p[0] + t * t * c[0],
                        (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * p[1] + t * t * c[1]))
    out.append(pts[-1])
    return out

def logo(name, s, mat, loc, rot, parent=None):
    """Your ASCII logo as smooth line art: side bars, ears, flat valley, wordmark between."""
    root = link(bpy.data.objects.new(name, None))
    root.location, root.rotation_euler, root.scale = loc, rot, (s, s, s)
    if parent:
        root.parent = parent
    path = rounded([(-96, -32), (-96, 0), (-60, 38), (-24, 0), (24, 0), (60, 38), (96, 0), (96, -32)])
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth, cu.bevel_resolution = 2.4, 4
    try_set(cu, "use_fill_caps", True)
    sp = cu.splines.new("POLY")
    sp.points.add(len(path) - 1)
    for pt, (x, y) in zip(sp.points, path):
        pt.co = (x, y, 0, 1)
    cu.materials.append(mat)
    o = link(bpy.data.objects.new(name, cu))
    o.parent = root
    text("M N M L S T", 19, (0, -27, 0), mat, align="CENTER", parent=root)
    return root

def aim(o, target):
    c = o.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis, c.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"

def keys(o, path, seq):
    """seq = [(frame, value[, smooth])]. Hard snap by default; smooth=True eases."""
    prev = None
    for e in seq:
        f, v = e[0], e[1]
        smooth = len(e) > 2 and e[2]
        if prev is not None and not smooth and f > 1:
            setattr(o, path, prev)
            o.keyframe_insert(path, frame=f - 1)
        setattr(o, path, v)
        o.keyframe_insert(path, frame=f)
        prev = v

def appear(o, f_on, s1=(1, 1, 1), f_off=None, s0=(0, 0, 0)):
    seq = [(1, s0), (f_on, s1)]
    if f_off:
        seq.append((f_off, s0))
    keys(o, "scale", seq)

def wav9(path, sr, vals):
    data = bytes(max(0, min(255, int(128 + 127 * v))) for v in vals)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(sr)
        w.writeframes(data)

def make_track(path, clicks, hits):
    """Built-in compact 8-bit house beat: punchy, syncopated, repeatable on every build."""
    random.seed(128)
    sr = 11025
    N = int((sc.frame_end / FPS + 1.0) * sr)
    buf = [0.0] * N
    spb = 60.0 / BPM
    def at(t):
        return int(t * sr)
    def kick(t0):
        s, ph = at(t0), 0.0
        for i in range(max(0, min(int(0.22 * sr), N - s))):
            t = i / sr
            ph += (45 + 120 * math.exp(-t * 28)) / sr
            buf[s + i] += 0.95 * math.sin(6.2832 * ph) * math.exp(-t * 13)
    def noise(t0, dur, decay, g):
        s = at(t0)
        for i in range(max(0, min(int(dur * sr), N - s))):
            buf[s + i] += g * random.uniform(-1, 1) * math.exp(-(i / sr) * decay)
    def sq(t0, f, d, g, dec=9.0):
        s = at(t0)
        for i in range(max(0, min(int(d * sr), N - s))):
            t = i / sr
            buf[s + i] += g * (1 if (t * f) % 1 < 0.5 else -1) * math.exp(-t * dec)
    def boom(t0):
        s = at(t0)
        for i in range(max(0, min(int(0.9 * sr), N - s))):
            t = i / sr
            buf[s + i] += 0.9 * math.sin(6.2832 * 38 * t) * math.exp(-t * 4) + 0.4 * random.uniform(-1, 1) * math.exp(-t * 6)
    for bar_ in range(1, BARS + 1):
        for beat in range(4):
            t = ((bar_ - 1) * 4 + beat) * spb
            on = (3 <= bar_ <= 13) or (15 <= bar_ <= 28)
            if on or (bar_ == 14 and beat == 3):
                kick(t)
            if bar_ <= 2 and beat % 2 == 0:
                noise(t, 0.03, 90, 0.18)
            elif 3 <= bar_ <= 28:
                noise(t + spb / 2, 0.04, 80, 0.3)
            if ((7 <= bar_ <= 13) or (15 <= bar_ <= 28)) and beat in (1, 3):
                noise(t, 0.14, 28, 0.5)
            if (7 <= bar_ <= 13) or (15 <= bar_ <= 28):
                sq(t + spb / 2, (55, 55, 65.41, 49)[(bar_ - 1) % 4] * 2, 0.2, 0.28)
        if bar_ == 14:
            for k in range(8):
                noise((bar_ - 1) * 4 * spb + k * spb / 2, 0.1, 30, 0.2 + 0.08 * k)
    for f in hits:
        boom((f - 1) / FPS)
    for f in clicks:
        sq((f - 1) / FPS, 1800, 0.015, 0.5, 40)
    pk = max(1e-6, max(abs(v) for v in buf))
    wav9(path, sr, [math.tanh(1.3 * v / pk) * 0.95 for v in buf])

def build():
    # Clear only this scene; do not erase objects belonging to other Blender scenes.
    for o in list(sc.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    dark = THEME == "dark"
    BG = hexcol("#0d0e11" if dark else "#f4f3ef")
    INKC = hexcol("#e0ded7" if dark else "#1a1a1a")
    GREY = tuple(BG[i] * 0.82 + INKC[i] * 0.18 for i in range(3)) + (1.0,)
    INK, GR = emit("ink", INKC), emit("grid", GREY)
    SHELL = principled("shell", hexcol("#e4e1d8"), 0.55)
    MATTE = principled("matte", hexcol("#101114"), 0.95)
    PRINT = principled("print", hexcol("#1a1a1a"), 0.6)
    BRASS = principled("brass", hexcol("#b08d57"), 0.35, 1.0)
    DK = principled("darkmark", hexcol("#25262a"), 0.5)
    ALU = principled("satin_aluminium", hexcol("#9b9a93"), 0.28, 0.72)
    GLASS = principled("smoked_lens", hexcol("#30343b"), 0.22, 0.12)
    SAGE = principled("status_sage", hexcol("#83927d"), 0.38, 0.08)
    GRAPHITE = principled("graphite", hexcol("#55575b"), 0.42, 0.38)

    # ---- render ----
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            pass
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.resolution_percentage = 50 if PREVIEW else 100
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, F(BARS + 1) - 1
    try_set(sc.view_settings, "view_transform", "Standard")
    try:
        try_set(sc.eevee, "taa_render_samples", 12 if PREVIEW else 48)
    except Exception:
        pass  # Engine settings differ slightly between Blender 3.6 and newer builds.
    sc.render.image_settings.file_format = "FFMPEG"
    sc.render.ffmpeg.format = "MPEG4"
    sc.render.ffmpeg.codec = "H264"
    try_set(sc.render.ffmpeg, "audio_codec", "AAC")
    try_set(sc.render.ffmpeg, "constant_rate_factor", "HIGH")
    try_set(sc.render.ffmpeg, "ffmpeg_preset", "GOOD")
    try_set(sc.render, "use_file_extension", True)
    # The source scene renders 3D only. A separate delivery scene combines this
    # scene strip with the audio strips, avoiding blank sequencer-only frames.
    try_set(sc.render, "use_sequencer", False)
    base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
    sc.render.filepath = os.path.join(base, "mnmlst_lab_ad_v9_music_only")

    # ---- seamless world, floor, lab grid (draws in fast) ----
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    bgn = w.node_tree.nodes.get("Background") or w.node_tree.nodes.new("ShaderNodeBackground")
    bgn.inputs["Color"].default_value = BG
    bgn.inputs["Strength"].default_value = 1.0
    quad("floor", 300, 300, -0.002).data.materials.append(emit("floor", BG))
    n = 0
    for k in range(-12, 13):
        for horiz in (False, True):
            g = quad("g", 12, 0.006, 0.0006) if horiz else quad("g", 0.006, 12, 0.0006)
            g.location = (0, k * 0.5, 0) if horiz else (k * 0.5, 0, 0)
            g.data.materials.append(GR)
            appear(g, int(2 + n * 1.8), (1, 1, 1), s0=(0, 1, 1) if horiz else (1, 0, 1))
            n += 1

    # ---- phone: layers from back (-z) to front (+z), 4.5 mm total ----
    pivot = link(bpy.data.objects.new("pivot", None))
    pivot.location = (0, 0, 0.87)
    phone = link(bpy.data.objects.new("phone", None))
    phone.parent = pivot
    phone.rotation_euler = (math.radians(90), 0, 0)

    def layer(o, mat, z):
        o.data.materials.append(mat)
        o.parent = phone
        o.location = (0, 0, z)
        return o
    Z0 = {"cover": -0.0185, "chassis": 0.0095, "mid": -0.0045, "frame": 0.0175, "screen": 0.0226}
    cover = layer(prism("back_cover", 0.72, 1.5, 0.008, 0.1, 0.002), SHELL, Z0["cover"])
    chassis = layer(prism("chassis", 0.72, 1.5, 0.008, 0.1, 0.002), SHELL, Z0["chassis"])
    mid = layer(ring("midframe", 0.72, 1.5, 0.1, 0.03, 0.02), SHELL, Z0["mid"])
    frame = layer(prism("display_frame", 0.72, 1.5, 0.008, 0.1, 0.002), SHELL, Z0["frame"])
    screen = layer(prism("screen", 0.66, 1.44, 0.002, 0.075), MATTE, Z0["screen"])
    pg = pins("pogo_pins")
    pg.data.materials.append(BRASS)
    pg.parent = chassis
    pg.location = (0, 0, -0.009)
    logo("back_logo", 0.0016, PRINT, (0, 0, -0.0046), (0, math.pi, 0), cover)

    # ---- 10 distinctly designed modules: each has its own visual signature ----
    # Positions approximate a real rear carrier layout; dimensions intentionally vary.
    MZ = -0.0045
    DEF = (("OPTIC",  (-0.20,  0.55), 0.17, 0.17, "#dedbd2"),
           ("AI",     ( 0.00,  0.55), 0.17, 0.17, "#c9c9c2"),
           ("CELL",   ( 0.20,  0.55), 0.17, 0.17, "#bfc4bf"),
           ("SOS",    (-0.20, -0.60), 0.17, 0.17, "#ddd8ce"),
           ("RADIO",  ( 0.00, -0.60), 0.17, 0.17, "#c8c7c0"),
           ("CO2",    ( 0.20, -0.60), 0.17, 0.17, "#bdc4be"),
           ("DAC",    (-0.145,-0.37), 0.27, 0.22, "#c4c4bd"),
           ("VECTOR", ( 0.145,-0.37), 0.27, 0.22, "#d7d4ca"),
           ("NFC",    ( 0.00,  0.33), 0.56, 0.20, "#b7b6ac"),
           ("POWER",  ( 0.00, -0.02), 0.56, 0.38, "#a8aaa4"))
    SLP, MODS = {}, {}
    SLOT_STYLE = {}
    for nm, pos, mw_, mh_, col in DEF:
        SLP[nm] = pos
        # Recess outline on the carrier makes each slide-in bay legible in close-ups.
        slot = ring("slot_" + nm, mw_ + 0.012, mh_ + 0.012,
                    min(0.035, min(mw_, mh_) * 0.30), 0.006, 0.002)
        slot.data.materials.append(GRAPHITE)
        slot.parent = chassis
        slot.location = (pos[0], pos[1], -0.005)
        # Module shell: satin recycled-polymer; size and tint vary by function.
        m = prism(nm, mw_, mh_, 0.02, min(0.035, min(mw_, mh_) * 0.25), 0.002)
        m.data.materials.append(principled(nm + "_shell", hexcol(col), 0.48, 0.04))
        m.parent = phone
        m.location = (pos[0], pos[1], MZ)
        MODS[nm] = m
        SLOT_STYLE[nm] = (mw_, mh_)

        # Three raised gold contact pads on the inward-facing side of every module.
        for j in range(3):
            px = (j - 1) * min(0.045, mw_ * 0.18)
            detail_box(nm + "_contact_%d" % j, m, min(0.018, mw_ * 0.08),
                       0.012, 0.003, (px, -mh_ * 0.34, 0.011), BRASS, 0.001)

        # Different functional hardware details on each outward-facing module face.
        face = -0.0125
        if nm == "OPTIC":
            detail_disc("optic_rim", m, 0.047, 0.004, (0, 0.012, face), ALU)
            detail_disc("optic_glass", m, 0.035, 0.004, (0, 0.012, face - 0.003), GLASS)
            detail_disc("optic_aperture", m, 0.012, 0.003, (0, 0.012, face - 0.006), DK)
            for sx in (-1, 1):
                detail_disc("optic_screw", m, 0.0045, 0.002, (sx * 0.062, -0.055, face), BRASS, 12)
        elif nm == "AI":
            detail_box("ai_chip_base", m, 0.083, 0.083, 0.003, (0, 0.012, face), DK)
            detail_box("ai_chip_core", m, 0.047, 0.047, 0.003, (0, 0.012, face - 0.003), ALU)
            for side in (-1, 1):
                for j in range(3):
                    detail_box("ai_pin", m, 0.009, 0.018, 0.002,
                               (side * 0.052, -0.012 + j * 0.022, face - 0.001), BRASS, 0.0008)
        elif nm == "CELL":
            for j, wid in enumerate((0.075, 0.056, 0.037)):
                detail_box("cell_antenna_%d" % j, m, wid, 0.008, 0.003,
                           (0, 0.030 - j * 0.022, face), DK, 0.001)
            detail_box("cell_spine", m, 0.008, 0.072, 0.003, (0, -0.018, face), BRASS, 0.001)
        elif nm == "SOS":
            detail_disc("sos_outer", m, 0.052, 0.004, (0, 0.012, face), DK)
            detail_disc("sos_button", m, 0.038, 0.004, (0, 0.012, face - 0.003), SAGE)
            detail_box("sos_mark_v", m, 0.006, 0.021, 0.002, (0, 0.008, face - 0.006), DK, 0.001)
            detail_box("sos_mark_h", m, 0.020, 0.006, 0.002, (0, -0.004, face - 0.006), DK, 0.001)
        elif nm == "RADIO":
            detail_box("radio_track", m, 0.115, 0.027, 0.003, (0, 0.015, face), DK, 0.003)
            detail_box("radio_slider", m, 0.035, 0.047, 0.005, (0.025, 0.015, face - 0.004), ALU, 0.003)
            for j in range(3):
                detail_box("radio_tick", m, 0.003, 0.012, 0.002,
                           (-0.045 + j * 0.023, -0.033, face), BRASS, 0.0005)
        elif nm == "CO2":
            for ix in range(3):
                for iy in range(3):
                    detail_disc("co2_vent", m, 0.006, 0.002,
                                ((ix - 1) * 0.026, 0.015 + (iy - 1) * 0.024, face), DK, 12)
            detail_box("co2_slot", m, 0.080, 0.008, 0.002, (0, -0.052, face), ALU, 0.001)
        elif nm == "DAC":
            for px, radius in ((-0.060, 0.036), (0.035, 0.026)):
                detail_disc("dac_port_rim", m, radius, 0.004, (px, 0.018, face), ALU)
                detail_disc("dac_port_dark", m, radius * 0.72, 0.004,
                            (px, 0.018, face - 0.003), DK)
                detail_disc("dac_port_core", m, radius * 0.22, 0.002,
                            (px, 0.018, face - 0.006), GLASS)
            for j in range(3):
                detail_box("dac_vent", m, 0.012, 0.004, 0.002,
                           (-0.025 + j * 0.025, -0.060, face), DK, 0.0005)
        elif nm == "VECTOR":
            # Bezel made from individual ticks, a needle and a central bearing.
            for j in range(12):
                a = 2 * math.pi * j / 12
                tick = detail_box("vector_tick", m, 0.014, 0.003, 0.002,
                                  (math.cos(a) * 0.067, math.sin(a) * 0.067 + 0.012, face), ALU, 0.0005)
                tick.rotation_euler[2] = a
            detail_disc("vector_bearing", m, 0.013, 0.003, (0, 0.012, face - 0.002), DK, 16)
            needle = detail_box("vector_needle", m, 0.008, 0.072, 0.002, (0, 0.018, face - 0.004), SAGE, 0.001)
            needle.rotation_euler[2] = math.radians(24)
            detail_disc("vector_pin", m, 0.007, 0.003, (0, 0.012, face - 0.006), BRASS, 16)
        elif nm == "NFC":
            detail_ring("nfc_loop_outer", m, 0.43, 0.13, 0.045, 0.012, 0.002,
                        (0, 0.004, face), ALU)
            detail_ring("nfc_loop_inner", m, 0.35, 0.085, 0.032, 0.010, 0.002,
                        (0, 0.004, face - 0.002), DK)
            for j in range(8):
                detail_box("nfc_pad", m, 0.014, 0.035, 0.002,
                           (-0.19 + j * 0.054, -0.065, face - 0.001), BRASS, 0.0005)
        elif nm == "POWER":
            detail_box("power_label_plate", m, 0.31, 0.20, 0.003, (0, 0.020, face), DK, 0.006)
            for j in range(4):
                detail_box("power_cell_%d" % j, m, 0.052, 0.115, 0.003,
                           (-0.093 + j * 0.062, 0.020, face - 0.003), ALU, 0.002)
            detail_box("power_plus", m, 0.035, 0.006, 0.002, (0.205, 0.052, face), BRASS, 0.0008)
            detail_box("power_plus_v", m, 0.006, 0.035, 0.002, (0.205, 0.052, face), BRASS, 0.0008)
            detail_box("power_minus", m, 0.035, 0.006, 0.002, (0.205, -0.015, face), BRASS, 0.0008)

        # Tiny industrial identifier printed on each module face.
        tag = {"OPTIC":"OPT", "AI":"AI", "CELL":"4G", "SOS":"SOS", "RADIO":"RF",
               "CO2":"CO2", "DAC":"HI-FI", "VECTOR":"VEC", "NFC":"NFC", "POWER":"PWR"}[nm]
        label = text(tag, 0.016 if mw_ < 0.3 else 0.022,
                     (-mw_ * 0.36, -mh_ * 0.36, -0.0155), DK, parent=m)
        label.rotation_euler = (0, math.pi, 0)

    # soft floor shadow
    sh = quad("shadow", 1, 1, 0.001)
    try_set(sh, "visible_shadow", False)
    smt, nt, out = fresh_mat("shadow")
    tc, mp = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (2, 2, 2)
    gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "QUADRATIC_SPHERE"
    mu = nt.nodes.new("ShaderNodeMath")
    mu.operation = "MULTIPLY"
    mu.inputs[1].default_value = 0.8 if dark else 0.45
    tr, bk, mx = (nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeEmission"),
                  nt.nodes.new("ShaderNodeMixShader"))
    bk.inputs["Color"].default_value = (0, 0, 0, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], gr.inputs["Vector"])
    nt.links.new(gr.outputs["Fac"], mu.inputs[0])
    nt.links.new(mu.outputs["Value"], mx.inputs[0])
    nt.links.new(tr.outputs["BSDF"], mx.inputs[1])
    nt.links.new(bk.outputs["Emission"], mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    try_set(smt, "blend_method", "BLEND")
    try_set(smt, "surface_render_method", "BLENDED")
    sh.data.materials.append(smt)

    # phone + shadow: slam in on bar 3, leave at the end card (bar 29)
    keys(pivot, "scale", [(1, (0, 0, 0)), (F(3), (1, 1, 1)), (F(29), (0, 0, 0))])
    keys(sh, "scale", [(1, (0, 0, 0)), (F(3), (1.5, 0.9, 1)), (F(29), (0, 0, 0))])

    # yaw: edge-on, back view, teardown spin, front, back logo, orbit
    yaw = [(1, 0), (F(3), 90), (F(7), 180), (F(15), 70), (F(19), 150, True), (F(20), 180),
           (F(23), 0), (F(25), 180), (F(29) - 1, 235, True)]
    keys(pivot, "rotation_euler", [(e[0], (0, 0, math.radians(e[1]))) + e[2:] for e in yaw])

    # ---- back cover slides off (bar 7), returns (bar 14), then explodes ----
    A = (0, 0, Z0["cover"])
    OFF = (1.4, 0, Z0["cover"])
    OUT = (0, 0, Z0["cover"] - 0.46)
    keys(cover, "location", [(1, A), (F(7), A, True), (F(7) + 26, OFF, True), (F(14, 3), OFF, True),
                             (F(14, 3) + 22, A, True), (F(15), A, True), (F(15) + 30, OUT, True),
                             (F(19), OUT, True), (F(19) + 30, A, True)])
    keys(cover, "scale", [(1, (1, 1, 1)), (F(7) + 30, (0, 0, 0)), (F(14, 3) - 1, (1, 1, 1))])

    # ---- module interchange: lift off the pins, cross over, drop in ----
    own = {k: k for k in ("OPTIC", "AI", "CELL", "SOS", "RADIO", "CO2", "DAC", "VECTOR")}
    def sp(slot, dz=0.0):
        return (SLP[slot][0], SLP[slot][1], MZ + dz)
    S = {k: [(1, sp(own.get(k, k)))] for k in MODS}
    CLK = []
    def swap(f, pairs, d=24):
        for a, b in pairs:
            sa, sb = own[a], own[b]
            for m, s0, s1, lift in ((a, sa, sb, -0.10), (b, sb, sa, -0.17)):
                S[m] += [(f, sp(s0), True), (f + d // 4, sp(s0, lift), True),
                         (f + 3 * d // 4, sp(s1, lift), True), (f + d, sp(s1), True)]
            own[a], own[b] = sb, sa
        CLK.append(f + d)
    SW = ((("OPTIC", "AI"), ("SOS", "CO2")), (("CELL", "RADIO"), ("DAC", "VECTOR")),
          (("OPTIC", "SOS"), ("AI", "CELL")), (("RADIO", "CO2"), ("DAC", "VECTOR")),
          (("OPTIC", "CO2"), ("AI", "SOS")), (("CELL", "SOS"), ("RADIO", "AI")),
          (("OPTIC", "CELL"), ("RADIO", "CO2"), ("DAC", "VECTOR")))
    for i, pairs in enumerate(SW):
        swap(F(7 + i, 3), pairs)
    # exploded view: modules scatter outward and back, like the reference
    for i, m in enumerate(MODS):
        p = sp(own.get(m, m))
        dz = {"NFC": -0.30, "POWER": -0.25}.get(m, -0.16 - 0.035 * (i % 5))
        # Radially spread every module so no parts overlap in the exploded hero shot.
        sx = -1 if (i % 2 == 0) else 1
        sy = -1 if (i % 3 == 0) else 1
        q = (p[0] * 1.55 + sx * (0.075 + 0.012 * (i % 3)),
             p[1] * 1.33 + sy * (0.045 + 0.012 * (i % 2)), p[2] + dz)
        S[m] += [(F(15), p, True), (F(15) + 30, q, True), (F(19), q, True), (F(19) + 30, p, True)]
    QS = ((F(20, 1), (("OPTIC", "CELL"), ("SOS", "RADIO"))),
          (F(20, 3), (("AI", "CO2"), ("DAC", "VECTOR"))),
          (F(21, 1), (("OPTIC", "RADIO"), ("CELL", "SOS"))),
          (F(21, 3), (("AI", "CELL"), ("CO2", "SOS"))),
          (F(22, 1), (("OPTIC", "CO2"), ("AI", "RADIO"), ("DAC", "VECTOR"))),
          (F(22, 3), (("OPTIC", "AI"), ("SOS", "CO2"))))
    for f, pairs in QS:
        swap(f, pairs, 22)
    for m, o in MODS.items():
        keys(o, "location", S[m])
    for o, key, off in ((chassis, "chassis", 0.06), (mid, "mid", -0.10), (frame, "frame", 0.30), (screen, "screen", 0.38)):
        z = Z0[key]
        keys(o, "location", [(1, (0, 0, z)), (F(15), (0, 0, z), True), (F(15) + 30, (0, 0, z + off), True),
                             (F(19), (0, 0, z + off), True), (F(19) + 30, (0, 0, z), True)])

    # ---- world-space spec text ----
    def lab(body, size, loc, f_on, f_off=None, blen=0.0, bat=None):
        t = text(body, size, loc, INK)
        appear(t, f_on, (1, 1, 1), f_off)
        if blen:
            b = bar("line")
            b.data.materials.append(INK)
            b.location = bat
            appear(b, f_on, (blen, 1, 1), f_off, s0=(0, 1, 1))
    lab("4.5 mm", 0.06, (0.14, 0, 0.99), F(3, 2), F(7), 0.1, (0.03, 0, 1.01))
    lab("off-white recycled HDPE shell", 0.045, (0.14, 0, 0.75), F(4), F(7), 0.1, (0.03, 0, 0.77))
    lab("matte display", 0.045, (0.14, 0, 1.25), F(5), F(7), 0.1, (0.03, 0, 1.27))
    for i, (s, z) in enumerate((("OPTIC / CAMERA", 1.45), ("AI / SUMMARY", 1.15), ("CELL / 4G", 0.85))):
        lab(s, 0.085, (0.85, 0, z), F(8 + i), F(15), 0.3, (0.5, 0, z + 0.03))
    for i, (s, z) in enumerate((("VECTOR / COMPASS", 1.48), ("HI-FI / DAC", 1.20),
                                ("RADIO / HARD CUT", 0.92), ("CO2 / SENSOR", 0.64),
                                ("POWER / HOT SWAP", 0.36))):
        lab(s, 0.071, (0.95, 0, z), F(15) + 20 + i * 8, F(19), 0.3, (0.6, 0, z + 0.03))
    lab("ONE DEVICE. YOUR RULES.", 0.09, (-2.3, 0, 0.8), F(23), F(25))
    lab("the product speaks for itself.", 0.09, (-2.3, 0, 0.8), F(27), F(29))

    # end card: smooth ears logo + lines; music resolves here
    lg = logo("end_logo", 0.012, INK, (0, 0, 0.95), (math.radians(90), 0, 0))
    appear(lg, F(29), (0.012, 0.012, 0.012))
    lab("snap in. switch off.", 0.09, (-0.8, 0, 0.35), F(29, 3))
    lab("batch #001  -  reserve now", 0.07, (-0.95, 0, 0.15), F(30, 3))

    # ---- lights ----
    for name, loc, power, size in (("key", (-2.5, -3.0, 3.5), LIGHT_POWER, 4.0),
                                   ("rim", (3.0, 2.0, 2.5), LIGHT_POWER * 0.5, 2.0)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.size = power, size
        lo = link(bpy.data.objects.new(name, ld))
        lo.location = loc
        aim(lo, pivot)

    # ---- camera, hard-cut on the beat ----
    look = link(bpy.data.objects.new("look", None))
    cd = bpy.data.cameras.new("cam")
    cd.lens, cd.sensor_fit, cd.sensor_height = 50, "VERTICAL", 24
    cd.dof.use_dof = True
    cd.dof.focus_object = pivot
    cd.dof.aperture_fstop = 4.0
    cam = link(bpy.data.objects.new("cam", cd))
    sc.camera = cam
    aim(cam, look)
    W1 = ((0.15, -5.2, 1.3), (0.35, 0, 0.87))
    W2 = ((1.5, -4.4, 0.35), (0.3, 0, 0.87))
    W3 = ((-1.2, -4.0, 3.2), (0.3, 0, 0.8))
    M1 = ((0.25, -1.4, 0.87), (0, 0, 0.87))
    M2 = ((0.3, -1.0, 1.35), (0, 0, 1.4))
    M3 = ((0.3, -1.0, 0.4), (0, 0, 0.35))
    C1 = ((0.9, -1.6, 1.5), (0, 0, 1.45))
    C2 = ((-0.9, -1.8, 0.4), (0, 0, 0.4))
    T = ((2.2, -3.6, 1.5), (0, -0.1, 0.87))
    LG = ((0.1, -1.9, 0.87), (0, 0, 0.87))
    PUSH = ((0.15, -3.9, 1.2), (0.35, 0, 0.87))
    EC = ((0, -5.4, 0.95), (0, 0, 0.95))
    cs, ls = [(1, (0.15, -9.0, 4.0))], [(1, W1[1])]
    def cut(f, s, smooth=False):
        cs.append((f, s[0], smooth))
        ls.append((f, s[1], smooth))
    cut(F(3) - 1, W1, True)
    for i, (b, bt) in enumerate(((3, 1), (3, 3), (4, 1), (4, 3), (5, 1), (5, 3), (6, 1), (6, 3))):
        cut(F(b, bt), (M1, M2, M3, M1, C1, M2, C2, M1)[i])
    for i, b in enumerate(range(7, 14)):
        cut(F(b), (W1, W2, W3, W1, W2, W3, W1)[i])
    for i, s in enumerate((W2, W3, C1, C2)):
        cut(F(14, 1 + i), s)
    cyc, i = (T, W2, W3, C1), 0
    for b in range(15, 19):
        for bt in (1, 3):
            cut(F(b, bt), cyc[i % 4])
            i += 1
    for i, s in enumerate((W1, W2, W3, W1)):
        cut(F(19, 1 + i), s)
    rapid = (W1, W2, C1, W3, C2, T, W2, W3, C1, W1, T, W2)
    for i in range(12):
        cut(F(20 + i // 4, 1 + i % 4), rapid[i])
    for b, s in ((23, W1), (24, W3), (25, LG), (26, W2), (27, W1)):
        cut(F(b), s)
    cut(F(29) - 1, PUSH, True)
    cut(F(29), EC)
    keys(cam, "location", cs)
    keys(look, "location", ls)

    # ---- HUD locked to the camera frame ----
    def hud_bar(x, y, rot, length):
        b = bar("hud")
        b.data.materials.append(INK)
        b.parent = cam
        b.location = (x, y, -3)
        b.rotation_euler = (0, 0, math.radians(rot))
        b.scale = (length, 1, 1)
    for x, y, hr, vr in ((-1.15, 0.62, 0, -90), (1.15, 0.62, 180, -90),
                         (-1.15, -0.62, 0, 90), (1.15, -0.62, 180, 90)):
        hud_bar(x, y, hr, 0.12)
        hud_bar(x, y, vr, 0.12)
    text("MNMLST : LAB", 0.04, (-1.08, 0.53), INK, cam)
    text("UNIT 001 / BATCH #001", 0.025, (-1.08, 0.48), INK, cam)
    text("%d BPM" % BPM, 0.03, (0.93, 0.53), INK, cam)
    led = quad("led", 0.03, 0.03)
    led.data.materials.append(INK)
    led.parent = cam
    led.location = (0.88, 0.545, -3)
    lq = [(1, (0, 0, 0))]
    for k in range(BARS * 4):
        f = F(1 + k // 4, 1 + k % 4)
        lq += [(f, (1, 1, 1)), (f + 3, (0, 0, 0))]
    keys(led, "scale", lq)
    pb = bar("progress")
    pb.data.materials.append(INK)
    pb.parent = cam
    pb.location = (-1.15, -0.66, -3)
    keys(pb, "scale", [(F(1 + b), (2.3 * b / BARS, 1, 1), b > 0) for b in range(BARS + 1)])
    for b0, b1, s in ((1, 3, "SYS BOOT"), (3, 7, "FIG.01  EDGE PROFILE"), (7, 15, "FIG.02  MODULE SWAP"),
                      (15, 23, "FIG.03  EXPLODED VIEW"), (23, 29, "FIG.04  THE PRODUCT"),
                      (29, BARS + 1, "MNMLST : LAB / BATCH #001")):
        t = text(s, 0.04, (-1.08, -0.56), INK, cam)
        appear(t, F(b0), (1, 1, 1), F(b1) if b1 <= BARS else None)

    # hook: kinetic words on the first four beats
    for word, f in (("SWAP.", F(1, 1)), ("SNAP.", F(1, 3)), ("CLICK.", F(2, 1)), ("DETACH.", F(2, 3))):
        t = text(word, 0.32, (0, -0.1), INK, cam, align="CENTER")
        appear(t, f, (1, 1, 1), f + 12)
    # impact flashes on the big downbeats
    fl = quad("flash", 6, 4)
    fl.data.materials.append(INK)
    fl.parent = cam
    fl.location = (0, 0, -2.5)
    HITS = [F(3), F(15), F(23), F(29)]
    fq = [(1, (0, 0, 0))]
    for f in HITS:
        fq += [(f, (1, 1, 1)), (f + 2, (0, 0, 0))]
    keys(fl, "scale", fq)

    # ---- beat markers + ad-ready delivery scene (3D picture + instrumental audio) ----
    for b in range(1, BARS + 1):
        sc.timeline_markers.new("bar %d" % b, frame=F(b))
    delivery = None
    trk = AUDIO_PATH
    if not trk:
        trk = os.path.join(base, "mnmlst_track.wav")
        make_track(trk, CLK, [F(15), F(23), F(29)])
    try:

        # Rebuild the delivery scene cleanly if the script is run more than once.
        old_delivery = bpy.data.scenes.get("MNMLST_AD_DELIVERY")
        if old_delivery is not None:
            try:
                if bpy.context.window:
                    bpy.context.window.scene = sc
            except Exception:
                pass
            bpy.data.scenes.remove(old_delivery)

        delivery = bpy.data.scenes.new("MNMLST_AD_DELIVERY")
        delivery.frame_start, delivery.frame_end = sc.frame_start, sc.frame_end
        delivery.render.engine = sc.render.engine
        delivery.render.resolution_x = sc.render.resolution_x
        delivery.render.resolution_y = sc.render.resolution_y
        delivery.render.resolution_percentage = sc.render.resolution_percentage
        delivery.render.fps = sc.render.fps
        delivery.render.image_settings.file_format = "FFMPEG"
        delivery.render.ffmpeg.format = "MPEG4"
        delivery.render.ffmpeg.codec = "H264"
        try_set(delivery.render.ffmpeg, "audio_codec", "AAC")
        try_set(delivery.render.ffmpeg, "constant_rate_factor", "HIGH")
        try_set(delivery.render.ffmpeg, "ffmpeg_preset", "GOOD")
        try_set(delivery.render, "use_file_extension", True)
        try_set(delivery.render, "use_sequencer", True)
        delivery.render.filepath = sc.render.filepath

        se = delivery.sequence_editor_create()
        coll = getattr(se, "strips", None)
        if coll is None or not hasattr(coll, "new_scene") or not hasattr(coll, "new_sound"):
            coll = getattr(se, "sequences", None)
        if coll is None or not hasattr(coll, "new_scene") or not hasattr(coll, "new_sound"):
            raise RuntimeError("Could not access Blender's Video Sequencer strip collection for this Blender version.")
        coll.new_scene("MNMLST 3D PRODUCT AD", sc, 1, 1)
        coll.new_sound("MNMLST instrumental 8-bit beat", trk, 2, 1)
        delivery.frame_set(1)
    except Exception:
        traceback.print_exc()
        print("Delivery setup failed. The 3D scene is built, but the MP4 scene could not be assembled.")

    sc.frame_set(1)
    # Keep Blender on the actual 3D product scene after script setup, so the
    # viewport is not left looking empty on the sequencer-only delivery scene.
    window = bpy.context.window
    if window is not None:
        try:
            window.scene = sc
        except Exception:
            pass

    print("MNMLST : LAB v9 MUSIC ONLY ready — %d frames (%.1f s) at %d BPM." %
          (sc.frame_end, sc.frame_end / FPS, BPM))
    print("MP4 output path: " + sc.render.filepath + ".mp4")
    print("Generated soundtrack: " + trk)
    if AUTO_RENDER:
        if delivery is None:
            raise RuntimeError("The delivery scene was not created; refusing to render a silent/source-only video.")
        print("Starting automatic MP4 render now. Keep Blender open until rendering finishes.")
        window = bpy.context.window
        try:
            if window is not None:
                window.scene = delivery
                bpy.ops.render.render(animation=True)
            else:
                # Supports background-mode runs as well as interactive Blender.
                with bpy.context.temp_override(scene=delivery, view_layer=delivery.view_layers[0]):
                    bpy.ops.render.render(animation=True)
        finally:
            if window is not None:
                try:
                    window.scene = sc
                except Exception:
                    pass

try:
    build()
except Exception:
    traceback.print_exc()
    print("FAILED. Copy the error above and send it to me.")
