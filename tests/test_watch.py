"""File-change detection used by the build watch loop."""

from argparse import Namespace
from pathlib import Path

from scenet.cli import build_parser, main, run_build, run_watch
from scenet.watch import snapshot, track_reads, wait_for_change


PANEL = "cast: {a: {reference: alice}}\n"


def test_track_reads_includes_files_opened_during_compilation(tmp_path: Path):
    source = tmp_path / "scene.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")

    with track_reads() as dependencies:
        source.read_text(encoding="utf-8")

    assert source.resolve() in dependencies


def test_polling_detects_a_change_with_a_fake_sleep(tmp_path: Path):
    source = tmp_path / "scene.panel.yaml"
    source.write_text("before", encoding="utf-8")
    before = snapshot({source.resolve()})

    def save_change(interval: float) -> None:
        assert interval == 0.5
        source.write_text("after", encoding="utf-8")

    changed = wait_for_change(
        {source.resolve()},
        before,
        sleep=save_change,
        use_native=False,
    )

    assert changed == {source.resolve()}


def test_watch_flag_is_exposed_by_the_build_parser(tmp_path: Path):
    source = tmp_path / "scene.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")

    args = build_parser().parse_args(["build", str(source), "--watch"])
    assert args.watch is True


def test_watched_build_writes_the_same_svg_as_a_plain_build(tmp_path: Path):
    source = tmp_path / "scene.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")
    plain = tmp_path / "plain.svg"
    watched = tmp_path / "watched.svg"

    assert main(["build", str(source), "-o", str(plain), "--quiet"]) == 0
    args = build_parser().parse_args(
        ["build", str(source), "-o", str(watched), "--quiet", "--watch"]
    )
    assert run_build(args) == 0
    assert plain.read_bytes() == watched.read_bytes()
    assert source.resolve() in args.watch_dependencies


def test_watch_loop_continues_after_a_failed_build(monkeypatch, tmp_path: Path):
    import scenet.cli as cli
    import scenet.watch as watch

    source = tmp_path / "scene.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")
    args = Namespace(source=source, watch=True)
    results = iter([1, 0])
    builds: list[int] = []
    waits = iter([None, KeyboardInterrupt()])

    def build(_args: Namespace) -> int:
        status = next(results)
        builds.append(status)
        return status

    def wait(*_args, **_kwargs):
        result = next(waits)
        if isinstance(result, BaseException):
            raise result
        return set()

    monkeypatch.setattr(cli, "run_build", build)
    monkeypatch.setattr(watch, "wait_for_change", wait)

    assert run_watch(args) == 0
    assert builds == [1, 0]
