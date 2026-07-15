import os

BLOCKS_DIR = os.path.join(os.path.dirname(__file__), "app", "assets", "cad_blocks")

def rect(x, y, w, h, rx=0, fill="none"):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="black" stroke-width="1.5" />'

def circle(cx, cy, r, fill="none"):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="black" stroke-width="1.5" />'

def ellipse(cx, cy, rx, ry, fill="none"):
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="black" stroke-width="1.5" />'

def line(x1, y1, x2, y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="black" stroke-width="1.5" />'

def path(d, fill="none"):
    return f'<path d="{d}" fill="{fill}" stroke="black" stroke-width="1.5" />'

def chair_top(cx, cy, r=15):
    # A simple chair representing a round seat with a backrest
    return circle(cx, cy, r) + path(f"M {cx-r} {cy} A {r} {r} 0 0 1 {cx+r} {cy}")

def wrap_svg(content, w=200, h=200):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">' + content + '</svg>'

SVGS = {}

# --- DOORS & COLUMNS ---
SVGS["door_single.svg"] = wrap_svg(path("M 5 95 L 5 5 A 90 90 0 0 1 95 95 Z") + rect(0, 95, 10, 5) + rect(90, 95, 10, 5), 100, 100)
SVGS["door_double.svg"] = wrap_svg(path("M 5 95 L 5 5 A 90 90 0 0 1 95 95 Z") + path("M 185 95 L 185 5 A 90 90 0 0 0 95 95 Z"), 190, 100)
SVGS["square_column.svg"] = wrap_svg(rect(10, 10, 80, 80), 100, 100)
SVGS["door_sliding.svg"] = wrap_svg(rect(5, 45, 90, 5) + rect(95, 50, 90, 5), 190, 100)
SVGS["bifold_doors.svg"] = wrap_svg(line(5,95, 45,45) + line(45,45, 95,95) + line(95,95, 145,45) + line(145,45, 185,95), 190, 100)

# --- DINING ROOM ---
SVGS["table_round.svg"] = wrap_svg(circle(100, 100, 60), 200, 200)
SVGS["table_round_4stools.svg"] = wrap_svg(circle(100, 100, 50) + circle(100, 30, 15) + circle(100, 170, 15) + circle(30, 100, 15) + circle(170, 100, 15), 200, 200)
SVGS["table_round_inner_ring.svg"] = wrap_svg(circle(100, 100, 60) + circle(100, 100, 40), 200, 200)
SVGS["table_round_outer_rim.svg"] = wrap_svg(circle(100, 100, 60) + circle(100, 100, 55), 200, 200)

SVGS["table_oval_2chairs.svg"] = wrap_svg(ellipse(100, 100, 80, 40) + chair_top(100, 40) + chair_top(100, 160), 200, 200)
SVGS["table_round_4chairs.svg"] = wrap_svg(circle(100, 100, 50) + chair_top(100, 30) + chair_top(100, 170) + chair_top(30, 100) + chair_top(170, 100), 200, 200)
SVGS["table_rect.svg"] = wrap_svg(rect(40, 60, 120, 80), 200, 200)
SVGS["table_rect_variant.svg"] = wrap_svg(rect(40, 60, 120, 80, rx=10) + rect(50, 70, 100, 60, rx=5), 200, 200)

SVGS["table_oval_6chairs.svg"] = wrap_svg(ellipse(150, 100, 100, 50) + chair_top(150,30) + chair_top(150,170) + chair_top(90,30) + chair_top(90,170) + chair_top(210,30) + chair_top(210,170) + chair_top(30,100) + chair_top(270,100), 300, 200)
SVGS["table_sq_2chairs.svg"] = wrap_svg(rect(60, 60, 80, 80) + chair_top(100, 40) + chair_top(100, 160), 200, 200)
SVGS["table_sq_4chairs.svg"] = wrap_svg(rect(60, 60, 80, 80) + chair_top(100, 40) + chair_top(100, 160) + chair_top(40, 100) + chair_top(160, 100), 200, 200)
SVGS["table_rect_6chairs.svg"] = wrap_svg(rect(50, 60, 150, 80) + chair_top(125, 40) + chair_top(125, 160) + chair_top(75, 40) + chair_top(75, 160) + chair_top(175, 40) + chair_top(175, 160) + chair_top(30, 100) + chair_top(220, 100), 250, 200)

# --- KITCHEN ---
SVGS["stove_2burner.svg"] = wrap_svg(rect(10, 10, 80, 80) + circle(50, 30, 15) + circle(50, 70, 15), 100, 100)
SVGS["stove_3burner.svg"] = wrap_svg(rect(10, 10, 80, 80) + circle(30, 30, 12) + circle(70, 30, 12) + circle(50, 70, 15), 100, 100)
SVGS["stove_3burner_variant.svg"] = wrap_svg(rect(10, 10, 80, 80) + circle(50, 30, 12) + circle(30, 70, 15) + circle(70, 70, 15), 100, 100)
SVGS["fridge.svg"] = wrap_svg(rect(10, 10, 80, 80) + line(10, 30, 90, 30), 100, 100)
SVGS["sink_circular.svg"] = wrap_svg(rect(10, 10, 80, 80) + circle(50, 50, 30) + circle(50, 50, 5), 100, 100)
SVGS["sink_double_basin.svg"] = wrap_svg(rect(10, 10, 140, 80) + rect(20, 20, 50, 60, rx=5) + rect(90, 20, 50, 60, rx=5) + circle(45, 50, 3) + circle(115, 50, 3), 160, 100)

# --- BEDROOM ---
SVGS["bed_double_blanket.svg"] = wrap_svg(rect(10, 10, 140, 180, rx=5) + rect(20, 20, 50, 30, rx=3) + rect(90, 20, 50, 30, rx=3) + path("M 10 90 Q 80 70 150 90 L 150 190 L 10 190 Z"), 160, 200)
SVGS["bed_double_pillows.svg"] = wrap_svg(rect(10, 10, 140, 180, rx=5) + rect(20, 20, 50, 30, rx=3) + rect(90, 20, 50, 30, rx=3) + line(10, 60, 150, 60), 160, 200)
SVGS["desk.svg"] = wrap_svg(rect(10, 10, 120, 60) + rect(30, 70, 40, 20) + circle(50, 80, 10), 140, 100)
SVGS["wardrobe.svg"] = wrap_svg(rect(10, 10, 180, 60) + line(100, 10, 100, 70) + line(90, 40, 95, 40) + line(110, 40, 105, 40), 200, 80)
SVGS["rug_circular.svg"] = wrap_svg(circle(100, 100, 80), 200, 200)
SVGS["radiator.svg"] = wrap_svg(rect(10, 10, 80, 20) + line(20, 10, 20, 30) + line(40, 10, 40, 30) + line(60, 10, 60, 30) + line(80, 10, 80, 30), 100, 40)
SVGS["houseplant.svg"] = wrap_svg(circle(50, 50, 20) + path("M 50 50 Q 80 20 50 10 Q 20 20 50 50") + path("M 50 50 Q 80 80 90 50 Q 80 20 50 50") + path("M 50 50 Q 20 80 50 90 Q 80 80 50 50") + path("M 50 50 Q 20 20 10 50 Q 20 80 50 50"), 100, 100)
SVGS["bed_single.svg"] = wrap_svg(rect(10, 10, 80, 180, rx=5) + rect(25, 20, 50, 30, rx=3) + line(10, 60, 90, 60), 100, 200)
SVGS["bed_single_vertical.svg"] = wrap_svg(rect(10, 10, 180, 80, rx=5) + rect(20, 25, 30, 50, rx=3) + line(60, 10, 60, 90), 200, 100)
SVGS["ceiling_fan.svg"] = wrap_svg(circle(100, 100, 15) + path("M 100 85 L 90 20 A 10 10 0 0 1 110 20 Z") + path("M 100 115 L 90 180 A 10 10 0 0 0 110 180 Z") + path("M 85 100 L 20 90 A 10 10 0 0 0 20 110 Z") + path("M 115 100 L 180 90 A 10 10 0 0 1 180 110 Z"), 200, 200)
SVGS["rug_rectangular.svg"] = wrap_svg(rect(20, 40, 160, 120), 200, 200)
SVGS["rug_oval.svg"] = wrap_svg(ellipse(100, 100, 80, 50), 200, 200)

# --- LIVING ROOM ---
SVGS["sofa_3_slanted.svg"] = wrap_svg(path("M 10 30 L 190 30 L 180 80 L 20 80 Z") + rect(10, 10, 180, 20, rx=5) + rect(0, 30, 20, 60, rx=3) + rect(180, 30, 20, 60, rx=3), 200, 100)
SVGS["sofa_3_cushions.svg"] = wrap_svg(rect(10, 10, 180, 20, rx=5) + rect(0, 30, 20, 60, rx=3) + rect(180, 30, 20, 60, rx=3) + rect(20, 30, 53, 50, rx=2) + rect(73, 30, 53, 50, rx=2) + rect(126, 30, 53, 50, rx=2), 200, 100)
SVGS["sofa_3_straight.svg"] = wrap_svg(rect(10, 10, 180, 20) + rect(0, 30, 20, 60) + rect(180, 30, 20, 60) + rect(20, 30, 160, 50), 200, 100)
SVGS["sofa_3_block.svg"] = wrap_svg(rect(0, 0, 200, 100) + rect(20, 20, 160, 80), 200, 100)
SVGS["loveseat_2.svg"] = wrap_svg(rect(10, 10, 120, 20, rx=5) + rect(0, 30, 20, 60, rx=3) + rect(120, 30, 20, 60, rx=3) + rect(20, 30, 50, 50, rx=2) + rect(70, 30, 50, 50, rx=2), 140, 100)
SVGS["armchair_square.svg"] = wrap_svg(rect(10, 10, 80, 20, rx=5) + rect(0, 30, 20, 60, rx=3) + rect(80, 30, 20, 60, rx=3) + rect(20, 30, 60, 50, rx=2), 100, 100)
SVGS["armchair_rounded.svg"] = wrap_svg(path("M 10 90 L 10 30 A 40 40 0 0 1 90 30 L 90 90 Z") + circle(50, 50, 25), 100, 100)
SVGS["sofa_curved_piece.svg"] = wrap_svg(path("M 10 90 A 80 80 0 0 1 90 10 L 90 30 A 60 60 0 0 0 30 90 Z"), 100, 100)
SVGS["armchair_barrel.svg"] = wrap_svg(circle(50, 50, 40) + path("M 10 50 A 40 40 0 0 0 90 50 L 80 50 A 30 30 0 0 1 20 50 Z"), 100, 100)
SVGS["armchair_tub.svg"] = wrap_svg(path("M 10 10 L 90 10 L 90 60 A 40 40 0 0 1 10 60 Z") + path("M 20 20 L 80 20 L 80 60 A 30 30 0 0 1 20 60 Z"), 100, 100)
SVGS["ottoman_round.svg"] = wrap_svg(circle(50, 50, 40) + circle(50, 50, 30), 100, 100)
SVGS["chaise_lounge.svg"] = wrap_svg(rect(10, 10, 60, 180, rx=10) + rect(10, 10, 60, 40, rx=10), 80, 200)
SVGS["tv_crt.svg"] = wrap_svg(path("M 10 40 Q 50 10 90 40 L 80 90 L 20 90 Z") + rect(30, 80, 40, 10), 100, 100)
SVGS["laptop.svg"] = wrap_svg(rect(10, 40, 80, 50, rx=2) + rect(20, 20, 60, 40, rx=2), 100, 100)
SVGS["table_coffee_sq.svg"] = wrap_svg(rect(10, 10, 80, 80) + rect(20, 20, 60, 60), 100, 100)

# --- BATH ROOM ---
SVGS["toilet.svg"] = wrap_svg(rect(30, 10, 40, 20, rx=3) + ellipse(50, 60, 15, 25), 100, 100)
SVGS["toilet_variant.svg"] = wrap_svg(rect(30, 10, 40, 25, rx=5) + ellipse(50, 60, 18, 28) + circle(50, 22, 3), 100, 100)
SVGS["shower_corner.svg"] = wrap_svg(path("M 10 10 L 90 10 A 80 80 0 0 1 10 90 Z") + line(10, 90, 90, 10) + circle(30, 30, 5), 100, 100)
SVGS["shower_corner_variant.svg"] = wrap_svg(path("M 10 10 L 90 10 A 80 80 0 0 1 10 90 Z") + path("M 20 20 L 80 20 A 60 60 0 0 1 20 80 Z") + circle(30, 30, 5), 100, 100)
SVGS["washbasin_rect.svg"] = wrap_svg(rect(20, 10, 60, 40, rx=5) + rect(30, 20, 40, 20, rx=5) + circle(50, 30, 3), 100, 60)
SVGS["washbasin_semi.svg"] = wrap_svg(path("M 20 10 L 80 10 A 30 30 0 0 1 20 10 Z") + circle(50, 25, 3), 100, 60)
SVGS["washbasin_round.svg"] = wrap_svg(circle(50, 50, 30) + circle(50, 50, 20) + circle(50, 50, 3), 100, 100)
SVGS["washbasin_oval.svg"] = wrap_svg(ellipse(50, 50, 40, 30) + ellipse(50, 50, 30, 20) + circle(50, 50, 3), 100, 100)
SVGS["washbasin_square.svg"] = wrap_svg(rect(20, 20, 60, 60) + rect(30, 30, 40, 40) + circle(50, 50, 3), 100, 100)
SVGS["sink_double_rect.svg"] = wrap_svg(rect(10, 10, 140, 40, rx=5) + rect(20, 20, 50, 20, rx=5) + rect(90, 20, 50, 20, rx=5) + circle(45, 30, 3) + circle(115, 30, 3), 160, 60)
SVGS["sink_double_square.svg"] = wrap_svg(rect(10, 10, 140, 60) + rect(20, 20, 50, 40) + rect(90, 20, 50, 40) + circle(45, 40, 3) + circle(115, 40, 3), 160, 80)
SVGS["sink_double_round.svg"] = wrap_svg(rect(10, 10, 140, 60, rx=5) + circle(45, 40, 20) + circle(115, 40, 20) + circle(45, 40, 3) + circle(115, 40, 3), 160, 80)
SVGS["bathtub_oval_freestanding.svg"] = wrap_svg(ellipse(100, 50, 80, 40) + ellipse(100, 50, 70, 30) + circle(50, 50, 5), 200, 100)
SVGS["bathtub_dropin.svg"] = wrap_svg(rect(10, 10, 180, 80) + ellipse(100, 50, 70, 30) + circle(50, 50, 5), 200, 100)
SVGS["bathtub_rect_drain_left.svg"] = wrap_svg(rect(10, 10, 180, 80) + rect(20, 20, 160, 60, rx=10) + circle(40, 50, 5), 200, 100)
SVGS["bathtub_rect_drain_right.svg"] = wrap_svg(rect(10, 10, 180, 80) + rect(20, 20, 160, 60, rx=10) + circle(160, 50, 5), 200, 100)

def main():
    os.makedirs(BLOCKS_DIR, exist_ok=True)
    for filename, content in SVGS.items():
        filepath = os.path.join(BLOCKS_DIR, filename)
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Created: {filepath}")

if __name__ == "__main__":
    main()
