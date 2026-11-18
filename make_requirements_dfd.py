# -*- coding: utf-8 -*-
"""Draw DFD diagrams for the requirements specification."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageChops

OUT = Path(r"D:\code\python\TravelMind\docs\第三次实验_assets")
OUT.mkdir(parents=True, exist_ok=True)

S = 3  # supersampling

FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

INK = (45, 55, 72)
MUTED = (90, 100, 115)
PROC_FILL = (234, 243, 251)
PROC_LINE = (47, 85, 151)
EXT_FILL = (252, 228, 214)
EXT_LINE = (197, 90, 17)
STORE_FILL = (226, 240, 217)
STORE_LINE = (84, 130, 53)
ARROW = (70, 80, 95)


def f(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, int(size * S))


def canvas(w, h):
    img = Image.new("RGB", (w * S, h * S), "white")
    return img, ImageDraw.Draw(img)


def wrap(draw, text, font, max_width):
    lines = []
    for raw in text.split("\n"):
        line = ""
        for ch in raw:
            trial = line + ch
            if draw.textlength(trial, font=font) <= max_width:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = ch
        lines.append(line)
    return "\n".join(lines)


def label(draw, xy, text, size=18, color=INK, bold=False, anchor="mm", max_width=None):
    font = f(size, bold)
    if max_width:
        text = wrap(draw, text, font, max_width * S)
    draw.multiline_text((xy[0] * S, xy[1] * S), text, font=font, fill=color,
                        anchor=anchor, align="center", spacing=4 * S)


def box(draw, xy, text, kind="process", size=19, bold=True, max_width=None):
    x1, y1, x2, y2 = [v * S for v in xy]
    if kind == "process":
        draw.rounded_rectangle((x1, y1, x2, y2), radius=16 * S, fill=PROC_FILL, outline=PROC_LINE, width=3 * S)
        color = PROC_LINE
    elif kind == "external":
        draw.rectangle((x1, y1, x2, y2), fill=EXT_FILL, outline=EXT_LINE, width=3 * S)
        color = EXT_LINE
    else:
        draw.rectangle((x1, y1, x2, y2), fill=STORE_FILL, outline=None)
        draw.line((x1, y1, x2, y1), fill=STORE_LINE, width=3 * S)
        draw.line((x1, y2, x2, y2), fill=STORE_LINE, width=3 * S)
        draw.line((x1, y1, x1, y1 + 16 * S), fill=STORE_LINE, width=3 * S)
        draw.line((x1, y2 - 16 * S, x1, y2), fill=STORE_LINE, width=3 * S)
        color = STORE_LINE
    w = (x2 - x1) / S
    mx = max_width if max_width else w - 22
    label(draw, ((xy[0] + xy[2]) / 2, (xy[1] + xy[3]) / 2), text, size=size, color=color, bold=bold, max_width=mx)


def arrow(draw, pts, text=None, size=16, color=ARROW, lx=None, ly=None, lw=52, anchor="mm"):
    pts = [(x * S, y * S) for x, y in pts]
    draw.line(pts, fill=color, width=2 * S, joint="curve")
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    ah, aw = 10 * S, 5 * S
    p1 = (x2, y2)
    p2 = (x2 - ux * ah + px * aw, y2 - uy * ah + py * aw)
    p3 = (x2 - ux * ah - px * aw, y2 - uy * ah - py * aw)
    draw.polygon([p1, p2, p3], fill=color)
    if text:
        mx = lx if lx is not None else (pts[0][0] + pts[-1][0]) / 2 / S
        my = ly if ly is not None else (pts[0][1] + pts[-1][1]) / 2 / S
        label(draw, (mx, my), text, size=size, color=MUTED, max_width=lw, anchor=anchor)


def save(img, name):
    path = OUT / name
    rgb = img.convert("RGB")
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white"))
    bbox = diff.getbbox()
    pad = 24
    if bbox:
        img = img.crop((
            max(0, bbox[0] - pad),
            max(0, bbox[1] - pad),
            min(img.width, bbox[2] + pad),
            min(img.height, bbox[3] + pad),
        ))
    img.save(path, "PNG", dpi=(220, 220))
    print(path)


# ---------------------------------------------------------------------------
# Context diagram
# ---------------------------------------------------------------------------
img, d = canvas(1000, 600)
box(d, (40, 220, 180, 340), "旅行者", "external", size=22)
box(d, (360, 200, 640, 380), "TravelMind\n行程规划系统\nP0", "process", size=24)
box(d, (800, 200, 960, 340), "高德\nWeb 服务", "external", size=19)
box(d, (400, 480, 600, 580), "官方数据 /\n人工维护", "external", size=18)

arrow(d, [(180, 280), (360, 280)], "出行条件", lx=270, ly=258, lw=90)
arrow(d, [(360, 320), (180, 320)], "行程方案 / 费用", lx=270, ly=342, lw=130)
arrow(d, [(640, 260), (800, 260)], "POI / 路线 /\n天气 / 静态图", lx=720, ly=235, lw=105)
arrow(d, [(800, 300), (640, 300)], "结果 / 状态", lx=720, ly=322, lw=90)
arrow(d, [(500, 480), (500, 380)], "票价 / 开放时间", lx=500, ly=430, lw=140)
save(img, "dfd_context.png")

# ---------------------------------------------------------------------------
# Level-0 DFD
# ---------------------------------------------------------------------------
img, d = canvas(1000, 650)
# External entities
box(d, (30, 55, 150, 135), "旅行者", "external", size=18)
box(d, (30, 390, 160, 470), "官方数据 /\n人工维护", "external", size=15)
box(d, (820, 390, 980, 470), "高德 Web 服务", "external", size=15)
# Processes
box(d, (200, 50, 360, 130), "P1 需求录入\n与校验", "process", size=17)
box(d, (200, 220, 360, 300), "P2 候选景点\n检索与筛选", "process", size=17)
box(d, (200, 390, 360, 470), "P3 多日行程\n编排", "process", size=18)
box(d, (580, 390, 740, 470), "P4 路线 / 天气 /\n费用计算", "process", size=15)
box(d, (580, 220, 740, 300), "P5 结果展示\n与静态图", "process", size=17)
box(d, (580, 50, 740, 130), "P6 方案保存\n与版本管理", "process", size=16)
# Data stores
box(d, (200, 540, 390, 610), "D1 城市 / POI / 票价 / 开放时间", "store", size=13, bold=False)
box(d, (820, 50, 980, 120), "D2 方案 / 版本", "store", size=14, bold=False)
box(d, (820, 220, 980, 290), "D3 外部数据缓存", "store", size=14, bold=False)

# Flows
arrow(d, [(150, 95), (200, 95)], "出行条件", lx=175, ly=30, lw=80)
arrow(d, [(280, 130), (280, 220)], "已校验", lx=280, ly=175, lw=55)
arrow(d, [(280, 300), (280, 390)], "候选", lx=280, ly=345, lw=45)
arrow(d, [(360, 430), (580, 430)], "初排", lx=470, ly=408, lw=45)
arrow(d, [(660, 390), (660, 300)], "完整方案", lx=660, ly=345, lw=65)
arrow(d, [(660, 220), (660, 130)], "待保存", lx=660, ly=175, lw=55)
# P5 output to traveler via below P2
arrow(d, [(580, 300), (580, 315), (175, 315), (175, 135), (150, 135)],
      "行程结果", lx=430, ly=335, lw=65)
# P6 -> D2 and D2 -> P5
arrow(d, [(740, 90), (820, 90)], "版本", lx=780, ly=70, lw=40)
arrow(d, [(900, 120), (900, 180), (740, 180), (740, 220)],
      "历史", lx=820, ly=165, lw=40)
# P4 <-> Amap
arrow(d, [(740, 420), (820, 420)], "请求", lx=780, ly=400, lw=40)
arrow(d, [(820, 450), (740, 450)], "结果", lx=780, ly=470, lw=40)
# P4 <-> D3
arrow(d, [(660, 390), (660, 350), (900, 350), (900, 290)],
      "缓存", lx=780, ly=335, lw=40)
# D1 -> P2
arrow(d, [(390, 575), (410, 575), (410, 260), (360, 260)],
      "POI/票价", lx=430, ly=500, lw=80, anchor="lm")
# Official -> P3
arrow(d, [(160, 430), (200, 430)], "核验", lx=180, ly=408, lw=40)
save(img, "dfd_level0.png")

# ---------------------------------------------------------------------------
# Level-1 DFD: decomposition of P3
# ---------------------------------------------------------------------------
img, d = canvas(1000, 520)
box(d, (30, 220, 170, 300), "P2 候选景点", "process", size=15)
box(d, (30, 40, 170, 110), "D1 城市 / POI /\n票价 / 开放时间", "store", size=12, bold=False)
box(d, (220, 40, 380, 120), "P3.1 候选池\n整理", "process", size=16)
box(d, (220, 220, 380, 300), "P3.2 逐日\n分配", "process", size=16)
box(d, (430, 220, 590, 300), "P3.3 顺序\n与时间", "process", size=16)
box(d, (640, 220, 800, 300), "P3.4 约束\n校验", "process", size=16)
box(d, (640, 390, 800, 470), "P3.5 调整 /\n裁剪", "process", size=16)
box(d, (860, 330, 980, 410), "P4 路线 /\n天气 / 费用", "process", size=13)

arrow(d, [(170, 260), (220, 260)], "候选", lx=195, ly=240, lw=40)
arrow(d, [(170, 75), (220, 75)], "POI", lx=195, ly=55, lw=35)
arrow(d, [(300, 120), (300, 220)], "可排", lx=300, ly=170, lw=40)
arrow(d, [(380, 260), (430, 260)], "逐日", lx=405, ly=240, lw=40)
arrow(d, [(590, 260), (640, 260)], "时间表", lx=615, ly=240, lw=55)
arrow(d, [(720, 300), (720, 390)], "违规/未知", lx=720, ly=345, lw=55)
arrow(d, [(640, 430), (500, 430), (500, 340), (380, 340), (380, 300)],
      "调整", lx=500, ly=410, lw=40)
arrow(d, [(800, 260), (840, 260), (840, 370), (860, 370)],
      "可行/部分", lx=830, ly=240, lw=55)
save(img, "dfd_level1.png")
