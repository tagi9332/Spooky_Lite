"""Generates the Spooky Lite app icon: a small cartoon ghost.

Draws the ghost procedurally with Pillow (no external image assets needed)
and writes assets/icon.ico with the standard multi-resolution sizes used by
Windows (16/32/48/64/128/256 px), plus a standalone assets/icon.png.

Run from the project root:
    python assets/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 256  # master render size; downscaled for smaller .ico frames
OUT_DIR = Path(__file__).resolve().parent

GHOST_WHITE = (240, 243, 255, 255)
GHOST_SHADE = (205, 212, 235, 255)  # subtle shading on the body
OUTLINE = (70, 75, 100, 255)
EYE_COLOR = (45, 48, 66, 255)
BLUSH = (255, 170, 190, 130)


def draw_ghost(size: int) -> Image.Image:
    # Render at 4x supersampling then downscale for clean anti-aliased edges.
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = s * 0.12
    left, right = margin, s - margin
    top = s * 0.10
    body_bottom = s * 0.86
    width = right - left
    radius = width / 2

    # --- Body: rounded top (dome) + straight sides down to a wavy hem ---
    body = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(body)

    # Dome (top half of the body is a circle arc).
    bdraw.pieslice([left, top, right, top + radius * 2], 180, 360, fill=GHOST_WHITE)
    # Rectangle filling the straight midsection.
    bdraw.rectangle([left, top + radius, right, body_bottom], fill=GHOST_WHITE)

    # Wavy bottom hem: scalloped using overlapping circles cut into the base,
    # then re-add rounded "feet" bumps so the silhouette reads as a ghost tail.
    bumps = 8
    bump_w = width / bumps
    for i in range(bumps):
        cx = left + bump_w * (i + 0.5)
        if i % 2 == 0:
            # Rounded foot bump pointing down.
            bdraw.ellipse(
                [cx - bump_w / 2, body_bottom - bump_w / 2, cx + bump_w / 2, body_bottom + bump_w / 2],
                fill=GHOST_WHITE,
            )
        else:
            # Notch cut upward between feet (erase to transparent).
            bdraw.ellipse(
                [cx - bump_w / 2, body_bottom - bump_w / 2, cx + bump_w / 2, body_bottom + bump_w / 2],
                fill=(0, 0, 0, 0),
            )

    img.alpha_composite(body)

    # Soft shading crescent on the right side of the body for a 3D feel.
    # Drawn oversized and heavily blurred so it reads as gentle gradient
    # shading rather than a hard edge cutting across the face.
    shade = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shade)
    sdraw.ellipse(
        [left + width * 0.62, top + radius * 0.85, right + width * 0.55, body_bottom + width * 0.25],
        fill=GHOST_SHADE,
    )
    shade = shade.filter(ImageFilter.GaussianBlur(radius=s * 0.05))
    # Mask the shading to the body silhouette only, and reduce its strength.
    body_mask = body.split()[3]
    shade_alpha = Image.composite(shade.split()[3], Image.new("L", (s, s), 0), body_mask)
    shade_alpha = shade_alpha.point(lambda a: int(a * 0.5))
    shade.putalpha(shade_alpha)
    img.alpha_composite(shade)

    # Outline for a friendly cartoon look.
    outline_w = max(1, int(s * 0.012))
    outline_layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(outline_layer)
    # Note: arc() (not pieslice()) so only the curve is drawn, not the two
    # straight radii pieslice would add from the circle's center out to the
    # left/right edges — those would cut a seam straight across the face.
    odraw.arc([left, top, right, top + radius * 2], 180, 360, fill=OUTLINE, width=outline_w)
    odraw.line([left, top + radius, left, body_bottom - bump_w * 0.1], fill=OUTLINE, width=outline_w)
    odraw.line([right, top + radius, right, body_bottom - bump_w * 0.1], fill=OUTLINE, width=outline_w)
    for i in range(bumps):
        cx = left + bump_w * (i + 0.5)
        if i % 2 == 0:
            odraw.arc(
                [cx - bump_w / 2, body_bottom - bump_w / 2, cx + bump_w / 2, body_bottom + bump_w / 2],
                0, 180, fill=OUTLINE, width=outline_w,
            )
    img.alpha_composite(outline_layer)

    # --- Face ---
    eye_w, eye_h = width * 0.11, width * 0.14
    eye_y = top + radius * 0.95
    for ex in (left + width * 0.33, left + width * 0.67):
        draw.ellipse([ex - eye_w / 2, eye_y - eye_h / 2, ex + eye_w / 2, eye_y + eye_h / 2], fill=EYE_COLOR)
        # tiny eye highlight
        hl = eye_w * 0.28
        draw.ellipse(
            [ex - eye_w / 2 + hl * 0.3, eye_y - eye_h / 2 + hl * 0.2, ex - eye_w / 2 + hl * 1.1, eye_y - eye_h / 2 + hl],
            fill=(255, 255, 255, 230),
        )

    # Rosy cheeks
    cheek_w = width * 0.10
    cheek_y = eye_y + eye_h * 0.9
    for cx in (left + width * 0.22, left + width * 0.78):
        draw.ellipse([cx - cheek_w / 2, cheek_y - cheek_w / 2, cx + cheek_w / 2, cheek_y + cheek_w / 2], fill=BLUSH)

    # Small open "ooo" mouth
    mouth_w, mouth_h = width * 0.16, width * 0.18
    mouth_cx = left + width * 0.5
    mouth_cy = eye_y + eye_h * 1.5
    draw.ellipse(
        [mouth_cx - mouth_w / 2, mouth_cy - mouth_h / 2, mouth_cx + mouth_w / 2, mouth_cy + mouth_h / 2],
        fill=EYE_COLOR,
    )

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    master = draw_ghost(SIZE)
    png_path = OUT_DIR / "icon.png"
    master.save(png_path)

    ico_path = OUT_DIR / "icon.ico"
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [master.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[-1].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])

    print(f"Wrote {png_path}")
    print(f"Wrote {ico_path}")


if __name__ == "__main__":
    main()
