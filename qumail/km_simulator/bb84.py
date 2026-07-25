"""BB84 quantum key distribution simulation (educational + key generation).

Simulates the BB84 protocol between Alice and Bob:

1. Alice picks random bits and random bases (rectilinear ``+`` / diagonal ``x``).
2. Bob picks random measurement bases.
3. Where their bases match, the measured bit equals Alice's bit; where they
   differ, Bob's result is random ("sifting" discards the mismatched positions).
4. QBER (quantum bit error rate) is estimated on the sifted key; in a
   noiseless, eavesdropper-free channel it is ~0.

Random bits/bases come from :mod:`km_simulator.qrng`, so the simulation uses
the same QRNG (Qiskit or CSPRNG fallback) as live key generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from km_simulator import qrng

logger = logging.getLogger(__name__)


@dataclass
class BB84Result:
    """Outcome of one BB84 run.

    Attributes:
        sifted_key: Bits kept after basis reconciliation (Alice == Bob where
            bases matched, minus any positions sacrificed for QBER estimation).
        qber: Estimated quantum bit error rate in ``[0.0, 1.0]``.
        raw_length: Number of qubits Alice initially sent.
        sifted_length: Number of positions surviving sifting.
    """

    sifted_key: list[int] = field(default_factory=list)
    qber: float = 0.0
    raw_length: int = 0
    sifted_length: int = 0


def simulate_bb84(
    n_qubits: int = 256, eavesdropper: bool = False, sample_fraction: float = 0.1
) -> BB84Result:
    """Run a BB84 exchange and return the sifted key plus estimated QBER.

    Args:
        n_qubits: Number of qubits Alice prepares and sends.
        eavesdropper: If True, simulate an intercept-resend attacker (Eve),
            which injects ~25% errors on sifted bits — useful for the demo.
        sample_fraction: Fraction of the sifted key disclosed to estimate QBER
            (these bits are consumed and excluded from the returned key).

    Returns:
        A :class:`BB84Result` with the sifted key, QBER, and length metadata.

    Raises:
        ValueError: If ``n_qubits`` is negative or ``sample_fraction`` is not
            in ``[0.0, 1.0)``.
    """
    if n_qubits < 0:
        raise ValueError("n_qubits must be non-negative")
    if not 0.0 <= sample_fraction < 1.0:
        raise ValueError("sample_fraction must be in [0.0, 1.0)")

    # Alice's random bits and bases; Bob's random measurement bases.
    # Basis convention: 0 = rectilinear (+), 1 = diagonal (x).
    alice_bits = qrng.generate_random_bits(n_qubits)
    alice_bases = qrng.generate_random_bits(n_qubits)
    bob_bases = qrng.generate_random_bits(n_qubits)

    # If Eve is present she measures in her own random bases, collapsing the
    # state; her (re)prepared qubit is what reaches Bob.
    eve_bases = qrng.generate_random_bits(n_qubits) if eavesdropper else None
    bob_noise = qrng.generate_random_bits(n_qubits)  # random outcome on basis mismatch

    sifted_alice: list[int] = []
    sifted_bob: list[int] = []
    for i in range(n_qubits):
        travelling_bit = alice_bits[i]
        travelling_basis = alice_bases[i]

        if eve_bases is not None:
            # Eve measures; if her basis differs from Alice's her result is
            # random and she resends in her (wrong) basis.
            if eve_bases[i] == alice_bases[i]:
                travelling_bit = alice_bits[i]
            else:
                travelling_bit = bob_noise[i]  # random collapse under Eve
            travelling_basis = eve_bases[i]

        # Bob keeps the bit only when his basis matches the qubit's basis.
        if bob_bases[i] == travelling_basis:
            bob_bit = travelling_bit
        else:
            bob_bit = bob_noise[i]  # basis mismatch -> random outcome

        # Sifting: keep positions where Alice's and Bob's bases agree.
        if alice_bases[i] == bob_bases[i]:
            sifted_alice.append(alice_bits[i])
            sifted_bob.append(bob_bit)

    sifted_length = len(sifted_alice)

    # Estimate QBER by disclosing a sample of the sifted positions.
    sample_size = int(sifted_length * sample_fraction)
    if sample_size > 0:
        errors = sum(
            1 for a, b in zip(sifted_alice[:sample_size], sifted_bob[:sample_size]) if a != b
        )
        qber = errors / sample_size
    else:
        qber = 0.0

    # The disclosed sample is consumed; the remainder is the usable key.
    final_key = sifted_bob[sample_size:]

    logger.info(
        "BB84: raw=%d sifted=%d qber=%.3f eavesdropper=%s",
        n_qubits,
        sifted_length,
        qber,
        eavesdropper,
    )
    return BB84Result(
        sifted_key=final_key,
        qber=qber,
        raw_length=n_qubits,
        sifted_length=sifted_length,
    )
