"""Native Core-to-PDF output for print workflows.

This emitter consumes resolved Core geometry directly; it never converts SVG. Coordinates
remain in Scenet's top-left-origin units until the final PDF canvas transform. ReportLab
is an optional dependency, installed with scenet[print].
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scenet.core import CoreActor, CoreBalloon, CoreCaption, CoreMass, PanelCore
from scenet.ir import BalloonKind, Face
from scenet.pipeline import Book
from scenet.solve.text import FontMetrics
from scenet.emit.svg import _burst, _runs_of, _width, typeface_of


def _reportlab() -> tuple[Any, Any]:
    try:
        from reportlab.lib.colors import CMYKColor
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError("PDF output requires the optional dependency; install scenet[print]") from exc
    return canvas, CMYKColor


def _cmyk(hex_colour: str, CMYKColor: Any) -> Any:
    value = hex_colour.lstrip("#")
    if len(value) != 6:
        return CMYKColor(0, 0, 0, 1)
    r, g, b = (int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))
    if max(r, g, b) - min(r, g, b) < 1 / 255:
        return CMYKColor(0, 0, 0, 1 - (r + g + b) / 3)
    k = 1 - max(r, g, b)
    if k >= 0.999:
        return CMYKColor(0, 0, 0, 1)
    return CMYKColor((1-r-k)/(1-k), (1-g-k)/(1-k), (1-b-k)/(1-k), k)


def _poly(canvas: Any, points: tuple[tuple[float, float], ...], *, fill: bool, stroke: bool) -> None:
    if not points:
        return
    path = canvas.beginPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    path.close()
    canvas.drawPath(path, stroke=int(stroke), fill=int(fill))


def _draw_actor(canvas: Any, actor: CoreActor, ink: Any, paper: Any) -> None:
    canvas.setLineCap(1)
    canvas.setLineJoin(1)
    for capsule in actor.capsules:
        (x1, y1), (x2, y2) = capsule.start, capsule.end
        canvas.setStrokeColor(ink)
        canvas.setLineWidth(capsule.width)
        canvas.line(x1, y1, x2, y2)
        canvas.setStrokeColor(paper)
        canvas.setLineWidth(max(capsule.width - 6, 1))
        canvas.line(x1, y1, x2, y2)
    canvas.setFillColor(paper)
    canvas.setStrokeColor(ink)
    canvas.setLineWidth(3)
    for blob in actor.blobs:
        x, y = blob.centre
        canvas.circle(x, y, blob.radius, stroke=1, fill=1)
    for mark in (*actor.face_marks, *actor.emanata):
        canvas.setLineWidth(mark.width)
        if hasattr(mark, "centre"):
            x, y = mark.centre
            canvas.setFillColor(ink if mark.filled else paper)
            canvas.circle(x, y, mark.radius, stroke=int(not mark.filled), fill=1)
        else:
            _poly(canvas, mark.points, fill=False, stroke=True)


def _draw_mass(canvas: Any, mass: CoreMass, CMYKColor: Any) -> None:
    tone = _cmyk(mass.tone, CMYKColor)
    canvas.setFillColor(tone)
    canvas.setStrokeColor(tone)
    _poly(canvas, mass.polygon, fill=True, stroke=False)


def _draw_text_line(canvas: Any, text: str, x: float, baseline: float, size: float, face: Face, family: Any, ink: Any) -> None:
    metrics: FontMetrics = family.face(face)
    cursor = x
    scale = size / metrics.units_per_em
    from fontTools.svgLib.path import parse_path

    class PDFPen:
        def __init__(self, target: Any) -> None:
            self.target = target

        def moveTo(self, p: tuple[float, float]) -> None:
            self.target.moveTo(*p)

        def lineTo(self, p: tuple[float, float]) -> None:
            self.target.lineTo(*p)

        def curveTo(self, p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float]) -> None:
            self.target.curveTo(*p1, *p2, *p3)

        def qCurveTo(self, *points: tuple[float, float] | None) -> None:
            valid = [p for p in points if p is not None]
            if len(valid) >= 2:
                self.target.curveTo(valid[0][0], valid[0][1], valid[-1][0], valid[-1][1], valid[-1][0], valid[-1][1])

        def closePath(self) -> None:
            self.target.close()

        def endPath(self) -> None:
            pass

    canvas.setFillColor(ink)
    for path_data, advance in metrics.glyph_outlines(text):
        if path_data:
            path = canvas.beginPath()
            parse_path(path_data, PDFPen(path))
            canvas.saveState()
            canvas.translate(cursor, baseline)
            canvas.scale(scale, -scale)
            canvas.drawPath(path, stroke=0, fill=1)
            canvas.restoreState()
        cursor += advance * size


def _draw_lettering(canvas: Any, item: CoreBalloon | CoreCaption, family: Any, ink: Any, paper: Any, CMYKColor: Any) -> None:
    from scenet.solve.text import Styled

    box = item.box
    if isinstance(item, CoreCaption):
        canvas.setFillColor(_cmyk(item.fill, CMYKColor))
        canvas.setStrokeColor(ink)
        canvas.setLineWidth(2.5)
        canvas.rect(box.x, box.y, box.width, box.height, fill=1, stroke=1)
        text_ink = _cmyk(item.ink, CMYKColor)
        base = Face.ITALIC if item.italic else Face.REGULAR
        padding = (box.height - len(item.lines) * item.line_height) / 2
        for index, line in enumerate(item.lines):
            runs = _runs_of(item.lines, item.runs, index, base)
            cursor = box.x + padding
            for run in runs:
                baseline = box.y + padding + index * item.line_height + item.font_size * .74
                _draw_text_line(canvas, run.text, cursor, baseline, item.font_size, run.face, family, text_ink)
                cursor += family.measure(Styled.of(run.text, run.face), item.font_size)
        return

    tail = item.tail
    if item.kind is not BalloonKind.THOUGHT:
        dx, dy = tail.end[0] - tail.start[0], tail.end[1] - tail.start[1]
        length = (dx * dx + dy * dy) ** .5 or 1
        half = max(box.height * .18, item.font_size * .35) / 2
        normal = (-dy / length * half, dx / length * half)
        _poly(canvas, ((tail.start[0]+normal[0], tail.start[1]+normal[1]), tail.end, (tail.start[0]-normal[0], tail.start[1]-normal[1])), fill=True, stroke=True)
    canvas.setFillColor(paper)
    canvas.setStrokeColor(ink)
    canvas.setLineWidth(3)
    if item.kind is BalloonKind.SHOUT:
        _poly(canvas, tuple(_burst(item)), fill=True, stroke=True)
    elif item.kind is BalloonKind.THOUGHT:
        canvas.ellipse(box.x, box.y, box.x + box.width, box.y + box.height, fill=1, stroke=1)
    else:
        canvas.roundRect(box.x, box.y, box.width, box.height, min(box.width, box.height) * .42, fill=1, stroke=1)
    padding = (box.height - len(item.lines) * item.line_height) / 2
    for index, line in enumerate(item.lines):
        runs = _runs_of(item.lines, item.runs, index, Face.REGULAR)
        width = _width(runs, item.font_size, family)
        cursor = box.x + (box.width - width) / 2
        baseline = box.y + padding + index * item.line_height + item.font_size * .74
        for run in runs:
            _draw_text_line(canvas, run.text, cursor, baseline, item.font_size, run.face, family, ink)
            cursor += family.measure(Styled.of(run.text, run.face), item.font_size)


def _draw_panel(canvas: Any, core: PanelCore, CMYKColor: Any, fonts: Mapping[str, FontMetrics]) -> None:
    family = typeface_of(core, fonts=fonts)
    ink = _cmyk("#000000", CMYKColor)
    paper = _cmyk("#ffffff", CMYKColor)
    canvas.setFillColor(paper)
    canvas.rect(0, 0, core.width, core.height, fill=1, stroke=0)
    backdrop = core.backdrop
    if backdrop is not None:
        for mass in sorted(backdrop.masses, key=lambda value: (value.depth, value.id)):
            _draw_mass(canvas, mass, CMYKColor)
        # The Core stores turbulence parameters rather than pixels; this emitter leaves
        # atmospheric noise out instead of silently substituting a different texture.
    drawn: list[tuple[int, str, Any]] = [(actor.depth, actor.id, actor) for actor in core.actors]
    if backdrop is not None:
        drawn.extend((mass.depth, mass.id, mass) for mass in backdrop.masses)
    for depth, _, item in sorted(drawn, key=lambda value: (value[0], value[1])):
        if depth >= 0 and isinstance(item, CoreActor):
            _draw_actor(canvas, item, ink, paper)
    for item in sorted((*core.balloons, *core.captions), key=lambda value: value.order):
        _draw_lettering(canvas, item, family, ink, paper, CMYKColor)
    canvas.setStrokeColor(ink)
    canvas.setLineWidth(6)
    if core.outline:
        _poly(canvas, core.outline, fill=False, stroke=True)
    else:
        canvas.rect(0, 0, core.width, core.height, fill=0, stroke=1)


def render_book_pdf(book: Book, output: Path, *, bleed_mm: float = 3.0) -> None:
    """Write a multi-page CMYK PDF from Core with trim/bleed boxes and stable metadata.

    Each page preserves its aspect ratio and fits within 8.5 × 11 inches, with 3 mm
    bleed. This is not a claim of PDF/X conformance: that requires external preflight
    and an output-intent ICC profile.
    """
    canvas_module, CMYKColor = _reportlab()
    cores = {name: result.core for name, result in book.panels.items()}
    pages: list[tuple[float, float, list[tuple[PanelCore, float, float, float, float]]]] = []
    if book.pages:
        for page in book.pages:
            scale = min(612 / page.width, 792 / page.height)
            pages.append((page.width * scale, page.height * scale, [
                (cores[frame.panel], frame.x * scale, frame.y * scale, frame.width * scale, frame.height * scale)
                for frame in page.frames
            ]))
    else:
        for result in book.panels.values():
            core = result.core
            scale = min(612 / core.width, 792 / core.height)
            pages.append((core.width * scale, core.height * scale, [(core, 0, 0, core.width * scale, core.height * scale)]))
    if not pages:
        raise ValueError("the source contains no panels to emit")
    bleed = bleed_mm * 72 / 25.4
    pdf = canvas_module.Canvas(str(output), pagesize=(pages[0][0] + 2*bleed, pages[0][1] + 2*bleed), pageCompression=1, invariant=1)
    pdf.setTitle(output.stem)
    pdf.setAuthor("Scenet")
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    timestamp = datetime.fromtimestamp(epoch, timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
    pdf._doc.info.creationDate = timestamp
    pdf._doc.info.modDate = timestamp
    digest = hashlib.sha256("\n".join(core.to_json() for core in cores.values()).encode()).hexdigest()
    pdf._doc._ID = (digest[:32].encode(), digest[:32].encode())
    for trim_w, trim_h, panels in pages:
        pdf.setPageSize((trim_w + 2*bleed, trim_h + 2*bleed))
        pdf.saveState()
        pdf.translate(bleed, bleed + trim_h)
        if len(panels) == 1:
            core, _, _, _, _ = panels[0]
            pdf.scale(trim_w / core.width, -trim_h / core.height)
            _draw_panel(pdf, core, CMYKColor, book.fonts)
        else:
            # Page coordinates and frame dimensions share the page's scale.
            pdf.scale(1, -1)
            for core, x, y, width, height in panels:
                pdf.saveState()
                pdf.translate(x, y)
                pdf.scale(width / core.width, height / core.height)
                _draw_panel(pdf, core, CMYKColor, book.fonts)
                pdf.restoreState()
        pdf.restoreState()
        # ReportLab exposes page boxes as raw PDF page attributes.
        pdf._code.append(f"/TrimBox [ {bleed:.4f} {bleed:.4f} {bleed+trim_w:.4f} {bleed+trim_h:.4f} ]")
        pdf._code.append(f"/BleedBox [ 0 0 {trim_w+2*bleed:.4f} {trim_h+2*bleed:.4f} ]")
        pdf.showPage()
    pdf.save()
