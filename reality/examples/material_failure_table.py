"""Demonstrator: the same load gives different outcomes for different materials.

For each brittle or ductile solid in the database, this prints the failure assessment for a
given uniaxial tensile stress and an assumed internal flaw. Brittle solids are judged by
linear-elastic fracture mechanics (K_I >= K_Ic); ductile metals by yield.

Run from the repository root:
    PYTHONPATH=reality/src python reality/examples/material_failure_table.py
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from reality import fracture  # noqa: E402
from reality.materials import default_database  # noqa: E402

APPLIED_STRESS = 100e6     # Pa, uniaxial tension (e.g. a bending or impact-induced stress)
FLAW_HALF_LENGTH = 0.1e-3  # m, an assumed 0.2 mm internal flaw (brittle solids only)


def main() -> None:
    db = default_database()
    print(f"Applied tensile stress: {APPLIED_STRESS / 1e6:.0f} MPa; flaw half-length: {FLAW_HALF_LENGTH * 1e3:.2f} mm\n")
    print(f"{'material':<14}{'behavior':<10}{'K_Ic (MPa√m)':>14}{'sigma_c (MPa)':>15}{'sigma_y (MPa)':>15}{'mode':>10}{'failed':>8}")
    for m in db:
        if m.behavior not in ("brittle", "ductile"):
            continue
        a = fracture.assess(m, APPLIED_STRESS, FLAW_HALF_LENGTH)
        kic = f"{m.fracture_toughness / 1e6:.2f}" if m.fracture_toughness else "-"
        sc = f"{a.critical_stress_flaw / 1e6:.1f}" if a.critical_stress_flaw else "-"
        sy = f"{a.yield_strength / 1e6:.0f}" if a.yield_strength else "-"
        print(f"{m.name:<14}{m.behavior:<10}{kic:>14}{sc:>15}{sy:>15}{a.mode:>10}{str(a.failed):>8}")


if __name__ == "__main__":
    main()
