"""Repo scan planner — auto-split large codebases into review units."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import click

from code_review.file_grouper import discover_files


@dataclass
class ReviewUnit:
    name: str           # e.g. "consensus", "action/protocol/staking"
    path: Path          # Absolute path to unit root
    files: list[Path]   # Files in this unit
    line_count: int     # Total lines
    priority: int = 0   # 0=highest
    tier: str = "other" # core | api | infra | utils | tests | other


@dataclass
class ScanPlan:
    target: Path
    units: list[ReviewUnit] = field(default_factory=list)
    skipped_dirs: list[str] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0

    def to_dict(self) -> dict:
        return {
            "target": str(self.target),
            "units": [
                {
                    "name": u.name,
                    "path": str(u.path),
                    "file_count": len(u.files),
                    "line_count": u.line_count,
                    "priority": u.priority,
                    "tier": u.tier,
                }
                for u in self.units
            ],
            "skipped_dirs": self.skipped_dirs,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
        }


# Directories to always skip
_SKIP_DIRS = {
    ".git", ".github", ".vscode", ".idea", "node_modules",
    "vendor", "third_party", "testdata", ".cache", "dist", "build",
}

# Tier classification by directory name keywords
# Order matters: tests before utils so "testutil" matches tests, not utils
_TIER_PATTERNS: list[tuple[str, list[str]]] = [
    ("core", ["core", "internal", "consensus", "blockchain", "protocol", "engine", "chain", "chainservice"]),
    ("api", ["api", "server", "handler", "endpoint", "route", "grpc", "rest"]),
    ("infra", ["db", "database", "state", "config", "storage", "cache", "migration"]),
    ("tests", ["test", "tests", "e2etest", "testutil", "testing", "mock", "mocks", "fixture", "fixtures"]),
    ("utils", ["pkg", "utils", "util", "lib", "tools", "helper", "helpers", "common", "shared", "misc"]),
]


_line_count_cache: dict[Path, int] = {}


def _count_lines(path: Path) -> int:
    """Count lines in a file, returning 0 on error. Results are cached."""
    if path in _line_count_cache:
        return _line_count_cache[path]
    try:
        count = path.read_text(errors="replace").count("\n") + 1
    except OSError:
        count = 0
    _line_count_cache[path] = count
    return count


def _classify_tier(name: str) -> str:
    """Classify a unit name into a tier based on directory name patterns."""
    parts = name.lower().replace("\\", "/").split("/")
    # Check tiers in order — tests checked before utils so "testutil" → tests
    for tier, keywords in _TIER_PATTERNS:
        for part in parts:
            if part in keywords:
                return tier
    return "other"


def _tier_priority(tier: str) -> int:
    """Return base priority for a tier (lower = higher priority)."""
    order = {"core": 0, "api": 1, "infra": 2, "other": 3, "utils": 4, "tests": 5}
    return order.get(tier, 3)


def scan_repo(
    target: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> ScanPlan:
    """Scan a repository and group files into logical review units."""
    target = target.resolve()
    all_files = discover_files(target, include=include, exclude=exclude)

    if not all_files:
        return ScanPlan(target=target)

    try:
        # Group files by directory
        dir_files: dict[str, list[Path]] = {}
        skipped: set[str] = set()

        for f in all_files:
            rel = f.relative_to(target)
            parts = rel.parts

            # Skip known non-code directories
            if any(p in _SKIP_DIRS for p in parts):
                skipped.add(parts[0] if parts else str(rel))
                continue

            # Group by first or second level directory
            if len(parts) <= 1:
                # Root-level file
                group = "."
            elif len(parts) == 2:
                group = parts[0]
            else:
                # Use first two levels for deeper nesting
                group = str(Path(parts[0]) / parts[1])

            dir_files.setdefault(group, []).append(f)

        # Build initial units with line counts
        raw_units: list[ReviewUnit] = []
        for name, files in dir_files.items():
            line_count = sum(_count_lines(f) for f in files)
            unit_path = target / name if name != "." else target
            raw_units.append(ReviewUnit(
                name=name,
                path=unit_path,
                files=files,
                line_count=line_count,
            ))

        # Smart merging: merge small units (<500 lines) into parent
        merged = _merge_small_units(raw_units, min_lines=500)

        # Smart splitting: split large units (>15K lines) into sub-units
        final_units = []
        for unit in merged:
            if unit.line_count > 15000 and unit.name != ".":
                sub_units = _split_large_unit(unit, target)
                final_units.extend(sub_units)
            else:
                final_units.append(unit)

        # Prioritize
        final_units = prioritize_units(final_units)

        total_files = sum(len(u.files) for u in final_units)
        total_lines = sum(u.line_count for u in final_units)

        return ScanPlan(
            target=target,
            units=final_units,
            skipped_dirs=sorted(skipped),
            total_files=total_files,
            total_lines=total_lines,
        )
    finally:
        _line_count_cache.clear()


def _merge_small_units(units: list[ReviewUnit], min_lines: int = 500) -> list[ReviewUnit]:
    """Merge units with < min_lines into their parent directory."""
    large = [u for u in units if u.line_count >= min_lines]
    small = [u for u in units if u.line_count < min_lines]

    if not small:
        return large

    # Build parent→unit map; use first match if multiple units share a parent
    parent_map: dict[str, ReviewUnit] = {}
    for u in large:
        parent = str(Path(u.name).parent) if "/" in u.name or "\\" in u.name else "."
        if parent not in parent_map:
            parent_map[parent] = u

    # Also allow merging small units directly into a large unit with the same name
    name_map: dict[str, ReviewUnit] = {u.name: u for u in large}

    orphans: list[Path] = []
    for u in small:
        parent = str(Path(u.name).parent) if "/" in u.name or "\\" in u.name else "."
        if u.name in name_map:
            # Exact parent match (small "action" merges into large "action")
            target_unit = name_map[u.name]
            target_unit.files.extend(u.files)
            target_unit.line_count += u.line_count
        elif parent in parent_map:
            target_unit = parent_map[parent]
            target_unit.files.extend(u.files)
            target_unit.line_count += u.line_count
        else:
            orphans.extend(u.files)

    # Collect remaining orphans into a "_misc" unit
    if orphans:
        line_count = sum(_count_lines(f) for f in orphans)
        # Use common parent of all orphan files
        misc_path = orphans[0].parent
        large.append(ReviewUnit(
            name="_misc",
            path=misc_path,
            files=orphans,
            line_count=line_count,
        ))

    return large


def _split_large_unit(unit: ReviewUnit, target: Path) -> list[ReviewUnit]:
    """Split a large unit into sub-directory units."""
    sub_groups: dict[str, list[Path]] = {}

    for f in unit.files:
        rel = f.relative_to(target)
        parts = rel.parts
        # Go one level deeper than the unit name
        unit_depth = len(Path(unit.name).parts)
        if len(parts) > unit_depth + 1:
            sub_name = str(Path(*parts[: unit_depth + 1]))
        else:
            sub_name = unit.name

        sub_groups.setdefault(sub_name, []).append(f)

    if len(sub_groups) <= 1:
        return [unit]

    result = []
    for name, files in sub_groups.items():
        line_count = sum(_count_lines(f) for f in files)
        result.append(ReviewUnit(
            name=name,
            path=target / name,
            files=files,
            line_count=line_count,
        ))
    return result


def prioritize_units(units: list[ReviewUnit]) -> list[ReviewUnit]:
    """Classify and sort units by tier and size."""
    for unit in units:
        unit.tier = _classify_tier(unit.name)
        unit.priority = _tier_priority(unit.tier)

    # Sort by tier priority (asc), then line count (desc) within tier
    units.sort(key=lambda u: (u.priority, -u.line_count))

    # Assign sequential priority numbers
    for i, unit in enumerate(units):
        unit.priority = i

    return units


def print_plan(plan: ScanPlan) -> None:
    """Pretty-print the scan plan to terminal."""
    click.echo(f"\n{'='*70}")
    click.echo(f"  Scan Plan: {plan.target}")
    click.echo(f"{'='*70}")
    click.echo(f"  Total files: {plan.total_files}")
    click.echo(f"  Total lines: {plan.total_lines:,}")
    click.echo(f"  Review units: {len(plan.units)}")
    if plan.skipped_dirs:
        click.echo(f"  Skipped dirs: {', '.join(plan.skipped_dirs)}")
    click.echo()

    # Table header
    click.echo(f"  {'#':<4} {'Unit':<40} {'Tier':<8} {'Files':<7} {'Lines':<10}")
    click.echo(f"  {'─'*4} {'─'*40} {'─'*8} {'─'*7} {'─'*10}")

    for i, unit in enumerate(plan.units):
        name = unit.name if len(unit.name) <= 40 else "..." + unit.name[-37:]
        click.echo(
            f"  {i:<4} {name:<40} {unit.tier:<8} {len(unit.files):<7} {unit.line_count:<10,}"
        )

    click.echo()
