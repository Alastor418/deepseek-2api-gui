"""WASM-based PoW solver for DeepSeekHashV1.

Адаптировано из https://github.com/KOSFin/deepseek-api

ВАЖНО: wasmtime Store не потокобезопасен. Один экземпляр PowSolver
нельзя использовать из нескольких потоков одновременно. Для этого
внутри используется threading.Lock — solve() сериализован.
"""
import ctypes
import struct
import threading
from pathlib import Path

import wasmtime

WASM_PATH = Path(__file__).parent / "wasm" / "sha3_wasm_bg.7b9ca65ddd.wasm"

_REQUIRED_EXPORTS = (
    "memory",
    "__wbindgen_add_to_stack_pointer",
    "__wbindgen_export_0",
    "wasm_solve",
)


class PowSolver:
    def __init__(self) -> None:
        if not WASM_PATH.exists():
            raise RuntimeError(f"WASM module not found: {WASM_PATH}")

        self._lock = threading.Lock()
        self.store = wasmtime.Store()
        self.engine = self.store.engine

        module = wasmtime.Module.from_file(self.engine, str(WASM_PATH))
        linker = wasmtime.Linker(self.engine)
        self.instance = linker.instantiate(self.store, module)
        exports = self.instance.exports(self.store)

        missing = [n for n in _REQUIRED_EXPORTS if n not in exports]
        if missing:
            raise RuntimeError(
                f"WASM module is missing required exports: {missing}. "
                f"Available: {sorted(exports.keys())}"
            )

        self.memory = exports["memory"]
        self.add_to_stack = exports["__wbindgen_add_to_stack_pointer"]
        self.alloc = exports["__wbindgen_export_0"]
        self.wasm_solve = exports["wasm_solve"]

    def _write_memory(self, offset: int, data: bytes) -> None:
        base = ctypes.cast(self.memory.data_ptr(self.store), ctypes.c_void_p).value
        if base is None:
            raise RuntimeError("WASM memory data_ptr returned NULL")
        ctypes.memmove(base + offset, data, len(data))

    def _read_memory(self, offset: int, size: int) -> bytes:
        base = ctypes.cast(self.memory.data_ptr(self.store), ctypes.c_void_p).value
        if base is None:
            raise RuntimeError("WASM memory data_ptr returned NULL")
        return ctypes.string_at(base + offset, size)

    def _encode_string(self, text: str) -> tuple[int, int]:
        data = text.encode("utf-8")
        length = len(data)
        ptr_val = self.alloc(self.store, length, 1)
        ptr = int(ptr_val.value) if hasattr(ptr_val, "value") else int(ptr_val)
        self._write_memory(ptr, data)
        return ptr, length

    def solve(
        self, challenge_str: str, salt: str, expire_at: int, difficulty: float
    ) -> int:
        """Возвращает answer (int) для DeepSeekHashV1.

        Бросает RuntimeError, если решение не найдено.
        Потокобезопасен (внутри self._lock).
        """
        prefix = f"{salt}_{expire_at}_"

        with self._lock:
            retptr = self.add_to_stack(self.store, -16)
            try:
                ptr_challenge, len_challenge = self._encode_string(challenge_str)
                ptr_prefix, len_prefix = self._encode_string(prefix)

                self.wasm_solve(
                    self.store,
                    retptr,
                    ptr_challenge,
                    len_challenge,
                    ptr_prefix,
                    len_prefix,
                    float(difficulty),
                )

                status_bytes = self._read_memory(retptr, 4)
                status = struct.unpack("<i", status_bytes)[0]

                if status == 0:
                    raise RuntimeError(
                        "WASM solve: no solution found (status=0)"
                    )

                value_bytes = self._read_memory(retptr + 8, 8)
                value = struct.unpack("<d", value_bytes)[0]
                return int(value)
            finally:
                self.add_to_stack(self.store, 16)


# Singleton — дорого инициализировать повторно (компиляция WASM).
_solver: PowSolver | None = None
_solver_lock = threading.Lock()


def get_pow_solver() -> PowSolver:
    global _solver
    if _solver is None:
        with _solver_lock:
            if _solver is None:
                _solver = PowSolver()
    return _solver
