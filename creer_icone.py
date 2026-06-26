# -*- coding: utf-8 -*-
"""
creer_icone.py — Genere logo_OPALE.ico pour associer a Lancer_OPALE.bat
Requiert : Pillow  (pip install pillow)
"""

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("[ERREUR] Pillow n'est pas installe.")
    print("  Lancez :  pip install pillow")
    input("\nAppuyez sur Entree pour fermer...")
    raise SystemExit(1)

import os


def _draw_icon(S):
    """Dessine l'icone en taille S x S et retourne une image RGBA."""
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d    = ImageDraw.Draw(img)

    r = max(4, S // 6)

    # ── Fond arrondi bleu nuit ────────────────────────────────────────────
    d.rounded_rectangle([0, 0, S-1, S-1], radius=r, fill=(11, 37, 69, 255))

    # ── Montagne (silhouette sombre) ──────────────────────────────────────
    mtn = [
        (int(S*.06), int(S*.93)),
        (int(S*.26), int(S*.50)),
        (int(S*.38), int(S*.63)),
        (int(S*.56), int(S*.37)),
        (int(S*.74), int(S*.53)),
        (int(S*.88), int(S*.43)),
        (int(S*.96), int(S*.93)),
    ]
    d.polygon(mtn, fill=(22, 58, 107, 255))

    # ── Hydrogramme — points de la courbe ────────────────────────────────
    curve = [
        (int(S*.02), int(S*.91)),
        (int(S*.10), int(S*.91)),
        (int(S*.20), int(S*.90)),
        (int(S*.28), int(S*.89)),
        (int(S*.33), int(S*.87)),
        (int(S*.36), int(S*.80)),
        (int(S*.38), int(S*.67)),
        (int(S*.39), int(S*.50)),
        (int(S*.40), int(S*.35)),
        (int(S*.40), int(S*.18)),   # PIC
        (int(S*.42), int(S*.30)),
        (int(S*.44), int(S*.44)),
        (int(S*.47), int(S*.55)),
        (int(S*.52), int(S*.64)),
        (int(S*.59), int(S*.71)),
        (int(S*.68), int(S*.76)),
        (int(S*.78), int(S*.80)),
        (int(S*.88), int(S*.83)),
        (int(S*.97), int(S*.85)),
    ]

    # Remplissage sous la courbe
    flood = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flood)
    fill_pts = curve + [(S-1, S-1), (0, S-1)]
    fd.polygon(fill_pts, fill=(26, 107, 181, 100))
    img = Image.alpha_composite(img, flood)
    d = ImageDraw.Draw(img)

    # Seuils de vigilance (pointilles horizontaux)
    seuils = [
        (0.68, (255, 221,  87, 185)),   # jaune
        (0.55, (255, 152,   0, 185)),   # orange
        (0.42, (229,  57,  53, 185)),   # rouge
    ]
    seg = max(3, S // 32)
    gap = max(2, S // 50)
    mx  = max(2, S // 12)
    lw  = max(1, S // 100)
    for frac, col in seuils:
        sy = int(S * frac)
        x  = mx
        while x < S - mx:
            d.line([(x, sy), (min(x + seg, S - mx), sy)], fill=col, width=lw)
            x += seg + gap
        pr = max(3, S // 50)
        cx = S - mx - pr - 1
        d.ellipse([cx-pr, sy-pr, cx+pr, sy+pr], fill=col[:3]+(220,))

    # Courbe hydrogramme
    lw2 = max(2, S // 55)
    d.line(curve, fill=(91, 184, 245, 255), width=lw2)

    # Point rouge au pic
    px, py = int(S*.40), int(S*.18)
    pr2 = max(4, S // 42)
    d.ellipse([px-pr2, py-pr2, px+pr2, py+pr2], fill=(229, 57, 53, 255))
    wr = max(2, S // 85)
    d.ellipse([px-wr, py-wr, px+wr, py+wr], fill=(255, 255, 255, 255))

    # Pointille vertical pic
    dot_col = (229, 57, 53, 150)
    for y in range(py + pr2 + 3, int(S*.90), max(3, S//28)):
        d.ellipse([px-1, y-1, px+1, y+1], fill=dot_col)

    # Goutte d'eau haut gauche
    gx, gy = int(S*.14), int(S*.09)
    gh     = max(8, S // 16)
    drop   = [
        (gx,           gy),
        (gx - gh//3,   gy + int(gh*.85)),
        (gx,           gy + gh),
        (gx + gh//3,   gy + int(gh*.85)),
    ]
    d.polygon(drop, fill=(91, 184, 245, 220))

    # ── "OPALE" en bas de l'icone (tailles >= 48) ────────────────────────
    if S >= 48:
        font_size = max(8, S // 9)
        font = None
        for candidate in [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
        ]:
            try:
                font = ImageFont.truetype(candidate, font_size)
                break
            except OSError:
                continue
        if font is None:
            font = ImageFont.load_default()
        text = "OPALE"
        bbox = d.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (S - tw) // 2
        ty = S - th - max(3, S // 20)
        # Ombre legere
        d.text((tx + 1, ty + 1), text, font=font, fill=(0, 0, 0, 160))
        d.text((tx, ty), text, font=font, fill=(255, 255, 255, 230))

    # Bordure fine
    bw = max(1, S // 90)
    d.rounded_rectangle([0, 0, S-1, S-1], radius=r,
                        outline=(42, 95, 168, 200), width=bw)
    return img


def main():
    base     = os.path.dirname(os.path.abspath(__file__))
    ico_path = os.path.join(base, "logo_OPALE.ico")

    sizes  = [256, 128, 64, 48, 32, 16]
    frames = [_draw_icon(s) for s in sizes]
    frames[0].save(ico_path, format="ICO",
                   append_images=frames[1:],
                   sizes=[(s, s) for s in sizes])

    print(f"[OK] Icone generee : {ico_path}")
    print()
    print("Pour associer l'icone a Lancer_OPALE.bat :")
    print("  1. Clic droit sur Lancer_OPALE.bat > Envoyer vers > Bureau (creer un raccourci)")
    print("  2. Clic droit sur le raccourci > Proprietes > Changer d'icone...")
    print(f"  3. Parcourir vers : {ico_path}")
    print()
    input("Appuyez sur Entree pour fermer...")


if __name__ == "__main__":
    main()
