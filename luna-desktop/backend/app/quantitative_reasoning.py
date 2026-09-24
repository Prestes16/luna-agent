"""Quantitative reasoning for Luna: exact math first, physics when the mechanism requires it.

This module is instruction-only. It supplies deterministic numerical helpers and
compact domain guidance so cyber conclusions are tied to representation, units,
bounds, rounding, conservation and measurable physical mechanisms.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable


@dataclass(frozen=True)
class QuantitativeProfile:
    name: str
    markers: tuple[str, ...]
    checks: tuple[str, ...]
    invariants: tuple[str, ...]


QUANTITATIVE_PROFILES: tuple[QuantitativeProfile, ...] = (
    QuantitativeProfile(
        "blockchain_financial",
        ("solana", "anchor", "spl", "token", "lamport", "usdc", "smart contract", "solidity", "fee", "vault"),
        (
            "integer/base-unit representation and decimal scale",
            "checked overflow/underflow and intermediate width",
            "multiply/divide order, rounding direction and dust",
            "fee/split conservation across every state transition",
            "probability/randomness mapping without modulo bias",
        ),
        (
            "sum(inflows) = sum(outflows) + fees + retained state",
            "no value is created or destroyed by rounding",
            "authority/state transition cannot change arithmetic semantics",
        ),
    ),
    QuantitativeProfile(
        "integer_memory_binary",
        ("overflow", "underflow", "integer", "u64", "u128", "i64", "signed", "unsigned", "pointer", "offset", "endian", "bit"),
        (
            "bit width, signedness and exact integer bounds",
            "promotion/cast/truncation rules",
            "address/offset/alignment arithmetic",
            "endianness and bit-mask semantics",
            "checked versus wrapping/saturating operations",
        ),
        (
            "all intermediate values remain representable",
            "casts preserve the intended mathematical value",
            "index/address arithmetic stays inside the intended object",
        ),
    ),
    QuantitativeProfile(
        "probability_randomness_crypto",
        ("probability", "probabilidade", "random", "randomness", "rng", "entropy", "nonce", "hash", "collision", "bias", "vrf", "crypto"),
        (
            "sample space and distribution",
            "entropy/min-entropy and independence assumptions",
            "modular arithmetic and finite-domain mapping",
            "collision/birthday bounds and nonce uniqueness",
            "bias, rejection sampling and adversarial influence",
        ),
        (
            "probabilities sum to one over the defined sample space",
            "security claims state their assumptions and bit-strength",
            "uniform source to bounded output does not introduce hidden bias",
        ),
    ),
    QuantitativeProfile(
        "numeric_programming",
        ("float", "double", "decimal", "precision", "rounding", "arredond", "fixed point", "fixed-point", "porcent", "percentage", "rate", "ratio"),
        (
            "number representation and precision",
            "unit/dimension consistency",
            "rounding mode and operation ordering",
            "error propagation and boundary cases",
            "monotonicity/conservation properties",
        ),
        (
            "units remain dimensionally consistent",
            "rounding error is bounded and cannot accumulate into forbidden state",
            "comparison thresholds use the intended numeric domain",
        ),
    ),
    QuantitativeProfile(
        "network_signal_physics",
        ("wifi", "wi-fi", "802.11", "radio", "rf", "rssi", "snr", "frequency", "frequência", "latency", "latência", "bandwidth", "throughput", "signal"),
        (
            "frequency, wavelength and propagation assumptions",
            "bandwidth, SNR/noise and achievable information rate",
            "latency decomposition and timing resolution",
            "sampling/window size and measurement variance",
            "units/logarithmic scales such as dB/dBm",
        ),
        (
            "dimensions/units are consistent",
            "measured effects exceed noise and resolution limits",
            "correlation is not promoted to causation without a physical mechanism",
        ),
    ),
    QuantitativeProfile(
        "hardware_side_channel",
        ("side channel", "side-channel", "timing attack", "power analysis", "emission", "em ", "voltage", "current", "thermal", "clock", "fault injection"),
        (
            "clock/time resolution and repeated-sample statistics",
            "power/energy/current/voltage relationships",
            "signal-to-noise and leakage model",
            "physical coupling path and measurement bandwidth",
            "confidence intervals/effect size before attribution",
        ),
        (
            "a physical claim identifies a measurable coupling mechanism",
            "effect size is distinguishable from measurement noise",
            "units and acquisition conditions are explicit",
        ),
    ),
)


def select_quantitative_profile(context: str) -> QuantitativeProfile | None:
    normalized = context.casefold()
    ranked: list[tuple[int, int, QuantitativeProfile]] = []
    for index, profile in enumerate(QUANTITATIVE_PROFILES):
        hits = sum(marker in normalized for marker in profile.markers)
        if hits:
            ranked.append((hits, -index, profile))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], -item[1]))
    return ranked[0][2]


def integer_bounds(bits: int, signed: bool) -> tuple[int, int]:
    if bits <= 0:
        raise ValueError("bits must be positive")
    if signed:
        high = (1 << (bits - 1)) - 1
        low = -(1 << (bits - 1))
        return low, high
    return 0, (1 << bits) - 1


def integer_margin(value: int, bits: int, signed: bool) -> int:
    """Distance to the nearest representable boundary; negative means out of range."""
    low, high = integer_bounds(bits, signed)
    if value < low:
        return value - low
    if value > high:
        return high - value
    return min(value - low, high - value)


def scale_decimal_exact(value: str, decimals: int) -> int:
    """Convert a decimal string to base units without binary floating-point."""
    if decimals < 0:
        raise ValueError("decimals must be non-negative")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal value") from exc
    scaled = decimal_value * (Decimal(10) ** decimals)
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("value has more fractional precision than the scale permits")
    return int(integral)


def max_unsigned_input_before_mul_overflow(bits: int, factor: int) -> int:
    """Largest unsigned x such that x * factor is representable in the given bit width."""
    if bits <= 0:
        raise ValueError("bits must be positive")
    if factor <= 0:
        raise ValueError("factor must be positive")
    return ((1 << bits) - 1) // factor


def floor_rounding_loss_numerator(value: int, numerator: int, denominator: int) -> int:
    """Discarded numerator units for floor(value*numerator/denominator)."""
    if value < 0 or numerator < 0 or denominator <= 0:
        raise ValueError("value/numerator must be non-negative and denominator positive")
    return (value * numerator) % denominator

def mul_div_floor(a: int, b: int, denominator: int) -> tuple[int, int]:
    """Exact integer multiply/divide; returns (quotient, discarded remainder)."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    product = a * b
    quotient, remainder = divmod(product, denominator)
    return quotient, remainder


def conservation_residual(inflows: Iterable[int], outflows: Iterable[int]) -> int:
    """Zero means exact conservation in the same base unit."""
    return sum(int(value) for value in inflows) - sum(int(value) for value in outflows)


def shannon_entropy_bits(probabilities: Iterable[float]) -> float:
    values = [float(p) for p in probabilities]
    if not values or any(p < 0.0 or p > 1.0 for p in values):
        raise ValueError("probabilities must be within [0,1]")
    if not math.isclose(sum(values), 1.0, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError("probabilities must sum to 1")
    entropy = -sum(p * math.log2(p) for p in values if p > 0.0)
    return round(entropy, 12)


def wilson_score_interval(
    successes: int,
    trials: int,
    *,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
    """Deterministic Wilson score interval for controlled Bernoulli repetitions.

    The result is descriptive uncertainty for the observed experiment, not a
    probability that an exploit will work on an untested host/environment.
    """
    if isinstance(successes, bool) or isinstance(trials, bool):
        raise ValueError("successes/trials must be integers")
    if not isinstance(successes, int) or not isinstance(trials, int):
        raise ValueError("successes/trials must be integers")
    if trials < 1 or successes < 0 or successes > trials:
        raise ValueError("require 0 <= successes <= trials and trials >= 1")
    if not math.isfinite(z) or z <= 0.0:
        raise ValueError("z must be finite and positive")

    p_hat = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    center = (p_hat + z2 / (2.0 * trials)) / denominator
    margin = (
        z
        * math.sqrt(
            (p_hat * (1.0 - p_hat) + z2 / (4.0 * trials)) / trials
        )
        / denominator
    )
    return (
        round(max(0.0, center - margin), 10),
        round(min(1.0, center + margin), 10),
    )


def zero_failure_probability_upper_bound(
    trials: int,
    *,
    alpha: float = 0.05,
) -> float:
    """Exact one-sided binomial upper bound after zero observed failures."""
    if isinstance(trials, bool) or not isinstance(trials, int):
        raise ValueError("trials must be an integer")
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if not math.isfinite(alpha) or not (0.0 < alpha < 1.0):
        raise ValueError("alpha must satisfy 0 < alpha < 1")
    return round(1.0 - math.pow(alpha, 1.0 / trials), 10)


def birthday_collision_probability(samples: int, bits: int) -> float:
    if samples < 0 or bits <= 0:
        raise ValueError("samples must be non-negative and bits positive")
    if samples < 2:
        return 0.0
    space = float(2 ** bits)
    exponent = -(samples * (samples - 1)) / (2.0 * space)
    return max(0.0, min(1.0, 1.0 - math.exp(exponent)))


def wavelength_m(frequency_hz: float, propagation_speed_m_s: float = 299_792_458.0) -> float:
    if frequency_hz <= 0.0 or propagation_speed_m_s <= 0.0:
        raise ValueError("frequency and propagation speed must be positive")
    return propagation_speed_m_s / frequency_hz


def shannon_capacity_bps(bandwidth_hz: float, snr_linear: float) -> float:
    if bandwidth_hz < 0.0 or snr_linear < 0.0:
        raise ValueError("bandwidth and SNR must be non-negative")
    return bandwidth_hz * math.log2(1.0 + snr_linear)


_RUST_U64_MUL_DIV_RE = re.compile(
    r"(?is)\blet\s+(?P<dest>[A-Za-z_]\w*)\s*=\s*"
    r"(?P<src>[A-Za-z_]\w*)\s*\*\s*(?P<mul>\d[\d_]*)\s*/\s*(?P<div>\d[\d_]*)\s*;?"
)


def quantitative_fact_sheet(context: str, max_chars: int = 900) -> str:
    """Derive compact deterministic facts from simple observed integer expressions."""
    match = _RUST_U64_MUL_DIV_RE.search(context)
    if not match:
        return ""
    src = match.group("src")
    type_patterns = (
        rf"\b{re.escape(src)}\b.{{0,48}}\bu64\b",
        rf"\bu64\b.{{0,48}}\b{re.escape(src)}\b",
    )
    if not any(re.search(pattern, context, flags=re.IGNORECASE | re.DOTALL) for pattern in type_patterns):
        return ""

    mul = int(match.group("mul").replace("_", ""))
    div = int(match.group("div").replace("_", ""))
    if mul <= 0 or div <= 0:
        return ""

    maximum = (1 << 64) - 1
    threshold = max_unsigned_input_before_mul_overflow(64, mul)
    gcd = math.gcd(mul, div)
    reduced_mul = mul // gcd
    reduced_div = div // gcd
    facts = (
        f"DETERMINISTIC NUMERIC FACTS: observed `{match.group(0).strip()}` and {src}:u64. "
        f"With no observed cast/helper, Rust infers the unsuffixed integer literals in this expression "
        f"to the u64 operation domain; the source multiplication `{src}*{mul}` is therefore u64. "
        f"u64::MAX={maximum}; multiplication is mathematically representable iff "
        f"{src}<={threshold}; {threshold + 1} is the first overflowing input for factor {mul}. "
        f"The exact ratio {mul}/{div} reduces to {reduced_mul}/{reduced_div}. After a non-overflowing "
        f"multiply, u64 division floors; discarded fraction is (({src}*{mul})%{div})/{div} of one "
        f"base unit, so per-evaluation floor loss is <1 base unit. UNKNOWN from the snippet: whether "
        f"{src} can reach that threshold, whether an explicit cast/helper changes the operation, and "
        "the deployed overflow-check behavior. Do not substitute i64/i128 bounds without observed casts."
    )
    return facts[:max_chars]

def quantitative_claim_violations(context: str, response: str) -> tuple[str, ...]:
    """Deterministic V17/V18 checks for strong quantitative/physical output claims."""
    reasons: list[str] = []
    normalized_context = context.casefold()
    normalized_response = response.casefold()

    match = _RUST_U64_MUL_DIV_RE.search(context)
    if match:
        src = match.group("src")
        type_patterns = (
            rf"\b{re.escape(src)}\b.{{0,48}}\bu64\b",
            rf"\bu64\b.{{0,48}}\b{re.escape(src)}\b",
        )
        if any(
            re.search(pattern, context, flags=re.IGNORECASE | re.DOTALL)
            for pattern in type_patterns
        ):
            mul = int(match.group("mul").replace("_", ""))
            div = int(match.group("div").replace("_", ""))
            if mul > 0 and div > 0:
                maximum = (1 << 64) - 1
                threshold = max_unsigned_input_before_mul_overflow(64, mul)
                first_overflow = threshold + 1
                gcd = math.gcd(mul, div)
                reduced = (mul // gcd, div // gcd)
                response_digits = response.replace("_", "").replace(",", "")

                if re.search(r"(?i)\bu64\s*::\s*max\b", response):
                    if str(maximum) not in response_digits:
                        reasons.append("exact_arithmetic_u64_max_mismatch")

                threshold_windows = re.findall(
                    r"(?is)(?:threshold|limite(?:\s+máximo|\s+maximo)?(?:\s+seguro)?|"
                    r"primeiro\s+(?:valor\s+que\s+)?(?:overflow|estoura)).{0,160}",
                    response,
                )
                for window in threshold_windows:
                    numbers = {
                        int(raw.replace("_", "").replace(",", ""))
                        for raw in re.findall(r"\b\d[\d_,]{8,}\b", window)
                    }
                    if numbers and not ({threshold, first_overflow} & numbers):
                        reasons.append("exact_arithmetic_u64_threshold_mismatch")
                        break

                ratio_claim = re.search(
                    r"(?is)(?:reduz(?:ida|ido|ir)?|razão|razao|ratio).{0,80}"
                    r"(\d[\d_]*)\s*/\s*(\d[\d_]*)",
                    response,
                )
                if ratio_claim:
                    claimed = (
                        int(ratio_claim.group(1).replace("_", "")),
                        int(ratio_claim.group(2).replace("_", "")),
                    )
                    if claimed != reduced:
                        reasons.append("exact_arithmetic_ratio_mismatch")

                if (
                    "i128" not in normalized_context
                    and re.search(
                        r"(?is)(?:domínio|dominio|domain|tipo|opera(?:ção|cao)?|"
                        r"overflow).{0,60}\bi128\b|\bi128\b.{0,60}"
                        r"(?:domínio|dominio|domain|tipo|overflow)",
                        response,
                    )
                ):
                    reasons.append("unobserved_numeric_domain_i128")

                positive_saturation_claim = re.search(
                    r"(?i)\b(?:satura|saturating|saturates)\b", response
                )
                saturation_negated = re.search(
                    r"(?i)(?:não|nao|does\s+not|is\s+not).{0,35}"
                    r"(?:satura|saturating|saturates)",
                    response,
                )
                if (
                    positive_saturation_claim
                    and not saturation_negated
                    and "saturating_" not in normalized_context
                ):
                    reasons.append("unobserved_saturating_semantics")

    profile = select_quantitative_profile(context)
    if profile and profile.name in {"network_signal_physics", "hardware_side_channel"}:
        strong_claim = re.search(
            r"(?i)\b(?:prova|proves?|confirma|confirms?|garante|guarantees?|"
            r"causa|causes?|exploitável|exploitavel|vazamento|leak(?:age)?)\b",
            response,
        )
        if strong_claim:
            mechanism_named = any(
                marker in normalized_response
                for marker in (
                    "mecanismo", "mechanism", "acoplamento", "coupling",
                    "propagação", "propagacao", "propagation", "leakage model",
                )
            )
            measurement_named = any(
                marker in normalized_response
                for marker in (
                    "medição", "medicao", "measurement", "snr", "ruído", "ruido",
                    "noise", "resolução", "resolucao", "resolution", "amostra",
                    "sample", "intervalo", "bound", "limite",
                )
            )
            if not mechanism_named:
                reasons.append("physical_claim_missing_mechanism")
            if not measurement_named:
                reasons.append("physical_claim_missing_measurement_bound")

    return tuple(dict.fromkeys(reasons))


def quantitative_guidance(context: str, max_chars: int = 850) -> str:
    profile = select_quantitative_profile(context)
    if not profile:
        return ""
    checks = "; ".join(profile.checks[:4])
    invariants = "; ".join(profile.invariants[:2])
    guidance = (
        f"QUANTITATIVE REASONING domain={profile.name}: {checks}. Invariants: {invariants}. "
        "Before a numeric/security conclusion, state the numeric domain/representation, units or "
        "base units, bounds, operation order, rounding semantics and the invariant being tested. "
        "For integer a*b/d, derive the exact safe multiplication threshold floor(TYPE_MAX/b), reduce "
        "the rational when possible, and bound floor-rounding loss to <1 base unit per operation. "
        "Decimals define scale only: never invent USD/$/cent tolerances unless observed. Plain Rust "
        "* does not saturate; saturation requires an explicit saturating operation. Keep distinct: "
        "mathematical possibility, input reachability, runtime overflow behavior, and exploitability. "
        "Prefer factual source/input-bound/build-profile inspection over synthetic harnesses when those "
        "facts are unknown. Prefer integers/rationals/fixed-point over binary float for exact value "
        "flows. For nontrivial math show formula -> substitution -> units -> bound/result; distinguish "
        "exact result from approximation. For physical/timing/RF claims require a measurable mechanism, "
        "acquisition conditions and noise/resolution limits. Treat arithmetic anomalies as hypotheses "
        "until the operator supplies reproducible evidence."
    )
    return guidance[:max_chars]
