"""Bảng mapping property Wikidata → quan hệ KG (Phase 7 — D1 phần 1).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 7, `docs/04` §6.

Nguồn sự thật cho mapping là `configs/wikidata_relations.yaml` — **không**
hard-code trong code (nguyên tắc "Không hard-code" của
`.cursor/rules/python-standards.mdc`).

Hướng (direction)
-----------------
``forward``
    Subject → object giữ nguyên. Ví dụ ``P22`` (father) → ``cha_cua``:
    "Lê Lợi → Lê Khánh Dư" (con → cha, đúng `docs/04` §3.1).
``inverse``
    Đảo subject ↔ object. Ví dụ ``P40`` (child) → ``cha_cua``: Wikidata nói
    "cha → con", nhưng KG cần "con → cha" nên phải đảo.
``symmetric``
    Quan hệ đối xứng — orientation được chuẩn hoá bằng
    `src.common.schemas.normalize_orientation` khi nạp KG.
``year``
    Object là **giá trị năm** (không phải entity). Grounding phải tìm chuỗi
    năm tương ứng trong câu bằng chứng.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from src.common.config import REPO_ROOT
from src.common.logger import get_logger
from src.common.schemas import RELATION_TYPES, SYMMETRIC_RELATIONS

logger = get_logger(__name__)

#: Hướng xử lý một property Wikidata.
Direction = Literal["forward", "inverse", "symmetric", "year"]

#: Đường dẫn mặc định tới file mapping.
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "wikidata_relations.yaml"


@dataclass(frozen=True, slots=True)
class PropertySpec:
    """Đặc tả mapping của một property Wikidata.

    Attributes:
        relation: Tên quan hệ trong 18 quan hệ đóng.
        direction: Hướng xử lý subject/object.
        object_type: Loại node KG của object khi grounding bằng tên.
    """

    relation: str
    direction: Direction
    object_type: str = "person"

    @property
    def is_year(self) -> bool:
        """Object có phải giá trị năm không.

        Returns:
            ``True`` nếu direction là ``"year"``.
        """
        return self.direction == "year"

    @property
    def is_symmetric(self) -> bool:
        """Quan hệ có đối xứng không.

        Returns:
            ``True`` nếu quan hệ nằm trong `SYMMETRIC_RELATIONS`.
        """
        return self.relation in SYMMETRIC_RELATIONS


class RelationMap:
    """Bảng tra property Wikidata → quan hệ KG.

    Attributes:
        properties: Map ``P<id>`` → `PropertySpec` cho bộ property lõi.
        extended_properties: Map ``P<id>`` → `PropertySpec` cho bộ mở rộng.
    """

    def __init__(
        self,
        properties: dict[str, PropertySpec],
        extended_properties: dict[str, PropertySpec] | None = None,
    ) -> None:
        """Khởi tạo bảng mapping.

        Args:
            properties: Bảng property lõi.
            extended_properties: Bảng property mở rộng (tuỳ chọn).
        """
        self.properties = properties
        self.extended_properties = extended_properties or {}

    def __len__(self) -> int:
        """Số property trong bảng lõi.

        Returns:
            Số property.
        """
        return len(self.properties)

    def get(self, prop: str, *, extended: bool = False) -> PropertySpec | None:
        """Tra đặc tả của một property.

        Args:
            prop: Tên property, ví dụ ``"P22"``.
            extended: Cho phép tra trong bảng mở rộng.

        Returns:
            `PropertySpec` nếu tìm thấy, ngược lại ``None``.
        """
        spec = self.properties.get(prop)
        if spec is None and extended:
            spec = self.extended_properties.get(prop)
        return spec

    def active_properties(self, *, extended: bool = False) -> list[str]:
        """Danh sách property sẽ được truy vấn.

        Args:
            extended: Có gộp bảng mở rộng không.

        Returns:
            Danh sách tên property, sắp xếp ổn định.
        """
        props = set(self.properties)
        if extended:
            props |= set(self.extended_properties)
        return sorted(props)

    def relation_for(self, prop: str, *, extended: bool = False) -> str | None:
        """Quan hệ ứng với một property.

        Args:
            prop: Tên property.
            extended: Cho phép tra trong bảng mở rộng.

        Returns:
            Tên quan hệ hoặc ``None``.
        """
        spec = self.get(prop, extended=extended)
        return spec.relation if spec else None

    def direction_for(self, prop: str, *, extended: bool = False) -> Direction | None:
        """Hướng xử lý của một property.

        Args:
            prop: Tên property.
            extended: Cho phép tra trong bảng mở rộng.

        Returns:
            Hướng hoặc ``None``.
        """
        spec = self.get(prop, extended=extended)
        return spec.direction if spec else None

    def relation_set(self, *, extended: bool = False) -> set[str]:
        """Tập quan hệ được sinh ra bởi bảng mapping.

        Args:
            extended: Có gộp bảng mở rộng không.

        Returns:
            Tập tên quan hệ.
        """
        props = self.active_properties(extended=extended)
        return {self.properties[p].relation for p in props if p in self.properties} | {
            self.extended_properties[p].relation
            for p in props
            if p in self.extended_properties
        }


def _parse_specs(raw: Any, *, section: str) -> dict[str, PropertySpec]:
    """Chuyển khối YAML thô thành bảng `PropertySpec`.

    Args:
        raw: Nội dung khối YAML (dict).
        section: Tên khối, dùng cho thông báo lỗi.

    Returns:
        Map ``P<id>`` → `PropertySpec`.

    Raises:
        ValueError: Nếu quan hệ không nằm trong 18 quan hệ đóng, hoặc hướng
            không hợp lệ.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"Khối '{section}' phải là dict, nhận {type(raw).__name__}")

    specs: dict[str, PropertySpec] = {}
    for prop, body in raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"'{section}.{prop}' phải là dict")
        relation = str(body.get("relation") or "")
        if relation not in RELATION_TYPES:
            raise ValueError(
                f"'{section}.{prop}' ánh xạ tới quan hệ '{relation}' "
                f"ngoài 18 quan hệ đóng (docs/04 §3.1)"
            )
        direction = str(body.get("direction") or "forward")
        if direction not in ("forward", "inverse", "symmetric", "year"):
            raise ValueError(
                f"'{section}.{prop}' có direction='{direction}' không hợp lệ"
            )
        specs[str(prop)] = PropertySpec(
            relation=relation,
            direction=direction,  # type: ignore[arg-type]
            object_type=str(body.get("object_type") or "person"),
        )
    return specs


def load_relation_map(
    path: str | Path | None = None,
    *,
    validate: bool = True,
) -> RelationMap:
    """Nạp bảng mapping property → quan hệ từ YAML.

    Args:
        path: Đường dẫn file YAML (mặc định `configs/wikidata_relations.yaml`).
        validate: Kiểm tra quan hệ ∈ 18 quan hệ đóng.

    Returns:
        `RelationMap` đã nạp.

    Raises:
        FileNotFoundError: Nếu file không tồn tại.
        ValueError: Nếu mapping không hợp lệ.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file mapping: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    properties = _parse_specs(raw.get("properties") or {}, section="properties")
    extended = _parse_specs(
        raw.get("extended_properties") or {}, section="extended_properties"
    )

    if validate:
        _validate_symmetric(properties, extended)

    logger.info(
        "Nạp mapping Wikidata: %d property lõi, %d property mở rộng",
        len(properties),
        len(extended),
    )
    return RelationMap(properties, extended)


def _validate_symmetric(
    properties: dict[str, PropertySpec],
    extended: dict[str, PropertySpec],
) -> None:
    """Kiểm tra tính nhất quán của hướng với quan hệ đối xứng.

    Một property có ``direction="symmetric"`` **phải** ánh xạ tới quan hệ nằm
    trong `SYMMETRIC_RELATIONS` — nếu không, `normalize_orientation` sẽ không
    chuẩn hoá và cạnh đối xứng sinh ra trùng.

    Args:
        properties: Bảng property lõi.
        extended: Bảng property mở rộng.

    Raises:
        ValueError: Nếu có property `symmetric` không khớp.
    """
    for section, table in (("properties", properties), ("extended_properties", extended)):
        for prop, spec in table.items():
            if spec.direction == "symmetric" and spec.relation not in SYMMETRIC_RELATIONS:
                raise ValueError(
                    f"'{section}.{prop}' có direction='symmetric' nhưng quan hệ "
                    f"'{spec.relation}' không nằm trong SYMMETRIC_RELATIONS"
                )


def load_gates(path: str | Path | None = None) -> dict[str, Any]:
    """Nạp ngưỡng Gate của Phase 7 từ YAML.

    Args:
        path: Đường dẫn file YAML (mặc định `configs/wikidata_relations.yaml`).

    Returns:
        Dict ngưỡng, có khoá ``min_positive``, ``max_neg_pos_ratio``,
        ``min_relations_with_positive``, ``max_negatives_per_positive``.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    gates = dict(raw.get("gates") or {})
    gates.setdefault("min_positive", 10000)
    gates.setdefault("max_neg_pos_ratio", 1.0)
    gates.setdefault("min_relations_with_positive", 8)
    gates.setdefault("max_negatives_per_positive", 1)
    return gates
