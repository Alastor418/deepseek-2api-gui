"""Smoke-тест PoW-солвера.

Пропускается, если WASM-модуль отсутствует или wasmtime не установлен.
"""
from pathlib import Path

import pytest

WASM = (
    Path(__file__).parent.parent
    / "app"
    / "providers"
    / "wasm"
    / "sha3_wasm_bg.7b9ca65ddd.wasm"
)

pytestmark = pytest.mark.skipif(
    not WASM.exists(),
    reason=f"WASM module not present at {WASM}",
)


def test_solver_returns_int():
    pytest.importorskip("wasmtime")
    from app.providers.pow_solver import PowSolver

    solver = PowSolver()
    answer = solver.solve(
        "17f75b5e0984f15fc0b8def0c77b48ee4b41b1865f5e8217971722f7870ad4cb",
        "cba9b8a9bf8368b6341c",
        1785354733914,
        144000,
    )
    assert isinstance(answer, int)
    assert answer >= 0


def test_solver_singleton():
    pytest.importorskip("wasmtime")
    from app.providers.pow_solver import get_pow_solver

    a = get_pow_solver()
    b = get_pow_solver()
    assert a is b
