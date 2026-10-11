"""Render the Bloom desktop companion as a transparent Pillow image."""

from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw

PLUM = (45, 34, 80, 255)
YELLOW = (255, 229, 88, 255)
PINK = (255, 127, 171, 255)
VIOLET = (139, 121, 255, 255)
SOFT = (255, 248, 241, 255)
MOODS = {"idle", "calm", "happy", "sad", "sleepy", "focused"}


def _blend(a, b, amount):
    return tuple(round(a[i] * (1 - amount) + b[i] * amount) for i in range(4))


@lru_cache(maxsize=8)
def _petal_base(size):
    """One upright, outlined radial petal, drawn at display resolution."""
    width = round(size * .27)
    height = round(size * .52)
    petal = Image.new("RGBA", (width + 8, height + 8))
    mask = Image.new("L", petal.size)
    d = ImageDraw.Draw(mask)
    d.ellipse((4, 4, width + 3, height + 3), fill=255)
    gradient = Image.new("RGBA", petal.size)
    pixels = gradient.load()
    for y in range(gradient.height):
        mix = min(1, max(0, y / gradient.height))
        color = _blend((*PINK[:3], 255), (*VIOLET[:3], 255), mix)
        for x in range(gradient.width):
            pixels[x, y] = color
    petal.paste(gradient, (0, 0), mask)
    ImageDraw.Draw(petal).ellipse((4, 4, width + 3, height + 3), outline=PLUM, width=max(2, size // 125))
    return petal


def _ellipse(draw, box, fill=PLUM, outline=None, width=1):
    draw.ellipse(tuple(round(v) for v in box), fill=fill, outline=outline, width=width)


@lru_cache(maxsize=8)
def _center_glow(size):
    """Soft radial light, later clipped to the opaque petals."""
    mask = Image.new("L", (size, size))
    pixels = mask.load()
    cx, cy = size / 2, size * .53
    spread = size * .22
    for y in range(size):
        for x in range(size):
            distance2 = (x - cx) ** 2 + (y - cy) ** 2
            pixels[x, y] = round(215 * math.exp(-distance2 / (2 * spread * spread)))
    return mask


def render_bloom(size=420, mood="idle", seconds=0.0, reduced_motion=False):
    """Return a square RGBA frame. `seconds` controls only decorative motion."""
    if mood not in MOODS:
        raise ValueError(f"Unknown Bloom mood: {mood}")
    if size < 80:
        raise ValueError("Bloom image must be at least 80 pixels square")
    t = 0.0 if reduced_motion else seconds
    image = Image.new("RGBA", (size, size))
    center_x, center_y = size / 2, size * .53
    if mood == "sad":
        center_y += size * .025
    elif mood == "happy":
        center_y += math.sin(t * 5.7) * size * .012
    elif mood == "sleepy":
        center_y += math.sin(t * .8) * size * .005

    base = _petal_base(size)
    for index in range(8):
        angle = index * 45
        if mood == "happy":
            angle += t * 360 / 2.2
        elif mood == "sleepy":
            angle += t * 360 / 22
        elif mood == "focused":
            angle += math.floor(t * 2.5) * 9
        else:
            angle += math.sin(t * .5) * 2
        radius = math.radians(angle)
        # Pillow rotates counter-clockwise; the base petal points upward.
        petal = base.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
        cx = center_x + math.sin(radius) * size * .18
        cy = center_y - math.cos(radius) * size * .18
        if mood == "sad" and not reduced_motion:
            fall = (t - index * 1.7) % 16
            if fall < 2.5:
                drift = fall / 2.5
                cx += (1 if index % 2 == 0 else -1) * drift * size * .40
                cy += drift * size * .55
                if fall > 1.9:
                    petal.putalpha(petal.getchannel("A").point(lambda a: round(a * (2.5 - fall) / .6)))
        image.alpha_composite(petal, (round(cx - petal.width / 2), round(cy - petal.height / 2)))

    # Blend light into the petals while preserving their existing alpha. A
    # translucent disk would reveal Tk's magenta transparency key on Windows.
    alpha = image.getchannel("A")
    light = _center_glow(size)
    if mood == "focused" and not reduced_motion:
        pulse = .85 + .15 * (1 + math.sin(t * 3))
        light = light.point(lambda value: min(255, round(value * pulse)))
    clipped = ImageChops.multiply(light, alpha)
    rgb = image.convert("RGB")
    rgb.paste(Image.new("RGB", image.size, YELLOW[:3]), (0, 0), clipped)
    image = Image.merge("RGBA", (*rgb.split(), alpha))

    draw = ImageDraw.Draw(image)
    r = size * (.187 if mood != "happy" else .187 + .004 * math.sin(t * 5.7))
    if mood == "sleepy":
        r *= 1 - .025 * (1 + math.sin(t * 1.2))
    _ellipse(draw, (center_x - r, center_y - r, center_x + r, center_y + r), fill=YELLOW, outline=PLUM, width=max(2, size // 175))

    eye_y = center_y - r * .10
    eye_dx = r * .25
    eye_w = max(3, size * .016)
    if mood == "sleepy":
        for x in (center_x - eye_dx, center_x + eye_dx):
            _ellipse(draw, (x - eye_w * 1.25, eye_y - eye_w * .18, x + eye_w * 1.25, eye_y + eye_w * .18))
    else:
        for x in (center_x - eye_dx, center_x + eye_dx):
            _ellipse(draw, (x - eye_w * .52, eye_y - eye_w * 1.1, x + eye_w * .52, eye_y + eye_w * 1.1))
    if mood == "focused":
        stroke = max(2, size // 115)
        glass_r = r * .26
        for x in (center_x - eye_dx, center_x + eye_dx):
            _ellipse(draw, (x - glass_r, eye_y - glass_r, x + glass_r, eye_y + glass_r), fill=None, outline=PLUM, width=stroke)
        draw.line((center_x - eye_dx + glass_r, eye_y, center_x + eye_dx - glass_r, eye_y), fill=PLUM, width=stroke)
        draw.line((center_x - eye_dx - glass_r, eye_y, center_x - r * .88, eye_y), fill=PLUM, width=stroke)
        draw.line((center_x + eye_dx + glass_r, eye_y, center_x + r * .88, eye_y), fill=PLUM, width=stroke)
        brow_y = eye_y - glass_r * 1.25
        draw.line((center_x - eye_dx - glass_r * .65, brow_y - size * .012,
                   center_x - eye_dx + glass_r * .65, brow_y + size * .012), fill=PLUM, width=stroke)
        draw.line((center_x + eye_dx - glass_r * .65, brow_y + size * .012,
                   center_x + eye_dx + glass_r * .65, brow_y - size * .012), fill=PLUM, width=stroke)

    mouth_y = center_y + r * .32
    mouth_w = r * (.19 if mood in ("sad", "focused") else .27)
    mouth_h = r * (.085 if mood in ("sad", "focused") else .13)
    if mood == "sleepy":
        mouth_w, mouth_h = r * .13, r * (.16 + (0 if reduced_motion else .035 * (1 + math.sin(t * 2))))
    _ellipse(draw, (center_x - mouth_w, mouth_y - mouth_h, center_x + mouth_w, mouth_y + mouth_h))

    if mood == "happy":
        for i in range(3):
            ray = size * (.25 + i * .016)
            angle = math.radians(-90 + i * 45)
            x1, y1 = center_x + math.cos(angle) * ray, center_y + math.sin(angle) * ray
            x2, y2 = center_x + math.cos(angle) * (ray + size * .065), center_y + math.sin(angle) * (ray + size * .065)
            draw.line((x1, y1, x2, y2), fill=PLUM, width=max(2, size // 95))
    return image
