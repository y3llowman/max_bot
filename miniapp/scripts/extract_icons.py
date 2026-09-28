"""Извлекает иконки из UI-кита дизайнера в src/components/icons.ts.

Запуск из папки miniapp:  python scripts/extract_icons.py [путь к UI Kit v2.svg]

Иконки в ките — раздел «Иконки», сетка `Grid`: линейные, 24×24, обводка 1.6,
скруглённые концы, цвет через currentColor. Экспорт Фигмы кладёт контуры в
абсолютных координатах доски без рамки 24×24. Каждая иконка в ките лежит на
квадратной подложке 48×48 — её центр и есть центр ячейки; подложку в вывод не
берём. Для иконок без подложки центр восстанавливается по сетке: центры рамок
группируются в строки и столбцы, медиана даёт центр ячейки. Затем все
координаты контуров переводятся в локальные 24×24.

SVG нужно выгружать из Фигмы с выключенным «Outline text» и включённым
«Include "id" attribute» — иначе имена слоёв пропадут.
"""
import os
import re
import statistics
import sys
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"
HERE = os.path.dirname(os.path.abspath(__file__))
KIT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "design", "UI Kit v2.svg")
OUT = os.path.join(HERE, "..", "src", "components", "icons.ts")

TOKEN = re.compile(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?")
SKIP = [None]  # подложка текущей иконки, которую не выводим
PARAMS = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7, "Z": 0}


def fix(s):
    """Фигма пишет UTF-8 байты имён слоёв отдельными сущностями — склеиваем."""
    if not s:
        return ""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def fmt(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def walk_path(d, fn):
    """Проходит по командам контура. fn(cmd, index_in_params, value) -> value."""
    out, toks, i, cmd = [], TOKEN.findall(d), 0, None
    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            out.append(cmd)
            i += 1
            if cmd.upper() == "Z":
                continue
        n = PARAMS[cmd.upper()]
        vals = [float(t) for t in toks[i:i + n]]
        i += n
        out.append(" ".join(fmt(fn(cmd, k, v)) for k, v in enumerate(vals)))
        if cmd == "M":
            cmd = "L"
        elif cmd == "m":
            cmd = "l"
    return " ".join(out)


def is_x(cmd, k):
    c = cmd.upper()
    if c == "H":
        return True
    if c == "V":
        return False
    if c == "A":
        return k == 5
    return k % 2 == 0


def is_coord(cmd, k):
    return cmd.upper() != "A" or k in (5, 6)


def tile(el):
    """Подложка ячейки в ките — квадрат ≥40px вокруг иконки. Не часть иконки,
    но её центр — точный центр ячейки 24×24."""
    for r in el.iter(NS + "rect"):
        w, h = r.get("width"), r.get("height")
        if w and h and float(w) == float(h) and float(w) >= 40:
            return r
    return None


def bbox(el):
    t = tile(el)
    if t is not None:
        x, y, w = float(t.get("x") or 0), float(t.get("y") or 0), float(t.get("width"))
        return x, y, x + w, y + w
    xs, ys = [], []

    def grab(cmd, k, v):
        if cmd.isupper() and is_coord(cmd, k):
            (xs if is_x(cmd, k) else ys).append(v)
        return v

    for p in el.iter():
        tag = p.tag.replace(NS, "")
        if tag == "path" and p.get("d"):
            walk_path(p.get("d"), grab)
        elif tag in ("circle", "ellipse"):
            cx, cy = float(p.get("cx")), float(p.get("cy"))
            rx = float(p.get("r") or p.get("rx"))
            ry = float(p.get("r") or p.get("ry"))
            xs += [cx - rx, cx + rx]
            ys += [cy - ry, cy + ry]
        elif tag == "rect" and p.get("width"):
            x, y = float(p.get("x") or 0), float(p.get("y") or 0)
            xs += [x, x + float(p.get("width"))]
            ys += [y, y + float(p.get("height"))]
        elif tag == "line":
            xs += [float(p.get("x1")), float(p.get("x2"))]
            ys += [float(p.get("y1")), float(p.get("y2"))]
    return min(xs), min(ys), max(xs), max(ys)


def cluster(values, tol=14):
    """Группирует близкие значения; возвращает функцию значение → центр группы."""
    groups = []
    for v in sorted(values):
        if groups and v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    centers = [statistics.median(g) for g in groups]
    return lambda v: min(centers, key=lambda c: abs(c - v))


def paint(value):
    if value in (None, "none"):
        return value
    return "currentColor"


def serialize(el, ox, oy):
    tag = el.tag.replace(NS, "")
    attrs = {}
    if tag == "path":
        attrs["d"] = walk_path(el.get("d"), lambda c, k, v: v - (ox if is_x(c, k) else oy)
                               if c.isupper() and is_coord(c, k) else v)
        if el.get("fill-rule"):
            attrs["fill-rule"] = el.get("fill-rule")
        if el.get("clip-rule"):
            attrs["clip-rule"] = el.get("clip-rule")
    elif tag in ("circle", "ellipse"):
        attrs["cx"] = fmt(float(el.get("cx")) - ox)
        attrs["cy"] = fmt(float(el.get("cy")) - oy)
        for a in ("r", "rx", "ry"):
            if el.get(a):
                attrs[a] = el.get(a)
    elif tag == "rect":
        if el is SKIP[0]:
            return ""
        attrs["x"] = fmt(float(el.get("x") or 0) - ox)
        attrs["y"] = fmt(float(el.get("y") or 0) - oy)
        for a in ("width", "height", "rx"):
            if el.get(a):
                attrs[a] = el.get(a)
    elif tag == "line":
        for a, o in (("x1", ox), ("x2", ox), ("y1", oy), ("y2", oy)):
            attrs[a] = fmt(float(el.get(a)) - o)
    else:
        return "".join(serialize(c, ox, oy) for c in el)
    # толщину и скругление задаёт <svg> в Icon.tsx; тут только то, что отличается
    fill = paint(el.get("fill"))
    stroke = paint(el.get("stroke"))
    if fill and fill != "none":
        attrs["fill"] = fill
    if stroke is None and el.get("fill") not in (None, "none"):
        attrs["stroke"] = "none"
    if el.get("stroke-width") and el.get("stroke-width") != "1.6":
        attrs["stroke-width"] = el.get("stroke-width")
    return f"<{tag} " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + "/>"


def main():
    root = ET.parse(KIT).getroot()
    grid = None
    for g in root.iter(NS + "g"):
        if fix(g.get("id")) == "Иконки":
            grid = next((c for c in g if fix(c.get("id")).startswith("Grid")), None)
    if grid is None:
        sys.exit("Не нашёл раздел «Иконки» → Grid в ките")

    icons = []
    for g in grid:
        m = re.match(r"^Icon/([\w-]+?)(_\d+)?$", fix(g.get("id")))
        if m:
            icons.append((m.group(1), g, bbox(g)))

    col = cluster([(b[0] + b[2]) / 2 for _, _, b in icons])
    row = cluster([(b[1] + b[3]) / 2 for _, _, b in icons])

    lines = [
        "// Сгенерировано scripts/extract_icons.py из design/UI Kit v2.svg — не править руками.",
        "// Иконки 24×24, обводка 1.6, скруглённые концы; цвет наследуется через currentColor.",
        "",
        "export const icons = {",
    ]
    names = []
    for name, g, b in sorted(icons, key=lambda t: t[0]):
        if name in names:
            continue
        names.append(name)
        ox = col((b[0] + b[2]) / 2) - 12
        oy = row((b[1] + b[3]) / 2) - 12
        SKIP[0] = tile(g)
        body = serialize(g, ox, oy)
        lines.append(f'  "{name}": `{body}`,')
    lines += ["} as const;", "", "export type IconName = keyof typeof icons;", ""]
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"{len(names)} иконок → {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
