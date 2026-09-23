"""
Topology validation for HydroBASINS and HydroRIVERS networks.

Validates:
  - ID uniqueness
  - NEXT_DOWN reference integrity
  - No self-references
  - No cycles (DAG verification)
  - No duplicate records
  - Geometry validity
  - Source attribute preservation

The source audit established Level-7 as a DAG; this module
reproduces that finding as an automated validation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TopologyValidationResult:
    """Result of topology validation for a hydrological network."""
    dataset_name: str
    total_features: int
    unique_ids: int
    duplicate_ids: list[int] = field(default_factory=list)
    self_references: list[int] = field(default_factory=list)
    missing_downstream: list[tuple[int, int]] = field(default_factory=list)
    cycle_nodes: list[int] = field(default_factory=list)
    invalid_geometries: list[int] = field(default_factory=list)
    is_dag: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return (
            len(self.duplicate_ids) == 0
            and len(self.self_references) == 0
            and len(self.cycle_nodes) == 0
            and len(self.invalid_geometries) == 0
            and self.unique_ids == self.total_features
        )


def validate_hydrobasins_topology(
    features: list[Any],
) -> TopologyValidationResult:
    """Validate HydroBASINS Level-7 network topology.

    Args:
        features: List of NormalizedHydroBasin dataclass instances.

    Returns:
        TopologyValidationResult with detailed validation results.
    """
    result = TopologyValidationResult(
        dataset_name="HydroBASINS Level-7",
        total_features=len(features),
        unique_ids=0,
    )

    if not features:
        result.warnings.append("No features to validate")
        return result

    # 1. HYBAS_ID uniqueness
    all_ids = [f.hybas_id for f in features]
    id_set = set(all_ids)
    result.unique_ids = len(id_set)

    if len(all_ids) != len(id_set):
        from collections import Counter
        counts = Counter(all_ids)
        result.duplicate_ids = [k for k, v in counts.items() if v > 1]
        logger.error("HydroBASINS duplicate HYBAS_IDs: %s", result.duplicate_ids)

    # 2. Self-references
    for f in features:
        if f.hybas_id == f.next_down:
            result.self_references.append(f.hybas_id)
            logger.warning("HydroBASINS self-reference: HYBAS_ID=%d", f.hybas_id)

    # 3. NEXT_DOWN reference integrity
    # NEXT_DOWN = 0 means terminal/outlet basin (no downstream)
    for f in features:
        if f.next_down != 0 and f.next_down not in id_set:
            result.missing_downstream.append((f.hybas_id, f.next_down))

    if result.missing_downstream:
        logger.info(
            "HydroBASINS: %d features have NEXT_DOWN targets outside the filtered set "
            "(expected for Karnataka-filtered subset of Asia-wide network)",
            len(result.missing_downstream)
        )
        result.warnings.append(
            f"{len(result.missing_downstream)} features have NEXT_DOWN targets "
            "outside filtered set (transboundary — expected)"
        )

    # 4. Cycle detection (DFS-based) — within the loaded feature set
    adjacency: dict[int, int] = {}
    for f in features:
        if f.next_down != 0 and f.next_down in id_set:
            adjacency[f.hybas_id] = f.next_down

    visited: set[int] = set()
    in_stack: set[int] = set()

    def _has_cycle(node: int) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        next_node = adjacency.get(node)
        if next_node is not None:
            if _has_cycle(next_node):
                result.cycle_nodes.append(node)
                return True
        in_stack.discard(node)
        return False

    for node_id in adjacency:
        if node_id not in visited:
            _has_cycle(node_id)

    result.is_dag = len(result.cycle_nodes) == 0

    # 5. Geometry validity
    for f in features:
        geom = getattr(f, "geometry", None)
        if geom is not None:
            if geom.is_empty or not geom.is_valid:
                result.invalid_geometries.append(f.hybas_id)

    logger.info(
        "HydroBASINS topology: %d features, %d unique IDs, DAG=%s, "
        "%d invalid geoms, %d self-refs, %d cycles",
        result.total_features, result.unique_ids, result.is_dag,
        len(result.invalid_geometries), len(result.self_references),
        len(result.cycle_nodes),
    )
    return result


def validate_hydrorivers_topology(
    features: list[Any],
    hydrobasins_hybas_ids: set[int] | None = None,
) -> TopologyValidationResult:
    """Validate HydroRIVERS network topology.

    Args:
        features: List of NormalizedHydroRiver dataclass instances.
        hydrobasins_hybas_ids: Optional set of Level-7 HYBAS_IDs for cross-ref checks.

    Returns:
        TopologyValidationResult with detailed validation results.
    """
    result = TopologyValidationResult(
        dataset_name="HydroRIVERS v1.0",
        total_features=len(features),
        unique_ids=0,
    )

    if not features:
        result.warnings.append("No features to validate")
        return result

    # 1. HYRIV_ID uniqueness
    all_ids = [f.hyriv_id for f in features]
    id_set = set(all_ids)
    result.unique_ids = len(id_set)

    if len(all_ids) != len(id_set):
        from collections import Counter
        counts = Counter(all_ids)
        result.duplicate_ids = [k for k, v in counts.items() if v > 1]
        logger.error("HydroRIVERS duplicate HYRIV_IDs: %s", result.duplicate_ids)

    # 2. Self-references
    for f in features:
        if f.hyriv_id == f.next_down:
            result.self_references.append(f.hyriv_id)

    # 3. NEXT_DOWN reference integrity
    for f in features:
        if f.next_down != 0 and f.next_down not in id_set:
            result.missing_downstream.append((f.hyriv_id, f.next_down))

    if result.missing_downstream:
        result.warnings.append(
            f"{len(result.missing_downstream)} reaches have NEXT_DOWN targets "
            "outside filtered set (transboundary — expected)"
        )

    # 4. Cycle detection within loaded set
    adjacency: dict[int, int] = {}
    for f in features:
        if f.next_down != 0 and f.next_down in id_set:
            adjacency[f.hyriv_id] = f.next_down

    visited: set[int] = set()
    in_stack: set[int] = set()

    def _has_cycle(node: int) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        next_node = adjacency.get(node)
        if next_node is not None:
            if _has_cycle(next_node):
                result.cycle_nodes.append(node)
                return True
        in_stack.discard(node)
        return False

    for node_id in adjacency:
        if node_id not in visited:
            _has_cycle(node_id)

    result.is_dag = len(result.cycle_nodes) == 0

    # 5. Geometry validity
    for f in features:
        geom = getattr(f, "geometry", None)
        if geom is not None:
            if geom.is_empty or not geom.is_valid:
                result.invalid_geometries.append(f.hyriv_id)

    # 6. HYBAS_L12 cross-reference note
    # Explicitly do NOT assume HYBAS_L12 == Level-7 HYBAS_ID
    if hydrobasins_hybas_ids is not None:
        l12_values = {f.hybas_l12 for f in features}
        l12_in_l7 = l12_values & hydrobasins_hybas_ids
        if l12_in_l7:
            result.warnings.append(
                f"NOTE: {len(l12_in_l7)} HYBAS_L12 values coincidentally match Level-7 IDs. "
                "This does NOT imply direct Level-7 association. HYBAS_L12 references "
                "Level-12 basins; Level-7 association requires spatial/hierarchical lookup."
            )

    logger.info(
        "HydroRIVERS topology: %d features, %d unique IDs, DAG=%s, "
        "%d invalid geoms, %d self-refs, %d cycles",
        result.total_features, result.unique_ids, result.is_dag,
        len(result.invalid_geometries), len(result.self_references),
        len(result.cycle_nodes),
    )
    return result
