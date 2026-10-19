"""Tests for dependency tracking and watch mode."""

from collections.abc import Callable
from pathlib import Path

import scenet.cli as cli
from scenet.pipeline import compile_book_file
from scenet.watch import snapshot, watch_loop


PANEL = """cast:
  alice: {reference: alice}
script:
  - say: {by: alice, text: Hello}
"""


def test_compiler_reports_files_it_reads(tmp_path: Path) -> None:
    source = tmp_path / "watch.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")
    dependencies: set[Path] = set()

    compile_book_file(source, dependencies=dependencies)

    assert source.resolve() in dependencies
    assert any(path.name == "alice.puppet.yaml" for path in dependencies)
    assert any(path.is_dir() and path.name == "library" for path in dependencies)


def test_watch_loop_rebuilds_again_after_a_failed_build() -> None:
    dependencies = {Path("source.panel.yaml")}
    state = {"revision": 0}
    calls: list[int] = []

    def wait(_interval: float, _dependencies: set[Path]) -> None:
        state["revision"] += 1

    def rebuild() -> int:
        calls.append(state["revision"])
        return 1 if len(calls) == 1 else 0

    watch_loop(
        dependencies,
        rebuild,
        wait=wait,
        take_snapshot=lambda _paths: state["revision"],
        max_iterations=2,
    )

    assert calls == [1, 2]


def test_watch_build_matches_regular_build(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "watch.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")
    assert cli.main(["build", str(source), "--quiet"]) == 0
    regular = source.with_name("watch.svg").read_bytes()

    source.with_name("watch.svg").unlink()

    def no_watch(_dependencies: set[Path], _rebuild: Callable[[], object]) -> None:
        return None

    monkeypatch.setattr(cli, "watch_loop", no_watch)
    assert cli.main(["build", str(source), "--watch", "--quiet"]) == 0
    assert source.with_name("watch.svg").read_bytes() == regular


def test_snapshot_detects_content_and_directory_changes(tmp_path: Path) -> None:
    source = tmp_path / "source.panel.yaml"
    source.write_text("one", encoding="utf-8")
    dependencies = {source, tmp_path}
    before = snapshot(dependencies)
    source.write_text("two", encoding="utf-8")
    assert snapshot(dependencies) != before
