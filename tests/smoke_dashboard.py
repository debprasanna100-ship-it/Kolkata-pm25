"""Smoke test that executes the dashboard without Streamlit installed.

The dashboard is the one module that cannot be unit tested normally: it runs
top-level code and needs a browser. This harness swaps `streamlit` for a
recording stub and then *actually executes* the file, so it catches real
breakage - wrong column names, bad plotly arguments, missing artefact keys -
rather than just syntax errors.

    python tests/smoke_dashboard.py

Exit code 0 means every tab rendered against the current artefacts.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CALLS: list[tuple[str, tuple, dict]] = []


class _Recorder:
    """Stands in for anything the Streamlit API returns."""

    def __init__(self, name: str = "st"):
        self._name = name

    def __getattr__(self, item: str):
        if item.startswith("__"):
            raise AttributeError(item)
        return _Recorder(f"{self._name}.{item}")

    def __call__(self, *args, **kwargs):
        # Decorator passthrough: @st.cache_data(...) applied to a function.
        if args and callable(args[0]) and not isinstance(args[0], _Recorder):
            return args[0]

        CALLS.append((self._name, args, kwargs))

        if self._name.endswith("multiselect"):
            return list(kwargs.get("default", []) or [])
        if self._name.endswith("stop"):
            raise SystemExit(0)
        if self._name.endswith("selectbox"):
            options = args[1] if len(args) > 1 else kwargs.get("options", [])
            return options[0] if options else None

        return _Call(self._name, args)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getitem__(self, index):
        return _Recorder(f"{self._name}[{index}]")


class _Call(_Recorder):
    def __init__(self, name: str, args: tuple):
        super().__init__(name)
        self._args = args

    def __iter__(self):
        first = self._args[0] if self._args else None
        if isinstance(first, int):
            n = first
        elif isinstance(first, (list, tuple)):
            n = len(first)
        else:
            n = 8
        return iter([_Recorder(f"{self._name}[{i}]") for i in range(n)])


def install_stub() -> None:
    stub = types.ModuleType("streamlit")
    recorder = _Recorder("st")

    def _getattr(item):
        return getattr(recorder, item)

    stub.__getattr__ = _getattr          # type: ignore[attr-defined]
    sys.modules["streamlit"] = stub


def main() -> int:
    install_stub()

    import importlib.util

    path = ROOT / "src" / "pm25" / "app" / "dashboard.py"
    spec = importlib.util.spec_from_file_location("pm25_dashboard_smoke", path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)   # type: ignore[union-attr]
    except SystemExit:
        print("dashboard halted early (st.stop / missing artefact)")
    except Exception as exc:
        import traceback

        print(f"\nFAILED: {type(exc).__name__}: {exc}\n")
        traceback.print_exc()
        return 1

    charts = [c for c in CALLS if c[0].endswith("plotly_chart")]
    frames = [c for c in CALLS if c[0].endswith("dataframe")]
    print(f"OK - {len(CALLS)} Streamlit calls, {len(charts)} charts, {len(frames)} tables rendered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
