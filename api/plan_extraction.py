from __future__ import annotations

from dataclasses import dataclass
import json
import math

import numpy as np


try:
    import cv2
except ImportError:  # pragma: no cover - handled at runtime by the API
    cv2 = None

try:
    import fitz
except ImportError:  # pragma: no cover - handled at runtime by the API
    fitz = None


@dataclass
class ExtractedPolygon:
    points: list[dict[str, int]]
    area_px: float
    bbox: dict[str, int]
    center: dict[str, float]
    confidence: float
    source: str = "unknown"


def _load_roi_polygon(project_polygon) -> list[dict[str, int]]:
    if not project_polygon:
        return []
    if isinstance(project_polygon, str):
        try:
            project_polygon = json.loads(project_polygon)
        except json.JSONDecodeError:
            return []
    if not isinstance(project_polygon, list):
        return []
    points = []
    for point in project_polygon:
        if not isinstance(point, dict):
            continue
        try:
            x = int(round(float(point.get("x"))))
            y = int(round(float(point.get("y"))))
        except (TypeError, ValueError):
            continue
        points.append({"x": x, "y": y})
    return points


def _require_cv2():
    if cv2 is None:
        raise RuntimeError(
            "OpenCV no está instalado. Agrega opencv-python-headless al entorno del backend."
        )


def _require_fitz():
    if fitz is None:
        raise RuntimeError(
            "PyMuPDF no está instalado. Agrega PyMuPDF al entorno del backend."
        )


def decode_image_bytes(image_bytes: bytes) -> np.ndarray:
    _require_cv2()
    raw = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("No se pudo decodificar la imagen recibida.")
    return image


def _fitz_point_to_xy(point) -> tuple[float, float]:
    if hasattr(point, "x") and hasattr(point, "y"):
        return float(point.x), float(point.y)
    if isinstance(point, (tuple, list)) and len(point) >= 2:
        return float(point[0]), float(point[1])
    raise TypeError("Punto PDF no soportado.")


def _pdf_to_canvas_point(point, scale_x: float, scale_y: float) -> tuple[int, int]:
    x, y = _fitz_point_to_xy(point)
    return int(round(x * scale_x)), int(round(y * scale_y))




def _clean_vector_line_mask(mask: np.ndarray) -> np.ndarray:
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    image_h, image_w = mask.shape[:2]
    image_area = float(image_h * image_w)
    cleaned = np.zeros_like(mask)

    for label in range(1, num_labels):
        x, y, w, h, area = stats[label]
        long_enough = max(w, h) >= max(24, int(round(max(image_w, image_h) * 0.035)))
        big_enough = area >= image_area * 0.000035
        if long_enough or big_enough:
            cleaned[labels == label] = 255

    return cleaned


def _render_pdf_vector_lines(
    pdf_bytes: bytes,
    *,
    image_width: int,
    image_height: int,
) -> np.ndarray | None:
    _require_fitz()
    if image_width <= 0 or image_height <= 0:
        return None

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    if document.page_count < 1:
        return None

    page = document.load_page(0)
    drawings = page.get_drawings()
    if not drawings:
        return None

    page_rect = page.rect
    scale_x = image_width / max(1.0, float(page_rect.width))
    scale_y = image_height / max(1.0, float(page_rect.height))
    canvas = np.ones((image_height, image_width, 3), dtype=np.uint8) * 255

    def draw_line(start, end, width_px: int):
        cv2.line(
            canvas,
            _pdf_to_canvas_point(start, scale_x, scale_y),
            _pdf_to_canvas_point(end, scale_x, scale_y),
            (0, 0, 0),
            max(1, width_px),
            lineType=cv2.LINE_AA,
        )

    def draw_polyline(points, closed: bool, width_px: int):
        if len(points) < 2:
            return
        pts = np.array(
            [_pdf_to_canvas_point(point, scale_x, scale_y) for point in points],
            dtype=np.int32,
        )
        cv2.polylines(
            canvas,
            [pts],
            closed,
            (0, 0, 0),
            max(1, width_px),
            lineType=cv2.LINE_AA,
        )

    for drawing in drawings:
        stroke_opacity = float(drawing.get("stroke_opacity", 1) or 1)
        if stroke_opacity <= 0:
            continue
        width_pt = float(drawing.get("width", 1) or 1)
        width_px = max(1, int(round(((width_pt * scale_x) + (width_pt * scale_y)) / 2)))
        for item in drawing.get("items", []):
            operator = item[0]
            try:
                if operator == "l":
                    draw_line(item[1], item[2], width_px)
                elif operator == "re":
                    rect = item[1]
                    points = [
                        (rect.x0, rect.y0),
                        (rect.x1, rect.y0),
                        (rect.x1, rect.y1),
                        (rect.x0, rect.y1),
                    ]
                    draw_polyline(points, True, width_px)
                elif operator == "qu":
                    quad = item[1]
                    points = [quad.ul, quad.ur, quad.lr, quad.ll]
                    draw_polyline(points, True, width_px)
                elif operator == "c":
                    p1 = _fitz_point_to_xy(item[1])
                    p2 = _fitz_point_to_xy(item[2])
                    p3 = _fitz_point_to_xy(item[3])
                    p4 = _fitz_point_to_xy(item[4])
                    bezier_points = []
                    for step in range(21):
                        t = step / 20
                        mt = 1 - t
                        x = (
                            mt**3 * p1[0]
                            + 3 * mt**2 * t * p2[0]
                            + 3 * mt * t**2 * p3[0]
                            + t**3 * p4[0]
                        )
                        y = (
                            mt**3 * p1[1]
                            + 3 * mt**2 * t * p2[1]
                            + 3 * mt * t**2 * p3[1]
                            + t**3 * p4[1]
                        )
                        bezier_points.append((x, y))
                    draw_polyline(bezier_points, False, width_px)
            except Exception:
                continue

    gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    _, line_mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    line_mask = _clean_vector_line_mask(line_mask)
    cleaned_canvas = np.ones_like(canvas) * 255
    cleaned_canvas[line_mask > 0] = (0, 0, 0)
    return cleaned_canvas


def _polygon_confidence(
    *,
    area: float,
    bbox_area: float,
    vertex_count: int,
    image_area: float,
) -> float:
    fill_ratio = area / max(1.0, bbox_area)
    area_ratio = area / max(1.0, image_area)
    vertex_penalty = min(abs(vertex_count - 4) * 0.06, 0.3)
    score = 0.55 + min(fill_ratio, 1.0) * 0.25 + min(area_ratio * 8.0, 0.2) - vertex_penalty
    return round(max(0.05, min(score, 0.99)), 3)


def _angle_between_points(prev_pt, current_pt, next_pt) -> float:
    v1 = (prev_pt[0] - current_pt[0], prev_pt[1] - current_pt[1])
    v2 = (next_pt[0] - current_pt[0], next_pt[1] - current_pt[1])
    mag1 = math.hypot(v1[0], v1[1])
    mag2 = math.hypot(v2[0], v2[1])
    if mag1 == 0 or mag2 == 0:
        return 0.0
    cos_angle = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))


def _fit_rectangle_from_contour(
    contour: np.ndarray,
    area: float,
) -> tuple[list[dict[str, int]] | None, float, float, float]:
    rect = cv2.minAreaRect(contour)
    (center_x, center_y), (width, height), _angle = rect
    if width < 12 or height < 12:
        return None, 0.0, 0.0, 0.0

    aspect_ratio = max(width, height) / max(1.0, min(width, height))
    if aspect_ratio > 8.0:
        return None, 0.0, width, height

    box = cv2.boxPoints(rect)
    points = [{"x": int(round(x)), "y": int(round(y))} for x, y in box]
    box_area = max(1.0, float(width * height))
    rectangularity = area / box_area
    if rectangularity < 0.42 or rectangularity > 1.18:
        return None, rectangularity, width, height

    tuples = [(point["x"], point["y"]) for point in points]
    angles = []
    for index, current_pt in enumerate(tuples):
        prev_pt = tuples[index - 1]
        next_pt = tuples[(index + 1) % len(tuples)]
        angles.append(_angle_between_points(prev_pt, current_pt, next_pt))
    if not all(55.0 <= angle <= 125.0 for angle in angles):
        return None, rectangularity, width, height
    return points, rectangularity, width, height


def _fit_polygon_from_contour(
    contour: np.ndarray,
    *,
    epsilon_ratio: float,
) -> list[dict[str, int]] | None:
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return None
    approx = cv2.approxPolyDP(contour, epsilon_ratio * perimeter, True)
    if len(approx) < 4 or len(approx) > 14:
        return None
    points = [
        {"x": int(point[0][0]), "y": int(point[0][1])}
        for point in approx
    ]
    return _order_points_clockwise(points)


def _build_roi_mask(image_shape, roi_points: list[dict[str, int]]) -> np.ndarray | None:
    if len(roi_points) < 3:
        return None
    mask = np.zeros(image_shape[:2], dtype=np.uint8)
    roi_array = np.array(
        [[point["x"], point["y"]] for point in roi_points],
        dtype=np.int32,
    )
    cv2.fillPoly(mask, [roi_array], 255)
    return mask


def _points_to_contour(points: list[dict[str, int]]) -> np.ndarray:
    return np.array(
        [[[int(point["x"]), int(point["y"])] for point in points]],
        dtype=np.int32,
    ).reshape((-1, 1, 2))


def _order_points_clockwise(points: list[dict[str, int]]) -> list[dict[str, int]]:
    center_x = sum(point["x"] for point in points) / len(points)
    center_y = sum(point["y"] for point in points) / len(points)
    return sorted(
        points,
        key=lambda point: math.atan2(point["y"] - center_y, point["x"] - center_x),
    )


def _polygon_contains_polygon(container: ExtractedPolygon, candidate: ExtractedPolygon) -> bool:
    container_contour = _points_to_contour(container.points)
    for point in candidate.points:
        inside = cv2.pointPolygonTest(
            container_contour,
            (float(point["x"]), float(point["y"])),
            False,
        )
        if inside < 0:
            return False
    return True


def _prune_nested_polygons(polygons: list[ExtractedPolygon]) -> tuple[list[ExtractedPolygon], int]:
    if len(polygons) < 2:
        return polygons, 0

    drop_indexes: set[int] = set()
    for outer_index, outer in enumerate(polygons):
        if outer_index in drop_indexes:
            continue

        contained_count = 0
        for inner_index, inner in enumerate(polygons):
            if outer_index == inner_index or inner_index in drop_indexes:
                continue
            if outer.area_px <= inner.area_px * 1.15:
                continue
            if not _polygon_contains_polygon(outer, inner):
                continue

            area_ratio = inner.area_px / max(1.0, outer.area_px)
            if area_ratio >= 0.08:
                contained_count += 1

        if contained_count >= 1:
            drop_indexes.add(outer_index)

    kept = [
        polygon
        for index, polygon in enumerate(polygons)
        if index not in drop_indexes
    ]
    return kept, len(drop_indexes)


def _sample_dark_score(
    line_image: np.ndarray,
    start: tuple[float, float],
    end: tuple[float, float],
    thickness: int = 2,
) -> float:
    canvas = np.zeros_like(line_image)
    cv2.line(
        canvas,
        (int(round(start[0])), int(round(start[1]))),
        (int(round(end[0])), int(round(end[1]))),
        255,
        thickness,
    )
    overlap = cv2.bitwise_and(line_image, canvas)
    return float(cv2.countNonZero(overlap))


def _line_intersection(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> tuple[float, float] | None:
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-6:
        return None
    px = (
        (x1 * y2 - y1 * x2) * (x3 - x4)
        - (x1 - x2) * (x3 * y4 - y3 * x4)
    ) / denominator
    py = (
        (x1 * y2 - y1 * x2) * (y3 - y4)
        - (y1 - y2) * (x3 * y4 - y3 * x4)
    ) / denominator
    return px, py


def _snap_rectangle_to_lines(
    line_image: np.ndarray,
    points: list[dict[str, int]],
    *,
    search_radius: int = 8,
) -> list[dict[str, int]]:
    ordered = _order_points_clockwise(points)
    if len(ordered) != 4:
        return ordered

    center_x = sum(point["x"] for point in ordered) / 4
    center_y = sum(point["y"] for point in ordered) / 4
    snapped_edges = []

    for index in range(4):
        start = ordered[index]
        end = ordered[(index + 1) % 4]
        dx = end["x"] - start["x"]
        dy = end["y"] - start["y"]
        length = math.hypot(dx, dy)
        if length < 1:
            return ordered

        normal_x = -dy / length
        normal_y = dx / length
        midpoint_x = (start["x"] + end["x"]) / 2
        midpoint_y = (start["y"] + end["y"]) / 2
        to_center_x = center_x - midpoint_x
        to_center_y = center_y - midpoint_y
        if normal_x * to_center_x + normal_y * to_center_y < 0:
            normal_x *= -1
            normal_y *= -1

        best_offset = 0
        best_score = -1.0
        for offset in range(-search_radius, search_radius + 1):
            shifted_start = (
                start["x"] + normal_x * offset,
                start["y"] + normal_y * offset,
            )
            shifted_end = (
                end["x"] + normal_x * offset,
                end["y"] + normal_y * offset,
            )
            score = _sample_dark_score(line_image, shifted_start, shifted_end)
            if score > best_score:
                best_score = score
                best_offset = offset

        snapped_edges.append(
            (
                (
                    start["x"] + normal_x * best_offset,
                    start["y"] + normal_y * best_offset,
                ),
                (
                    end["x"] + normal_x * best_offset,
                    end["y"] + normal_y * best_offset,
                ),
            )
        )

    snapped_points: list[dict[str, int]] = []
    for index in range(4):
        prev_edge = snapped_edges[index - 1]
        current_edge = snapped_edges[index]
        intersection = _line_intersection(
            prev_edge[0],
            prev_edge[1],
            current_edge[0],
            current_edge[1],
        )
        if intersection is None:
            return ordered
        snapped_points.append(
            {"x": int(round(intersection[0])), "y": int(round(intersection[1]))}
        )

    return _order_points_clockwise(snapped_points)


def _interior_line_density(binary_image: np.ndarray, points: list[dict[str, int]]) -> float:
    contour = _points_to_contour(points)
    mask = np.zeros(binary_image.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [contour], 255)

    # Erode the filled area to ignore the border stroke and focus on inner subdivisions.
    eroded = cv2.erode(mask, np.ones((7, 7), np.uint8), iterations=1)
    total_pixels = cv2.countNonZero(eroded)
    if total_pixels <= 0:
        return 0.0

    inner_lines = cv2.bitwise_and(binary_image, binary_image, mask=eroded)
    dark_pixels = cv2.countNonZero(inner_lines)
    return dark_pixels / total_pixels


def _polygon_overlap_ratio(a: ExtractedPolygon, b: ExtractedPolygon) -> float:
    contour_a = _points_to_contour(a.points).astype(np.float32)
    contour_b = _points_to_contour(b.points).astype(np.float32)
    overlap_area, _intersection = cv2.intersectConvexConvex(contour_a, contour_b)
    if overlap_area <= 0:
        return 0.0
    return float(overlap_area) / max(1.0, min(a.area_px, b.area_px))


def _bbox_iou(a: dict[str, int], b: dict[str, int]) -> float:
    ax1 = a["x"]
    ay1 = a["y"]
    ax2 = a["x"] + a["width"]
    ay2 = a["y"] + a["height"]
    bx1 = b["x"]
    by1 = b["y"]
    bx2 = b["x"] + b["width"]
    by2 = b["y"] + b["height"]

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0

    intersection = float((inter_x2 - inter_x1) * (inter_y2 - inter_y1))
    area_a = float(max(1, a["width"] * a["height"]))
    area_b = float(max(1, b["width"] * b["height"]))
    union = area_a + area_b - intersection
    return intersection / max(1.0, union)


def _bbox_gap(a: dict[str, int], b: dict[str, int]) -> tuple[float, float]:
    ax1 = a["x"]
    ay1 = a["y"]
    ax2 = a["x"] + a["width"]
    ay2 = a["y"] + a["height"]
    bx1 = b["x"]
    by1 = b["y"]
    bx2 = b["x"] + b["width"]
    by2 = b["y"] + b["height"]

    gap_x = max(0, max(ax1, bx1) - min(ax2, bx2))
    gap_y = max(0, max(ay1, by1) - min(ay2, by2))
    return float(gap_x), float(gap_y)


def _overlap_span_ratio(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    overlap = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    span = max(1.0, min(a_end - a_start, b_end - b_start))
    return overlap / span


def _shares_grid_adjacency(candidate: ExtractedPolygon, anchors: list[ExtractedPolygon]) -> bool:
    for anchor in anchors:
        gap_x, gap_y = _bbox_gap(candidate.bbox, anchor.bbox)
        cx1 = candidate.bbox["x"]
        cx2 = candidate.bbox["x"] + candidate.bbox["width"]
        cy1 = candidate.bbox["y"]
        cy2 = candidate.bbox["y"] + candidate.bbox["height"]
        ax1 = anchor.bbox["x"]
        ax2 = anchor.bbox["x"] + anchor.bbox["width"]
        ay1 = anchor.bbox["y"]
        ay2 = anchor.bbox["y"] + anchor.bbox["height"]

        vertical_ratio = _overlap_span_ratio(cy1, cy2, ay1, ay2)
        horizontal_ratio = _overlap_span_ratio(cx1, cx2, ax1, ax2)
        if gap_x <= 8 and vertical_ratio >= 0.35:
            return True
        if gap_y <= 8 and horizontal_ratio >= 0.35:
            return True
    return False


def _adjacency_count(candidate: ExtractedPolygon, polygons: list[ExtractedPolygon]) -> int:
    count = 0
    for other in polygons:
        if other is candidate:
            continue
        gap_x, gap_y = _bbox_gap(candidate.bbox, other.bbox)
        cx1 = candidate.bbox["x"]
        cx2 = candidate.bbox["x"] + candidate.bbox["width"]
        cy1 = candidate.bbox["y"]
        cy2 = candidate.bbox["y"] + candidate.bbox["height"]
        ox1 = other.bbox["x"]
        ox2 = other.bbox["x"] + other.bbox["width"]
        oy1 = other.bbox["y"]
        oy2 = other.bbox["y"] + other.bbox["height"]
        vertical_ratio = _overlap_span_ratio(cy1, cy2, oy1, oy2)
        horizontal_ratio = _overlap_span_ratio(cx1, cx2, ox1, ox2)
        if gap_x <= 10 and vertical_ratio >= 0.3:
            count += 1
            continue
        if gap_y <= 10 and horizontal_ratio >= 0.3:
            count += 1
    return count


def _nearest_neighbor_gap(candidate: ExtractedPolygon, polygons: list[ExtractedPolygon]) -> float:
    nearest = float("inf")
    for other in polygons:
        if other is candidate:
            continue
        gap_x, gap_y = _bbox_gap(candidate.bbox, other.bbox)
        nearest = min(nearest, max(gap_x, gap_y))
    return nearest if nearest != float("inf") else 9999.0


def _median_area(polygons: list[ExtractedPolygon]) -> float:
    if not polygons:
        return 0.0
    areas = sorted(polygon.area_px for polygon in polygons)
    return areas[len(areas) // 2]


def _robust_area_bounds(polygons: list[ExtractedPolygon]) -> tuple[float, float]:
    if not polygons:
        return 0.0, float("inf")
    areas = sorted(polygon.area_px for polygon in polygons)
    median = areas[len(areas) // 2]
    min_bound = median * 0.35
    max_bound = median * 2.8
    return min_bound, max_bound


def _filter_additional_candidates(
    anchors: list[ExtractedPolygon],
    candidates: list[ExtractedPolygon],
) -> tuple[list[ExtractedPolygon], int]:
    if not candidates:
        return [], 0

    min_area, max_area = _robust_area_bounds(anchors or candidates)
    accepted: list[ExtractedPolygon] = []
    rejected = 0
    anchor_pool = list(anchors)

    for candidate in candidates:
        if candidate.area_px < min_area or candidate.area_px > max_area:
            rejected += 1
            continue
        if anchors and not _shares_grid_adjacency(candidate, anchor_pool):
            rejected += 1
            continue
        accepted.append(candidate)
        anchor_pool.append(candidate)

    return accepted, rejected


def _prune_small_outliers(polygons: list[ExtractedPolygon]) -> tuple[list[ExtractedPolygon], int]:
    if len(polygons) < 8:
        return polygons, 0
    areas = sorted(polygon.area_px for polygon in polygons)
    median = areas[len(areas) // 2]
    min_allowed = median * 0.22
    kept = [polygon for polygon in polygons if polygon.area_px >= min_allowed]
    return kept, len(polygons) - len(kept)


def _prune_isolated_small_polygons(polygons: list[ExtractedPolygon]) -> tuple[list[ExtractedPolygon], int]:
    if len(polygons) < 8:
        return polygons, 0
    median = _median_area(polygons)
    min_small = median * 0.55
    kept: list[ExtractedPolygon] = []
    removed = 0
    for polygon in polygons:
        neighbors = _adjacency_count(polygon, polygons)
        nearest_gap = _nearest_neighbor_gap(polygon, polygons)
        if polygon.area_px < min_small and neighbors <= 1:
            removed += 1
            continue
        if neighbors == 0 and nearest_gap > 18:
            removed += 1
            continue
        kept.append(polygon)
    return kept, removed


def _shared_edge_length_ratio(a: ExtractedPolygon, b: ExtractedPolygon) -> tuple[float, str | None]:
    ax1 = a.bbox["x"]
    ax2 = a.bbox["x"] + a.bbox["width"]
    ay1 = a.bbox["y"]
    ay2 = a.bbox["y"] + a.bbox["height"]
    bx1 = b.bbox["x"]
    bx2 = b.bbox["x"] + b.bbox["width"]
    by1 = b.bbox["y"]
    by2 = b.bbox["y"] + b.bbox["height"]
    gap_x, gap_y = _bbox_gap(a.bbox, b.bbox)
    if gap_x <= 6:
        overlap = max(0.0, min(ay2, by2) - max(ay1, by1))
        span = max(1.0, min(ay2 - ay1, by2 - by1))
        return overlap / span, "vertical"
    if gap_y <= 6:
        overlap = max(0.0, min(ax2, bx2) - max(ax1, bx1))
        span = max(1.0, min(ax2 - ax1, bx2 - bx1))
        return overlap / span, "horizontal"
    return 0.0, None


def _merge_polygon_pair(a: ExtractedPolygon, b: ExtractedPolygon) -> ExtractedPolygon | None:
    merged_points = np.vstack(
        [_points_to_contour(a.points), _points_to_contour(b.points)]
    )
    hull = cv2.convexHull(merged_points)
    area = float(cv2.contourArea(hull))
    if area <= 0:
        return None
    perimeter = cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, 0.01 * perimeter, True)
    if len(approx) < 4 or len(approx) > 10:
        return None
    points = _order_points_clockwise(
        [{"x": int(point[0][0]), "y": int(point[0][1])} for point in approx]
    )
    contour = _points_to_contour(points)
    x, y, w, h = cv2.boundingRect(contour)
    center_x = sum(point["x"] for point in points) / len(points)
    center_y = sum(point["y"] for point in points) / len(points)
    return ExtractedPolygon(
        points=points,
        area_px=round(area, 2),
        bbox={"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
        center={"x": round(center_x, 2), "y": round(center_y, 2)},
        confidence=max(a.confidence, b.confidence),
        source="merged_pair",
    )


def _merge_split_pairs(polygons: list[ExtractedPolygon]) -> tuple[list[ExtractedPolygon], int]:
    if len(polygons) < 2:
        return polygons, 0
    median = _median_area(polygons)
    consumed: set[int] = set()
    merged: list[ExtractedPolygon] = []
    merged_count = 0

    for index, polygon in enumerate(polygons):
        if index in consumed:
            continue
        best_match_index = None
        best_score = -1.0
        for other_index in range(index + 1, len(polygons)):
            if other_index in consumed:
                continue
            other = polygons[other_index]
            share_ratio, orientation = _shared_edge_length_ratio(polygon, other)
            if share_ratio < 0.45:
                continue
            combined_area = polygon.area_px + other.area_px
            if not (median * 0.58 <= combined_area <= median * 1.7):
                continue
            if polygon.area_px > median * 1.05 or other.area_px > median * 1.05:
                continue
            combined = _merge_polygon_pair(polygon, other)
            if combined is None:
                continue
            union_efficiency = combined_area / max(1.0, combined.area_px)
            if union_efficiency < 0.72:
                continue
            bbox_aspect = max(
                combined.bbox["width"],
                combined.bbox["height"],
            ) / max(1.0, min(combined.bbox["width"], combined.bbox["height"]))
            if bbox_aspect > 9.0:
                continue
            score = share_ratio + union_efficiency
            if orientation == "vertical" and combined.bbox["width"] < combined.bbox["height"]:
                score += 0.08
            if orientation == "horizontal" and combined.bbox["height"] < combined.bbox["width"]:
                score += 0.08
            polygon_neighbors = _adjacency_count(polygon, polygons)
            other_neighbors = _adjacency_count(other, polygons)
            if polygon_neighbors <= 2 and other_neighbors <= 2:
                score += 0.08
            if score > best_score:
                best_match_index = other_index
                best_score = score

        if best_match_index is None:
            merged.append(polygon)
            continue

        combined = _merge_polygon_pair(polygon, polygons[best_match_index])
        if combined is None:
            merged.append(polygon)
            continue
        consumed.add(best_match_index)
        merged.append(combined)
        merged_count += 1

    return merged, merged_count


def _prune_low_connectivity_polygons(polygons: list[ExtractedPolygon]) -> tuple[list[ExtractedPolygon], int]:
    if len(polygons) < 12:
        return polygons, 0
    median = _median_area(polygons)
    kept: list[ExtractedPolygon] = []
    removed = 0
    for polygon in polygons:
        neighbors = _adjacency_count(polygon, polygons)
        nearest_gap = _nearest_neighbor_gap(polygon, polygons)
        # En un lote real de manzana normalmente hay al menos 1-2 vecinos muy cercanos.
        if neighbors == 0 and nearest_gap > 12:
            removed += 1
            continue
        if neighbors <= 1 and polygon.area_px < median * 1.05 and nearest_gap > 6:
            removed += 1
            continue
        kept.append(polygon)
    return kept, removed


def _merge_polygon_sets(
    primary: list[ExtractedPolygon],
    secondary: list[ExtractedPolygon],
) -> tuple[list[ExtractedPolygon], int]:
    merged = list(primary)
    deduped = 0
    for candidate in secondary:
        duplicate = False
        for existing in merged:
            center_dx = abs(existing.center["x"] - candidate.center["x"])
            center_dy = abs(existing.center["y"] - candidate.center["y"])
            if center_dx <= 10 and center_dy <= 10:
                if _bbox_iou(existing.bbox, candidate.bbox) >= 0.45:
                    duplicate = True
                    break
            if _polygon_overlap_ratio(existing, candidate) >= 0.65:
                duplicate = True
                break
        if duplicate:
            deduped += 1
            continue
        merged.append(candidate)
    return merged, deduped


def _suppress_overlapping_polygons(
    polygons: list[ExtractedPolygon],
    *,
    overlap_tolerance_ratio: float = 0.12,
) -> tuple[list[ExtractedPolygon], int]:
    if len(polygons) < 2:
        return polygons, 0

    ordered = sorted(
        polygons,
        key=lambda polygon: (polygon.confidence, polygon.area_px),
        reverse=True,
    )
    kept: list[ExtractedPolygon] = []
    removed = 0
    for candidate in ordered:
        has_conflict = False
        for accepted in kept:
            if _polygon_overlap_ratio(candidate, accepted) > overlap_tolerance_ratio:
                has_conflict = True
                removed += 1
                break
        if not has_conflict:
            kept.append(candidate)
    return kept, removed


def _component_to_polygon(
    component_mask: np.ndarray,
    *,
    min_area_px: float,
    max_area_px: float,
    image_area: float,
    source: str,
) -> ExtractedPolygon | None:
    contours, _ = cv2.findContours(
        component_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    if area < min_area_px or area > max_area_px:
        return None

    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return None
    approx = cv2.approxPolyDP(contour, 0.01 * perimeter, True)
    if len(approx) < 4 or len(approx) > 12:
        return None

    contour_points = [
        {"x": int(point[0][0]), "y": int(point[0][1])}
        for point in approx
    ]
    rect_points, _rectangularity, rect_width, rect_height = _fit_rectangle_from_contour(
        contour,
        area,
    )
    if rect_points:
        points = _order_points_clockwise(rect_points)
    else:
        points = _order_points_clockwise(contour_points)

    contour_array = _points_to_contour(points)
    x, y, w, h = cv2.boundingRect(contour_array)
    center_x = sum(point["x"] for point in points) / len(points)
    center_y = sum(point["y"] for point in points) / len(points)

    return ExtractedPolygon(
        points=points,
        area_px=round(area, 2),
        bbox={"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
        center={"x": round(center_x, 2), "y": round(center_y, 2)},
        confidence=_polygon_confidence(
            area=area,
            bbox_area=max(1.0, rect_width * rect_height) if rect_points else max(1.0, w * h),
            vertex_count=len(points),
            image_area=image_area,
        ),
        source=source,
    )


def extract_lot_polygons_from_vector_cells(
    pdf_bytes: bytes,
    *,
    image_width: int,
    image_height: int,
    project_polygon: list[dict[str, int]] | str | None = None,
) -> dict[str, object] | None:
    vector_canvas = _render_pdf_vector_lines(
        pdf_bytes,
        image_width=image_width,
        image_height=image_height,
    )
    if vector_canvas is None:
        return None

    gray = cv2.cvtColor(vector_canvas, cv2.COLOR_BGR2GRAY)
    _, line_mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    line_mask = cv2.dilate(line_mask, np.ones((3, 3), np.uint8), iterations=1)

    roi_points = _load_roi_polygon(project_polygon)
    roi_mask = _build_roi_mask(vector_canvas.shape, roi_points)
    if roi_mask is not None:
        line_mask = cv2.bitwise_and(line_mask, line_mask, mask=roi_mask)

    free_space = cv2.bitwise_not(line_mask)
    if roi_mask is not None:
        free_space = cv2.bitwise_and(free_space, free_space, mask=roi_mask)

    num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(free_space, 8)
    image_area = float(image_width * image_height)
    min_area_px = image_area * 0.00005
    max_area_px = image_area * 0.12

    polygons: list[ExtractedPolygon] = []
    skipped_border_touch = 0
    skipped_area = 0

    for label in range(1, num_labels):
        x, y, w, h, area_px = stats[label]
        if area_px < min_area_px or area_px > max_area_px:
            skipped_area += 1
            continue
        if x <= 1 or y <= 1 or x + w >= image_width - 1 or y + h >= image_height - 1:
            skipped_border_touch += 1
            continue

        component_mask = np.zeros_like(labels, dtype=np.uint8)
        component_mask[labels == label] = 255

        polygon = _component_to_polygon(
            component_mask,
            min_area_px=min_area_px,
            max_area_px=max_area_px,
            image_area=image_area,
            source="pdf_vector_cells",
        )
        if not polygon:
            continue
        if _is_duplicate_polygon(
            polygons,
            center_x=polygon.center["x"],
            center_y=polygon.center["y"],
            area=polygon.area_px,
        ):
            continue
        polygons.append(polygon)

    polygons, skipped_containers = _prune_nested_polygons(polygons)
    polygons, skipped_overlaps = _suppress_overlapping_polygons(
        polygons,
        overlap_tolerance_ratio=0.18,
    )
    polygons.sort(key=lambda item: (item.center["y"], item.center["x"]))

    return {
        "image_width": image_width,
        "image_height": image_height,
        "polygons": [
            {
                "points": item.points,
                "area_px": item.area_px,
                "bbox": item.bbox,
                "center": item.center,
                "confidence": item.confidence,
                "source": item.source,
            }
            for item in polygons
        ],
        "debug": {
            "source": "pdf_vector_cells",
            "roi_applied": bool(roi_mask is not None),
            "roi_points": len(roi_points),
            "components_found": int(num_labels - 1),
            "polygons_found": len(polygons),
            "skipped_border_touch": skipped_border_touch,
            "skipped_area": skipped_area,
            "skipped_container_polygons": skipped_containers,
            "skipped_overlapping_polygons": skipped_overlaps,
        },
    }


def _is_duplicate_polygon(
    polygons: list[ExtractedPolygon],
    *,
    center_x: float,
    center_y: float,
    area: float,
) -> bool:
    for existing in polygons:
        dx = abs(existing.center["x"] - center_x)
        dy = abs(existing.center["y"] - center_y)
        area_ratio = area / max(1.0, existing.area_px)
        if dx <= 10 and dy <= 10 and 0.75 <= area_ratio <= 1.25:
            return True
    return False


def _extract_lot_polygons_from_ndarray(
    image: np.ndarray,
    *,
    min_area_ratio: float = 0.00015,
    max_area_ratio: float = 0.18,
    epsilon_ratio: float = 0.015,
    project_polygon: list[dict[str, int]] | str | None = None,
    source: str = "overlay_raster",
    fill_ratio_threshold: float = 0.32,
    dense_interior_threshold: float = 0.12,
    allow_non_rectangular: bool = False,
) -> dict[str, object]:
    image_h, image_w = image.shape[:2]
    image_area = float(image_h * image_w)
    roi_points = _load_roi_polygon(project_polygon)
    roi_mask = _build_roi_mask(image.shape, roi_points)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    binary = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        7,
    )

    kernel = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)
    line_image = cv2.dilate(closed, kernel, iterations=1)
    if roi_mask is not None:
        opened = cv2.bitwise_and(opened, opened, mask=roi_mask)
        line_image = cv2.bitwise_and(line_image, line_image, mask=roi_mask)

    contours, _hierarchy = cv2.findContours(
        opened,
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    min_area = image_area * max(0.0, min_area_ratio)
    max_area = image_area * max(0.0, max_area_ratio)

    polygons: list[ExtractedPolygon] = []
    skipped_outside_roi = 0
    skipped_non_rectangular = 0
    skipped_dense_interior = 0
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area or area > max_area:
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue

        points, rectangularity, rect_width, rect_height = _fit_rectangle_from_contour(
            contour,
            area,
        )
        used_rectangular_fit = bool(points)
        if points:
            points = _snap_rectangle_to_lines(line_image, points)
        elif allow_non_rectangular:
            points = _fit_polygon_from_contour(contour, epsilon_ratio=epsilon_ratio)
            if not points:
                skipped_non_rectangular += 1
                continue
        else:
            skipped_non_rectangular += 1
            continue

        contour_array = _points_to_contour(points)
        x, y, w, h = cv2.boundingRect(contour_array)
        snapped_area = float(cv2.contourArea(contour_array))
        if snapped_area <= 0:
            continue

        if roi_mask is not None:
            if not all(
                0 <= point["x"] < image_w
                and 0 <= point["y"] < image_h
                and roi_mask[point["y"], point["x"]] > 0
                for point in points
            ):
                skipped_outside_roi += 1
                continue

        bbox_area = float(w * h)
        fill_ratio = snapped_area / max(1.0, bbox_area)
        min_fill_ratio = fill_ratio_threshold if used_rectangular_fit else fill_ratio_threshold * 0.65
        if fill_ratio < min_fill_ratio:
            continue
        if bbox_area > image_area * 0.3:
            continue

        internal_density = _interior_line_density(opened, points)
        if internal_density > dense_interior_threshold:
            skipped_dense_interior += 1
            continue

        center_x = sum(point["x"] for point in points) / len(points)
        center_y = sum(point["y"] for point in points) / len(points)
        if _is_duplicate_polygon(
            polygons,
            center_x=center_x,
            center_y=center_y,
            area=area,
        ):
            continue

        polygons.append(
            ExtractedPolygon(
                points=points,
                area_px=round(snapped_area, 2),
                bbox={"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                center={"x": round(center_x, 2), "y": round(center_y, 2)},
                confidence=_polygon_confidence(
                    area=snapped_area,
                    bbox_area=max(1.0, rect_width * rect_height),
                    vertex_count=len(points),
                    image_area=image_area,
                ),
                source=source,
            )
        )

    polygons.sort(key=lambda item: (item.center["y"], item.center["x"]))
    polygons, skipped_containers = _prune_nested_polygons(polygons)
    polygons, skipped_overlaps = _suppress_overlapping_polygons(polygons)
    polygons.sort(key=lambda item: (item.center["y"], item.center["x"]))

    return {
        "image_width": image_w,
        "image_height": image_h,
        "polygons": [
            {
                "points": item.points,
                "area_px": item.area_px,
                "bbox": item.bbox,
                "center": item.center,
                "confidence": item.confidence,
                "source": item.source,
            }
            for item in polygons
        ],
        "debug": {
            "contours_found": len(contours),
            "polygons_found": len(polygons),
            "roi_applied": bool(roi_mask is not None),
            "roi_points": len(roi_points),
            "skipped_outside_roi": skipped_outside_roi,
            "skipped_non_rectangular": skipped_non_rectangular,
            "skipped_dense_interior": skipped_dense_interior,
            "skipped_container_polygons": skipped_containers,
            "skipped_overlapping_polygons": skipped_overlaps,
            "source": source,
        },
    }


def extract_lot_polygons_from_image(
    image_bytes: bytes,
    *,
    min_area_ratio: float = 0.00015,
    max_area_ratio: float = 0.18,
    epsilon_ratio: float = 0.015,
    project_polygon: list[dict[str, int]] | str | None = None,
) -> dict[str, object]:
    image = decode_image_bytes(image_bytes)
    return _extract_lot_polygons_from_ndarray(
        image,
        min_area_ratio=min_area_ratio,
        max_area_ratio=max_area_ratio,
        epsilon_ratio=epsilon_ratio,
        project_polygon=project_polygon,
        source="overlay_raster",
    )


def extract_lot_polygons_from_pdf(
    pdf_bytes: bytes,
    *,
    image_width: int,
    image_height: int,
    project_polygon: list[dict[str, int]] | str | None = None,
    min_area_ratio: float = 0.00015,
    max_area_ratio: float = 0.18,
    epsilon_ratio: float = 0.015,
) -> dict[str, object] | None:
    vector_canvas = _render_pdf_vector_lines(
        pdf_bytes,
        image_width=image_width,
        image_height=image_height,
    )
    if vector_canvas is None:
        return None

    result = _extract_lot_polygons_from_ndarray(
        vector_canvas,
        min_area_ratio=min_area_ratio,
        max_area_ratio=max_area_ratio,
        epsilon_ratio=epsilon_ratio,
        project_polygon=project_polygon,
        source="pdf_vector",
        fill_ratio_threshold=0.24,
        dense_interior_threshold=0.18,
        allow_non_rectangular=True,
    )
    return result


def extract_lot_polygons_from_pdf_relaxed(
    pdf_bytes: bytes,
    *,
    image_width: int,
    image_height: int,
    project_polygon: list[dict[str, int]] | str | None = None,
) -> dict[str, object] | None:
    vector_canvas = _render_pdf_vector_lines(
        pdf_bytes,
        image_width=image_width,
        image_height=image_height,
    )
    if vector_canvas is None:
        return None

    result = _extract_lot_polygons_from_ndarray(
        vector_canvas,
        min_area_ratio=0.00008,
        max_area_ratio=0.22,
        epsilon_ratio=0.02,
        project_polygon=project_polygon,
        source="pdf_vector_relaxed",
        fill_ratio_threshold=0.16,
        dense_interior_threshold=0.32,
        allow_non_rectangular=True,
    )
    return result


def extract_lot_polygons_combined(
    *,
    overlay_image_bytes: bytes,
    overlay_pdf_bytes: bytes | None = None,
    image_width: int = 0,
    image_height: int = 0,
    project_polygon: list[dict[str, int]] | str | None = None,
) -> dict[str, object]:
    raster_result = extract_lot_polygons_from_image(
        overlay_image_bytes,
        project_polygon=project_polygon,
    )

    vector_result = None
    vector_relaxed_result = None
    vector_cells_result = None
    if overlay_pdf_bytes and image_width > 0 and image_height > 0:
        try:
            vector_result = extract_lot_polygons_from_pdf(
                overlay_pdf_bytes,
                image_width=image_width,
                image_height=image_height,
                project_polygon=project_polygon,
            )
        except Exception:
            vector_result = None
        try:
            vector_relaxed_result = extract_lot_polygons_from_pdf_relaxed(
                overlay_pdf_bytes,
                image_width=image_width,
                image_height=image_height,
                project_polygon=project_polygon,
            )
        except Exception:
            vector_relaxed_result = None
        try:
            vector_cells_result = extract_lot_polygons_from_vector_cells(
                overlay_pdf_bytes,
                image_width=image_width,
                image_height=image_height,
                project_polygon=project_polygon,
            )
        except Exception:
            vector_cells_result = None

    if not vector_result and not vector_relaxed_result and not vector_cells_result:
        raster_result["debug"]["mode"] = "raster_only"
        return raster_result

    def to_models(items):
        models: list[ExtractedPolygon] = []
        for item in items:
            models.append(
                ExtractedPolygon(
                    points=item["points"],
                    area_px=float(item["area_px"]),
                    bbox=item["bbox"],
                    center=item["center"],
                    confidence=float(item["confidence"]),
                    source=item.get("source", "unknown"),
                )
            )
        return models

    vector_models = to_models(vector_result["polygons"]) if vector_result else []
    vector_relaxed_models = (
        to_models(vector_relaxed_result["polygons"]) if vector_relaxed_result else []
    )
    vector_cells_models = (
        to_models(vector_cells_result["polygons"]) if vector_cells_result else []
    )
    raster_models = to_models(raster_result["polygons"])
    merged_models = list(vector_models)
    filtered_cells, rejected_cells = _filter_additional_candidates(
        vector_models,
        vector_cells_models,
    )
    merged_models, deduped_from_cells = _merge_polygon_sets(
        merged_models,
        filtered_cells,
    )
    filtered_relaxed, rejected_relaxed = _filter_additional_candidates(
        merged_models,
        vector_relaxed_models,
    )
    merged_models, deduped_from_relaxed = _merge_polygon_sets(
        merged_models,
        filtered_relaxed,
    )
    filtered_raster, rejected_raster = _filter_additional_candidates(
        merged_models,
        raster_models,
    )
    merged_models, deduped_from_raster = _merge_polygon_sets(merged_models, filtered_raster)
    merged_models, skipped_containers = _prune_nested_polygons(merged_models)
    merged_models, skipped_overlaps = _suppress_overlapping_polygons(merged_models)
    merged_models, merged_split_pairs = _merge_split_pairs(merged_models)
    merged_models, skipped_low_connectivity = _prune_low_connectivity_polygons(merged_models)
    merged_models, skipped_small_outliers = _prune_small_outliers(merged_models)
    merged_models, skipped_isolated_small = _prune_isolated_small_polygons(merged_models)
    merged_models.sort(key=lambda item: (item.center["y"], item.center["x"]))

    return {
        "image_width": raster_result["image_width"],
        "image_height": raster_result["image_height"],
        "polygons": [
            {
                "points": item.points,
                "area_px": item.area_px,
                "bbox": item.bbox,
                "center": item.center,
                "confidence": item.confidence,
                "source": item.source,
            }
            for item in merged_models
        ],
        "debug": {
            "mode": "combined",
            "vector_polygons": len(vector_models),
            "vector_cells_polygons": len(vector_cells_models),
            "vector_relaxed_polygons": len(vector_relaxed_models),
            "raster_polygons": len(raster_models),
            "merged_polygons": len(merged_models),
            "rejected_cells": rejected_cells,
            "deduped_from_cells": deduped_from_cells,
            "rejected_relaxed": rejected_relaxed,
            "deduped_from_relaxed": deduped_from_relaxed,
            "rejected_raster": rejected_raster,
            "deduped_from_raster": deduped_from_raster,
            "skipped_container_polygons": skipped_containers,
            "skipped_overlapping_polygons": skipped_overlaps,
            "merged_split_pairs": merged_split_pairs,
            "skipped_low_connectivity": skipped_low_connectivity,
            "skipped_small_outliers": skipped_small_outliers,
            "skipped_isolated_small": skipped_isolated_small,
            "vector_debug": vector_result.get("debug", {}) if vector_result else {},
            "vector_cells_debug": (
                vector_cells_result.get("debug", {}) if vector_cells_result else {}
            ),
            "vector_relaxed_debug": (
                vector_relaxed_result.get("debug", {}) if vector_relaxed_result else {}
            ),
            "raster_debug": raster_result.get("debug", {}),
        },
    }
