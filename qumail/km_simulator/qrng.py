"""Quantum random number generation for the KM simulator.

Primary path uses a Qiskit circuit — one Hadamard gate per qubit measured in
the computational basis yields uniform random bits from quantum superposition.
If Qiskit (or its Aer simulator) is not installed, we fall back to the OS
CSPRNG (:func:`secrets.token_bytes`) and log a warning, so the simulator still
runs in a minimal dev environment.

No key material is logged — only bit counts and the source used.
"""

from __future__ import annotations

import logging
import secrets

logger = logging.getLogger(__name__)

# Detect Qiskit once at import time so we don't pay the import cost per call.
try:  # pragma: no cover - exercised only when Qiskit is installed
    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator

    _QISKIT_AVAILABLE = True
except ImportError:  # pragma: no cover - default dev path (Qiskit not installed)
    _QISKIT_AVAILABLE = False

# Max qubits per circuit; large key requests are chunked to keep the simulated
# statevector small (2**_MAX_QUBITS amplitudes).
_MAX_QUBITS = 16


def qiskit_available() -> bool:
    """Return True if the Qiskit-backed generator can be used.

    Returns:
        Whether both ``qiskit`` and ``qiskit_aer`` imported successfully.
    """
    return _QISKIT_AVAILABLE


def _generate_bits_qiskit(n: int) -> list[int]:
    """Generate ``n`` random bits with a Hadamard-per-qubit Qiskit circuit.

    Args:
        n: Number of bits to generate.

    Returns:
        A list of ``n`` bits (each 0 or 1).
    """
    simulator = AerSimulator()
    bits: list[int] = []
    remaining = n
    while remaining > 0:
        width = min(_MAX_QUBITS, remaining)
        circuit = QuantumCircuit(width, width)
        circuit.h(range(width))  # superposition: each qubit -> (|0> + |1>)/sqrt(2)
        circuit.measure(range(width), range(width))
        compiled = transpile(circuit, simulator)
        # One shot per circuit; each measured qubit contributes one random bit.
        result = simulator.run(compiled, shots=1, memory=True).result()
        bitstring = result.get_memory()[0]  # e.g. "0110" (MSB = highest qubit)
        bits.extend(int(b) for b in bitstring)
        remaining -= width
    return bits[:n]


def _generate_bits_secrets(n: int) -> list[int]:
    """Generate ``n`` random bits from the OS CSPRNG (fallback path).

    Args:
        n: Number of bits to generate.

    Returns:
        A list of ``n`` bits (each 0 or 1).
    """
    num_bytes = (n + 7) // 8
    raw = secrets.token_bytes(num_bytes)
    bits: list[int] = []
    for byte in raw:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    return bits[:n]


def generate_random_bits(n: int) -> list[int]:
    """Generate ``n`` uniformly random bits.

    Uses the Qiskit QRNG when available, otherwise the OS CSPRNG.

    Args:
        n: Number of bits to generate. Must be non-negative.

    Returns:
        A list of ``n`` bits (each 0 or 1).

    Raises:
        ValueError: If ``n`` is negative.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return []
    if _QISKIT_AVAILABLE:
        return _generate_bits_qiskit(n)
    logger.warning(
        "Qiskit unavailable; falling back to secrets.token_bytes for %d bits", n
    )
    return _generate_bits_secrets(n)


def _bits_to_bytes(bits: list[int]) -> bytes:
    """Pack a list of bits into bytes (MSB-first, zero-padded to a byte).

    Args:
        bits: The bits to pack.

    Returns:
        The packed bytes.
    """
    out = bytearray()
    for i in range(0, len(bits), 8):
        chunk = bits[i : i + 8]
        byte = 0
        for bit in chunk:
            byte = (byte << 1) | bit
        byte <<= 8 - len(chunk)  # left-align if the final chunk is short
        out.append(byte)
    return bytes(out)


def get_random_key(size_bits: int) -> bytes:
    """Generate a quantum key of ``size_bits`` bits.

    Args:
        size_bits: Key length in bits. Must be a positive multiple of 8.

    Returns:
        The key as ``size_bits // 8`` bytes.

    Raises:
        ValueError: If ``size_bits`` is not a positive multiple of 8.
    """
    if size_bits <= 0 or size_bits % 8 != 0:
        raise ValueError("size_bits must be a positive multiple of 8")
    bits = generate_random_bits(size_bits)
    return _bits_to_bytes(bits)
