"""Physical material model and universal material database (SI units).

A ``Material`` is a bundle of physically meaningful properties. Properties that do
not apply to a material (for example Young's modulus of water) are ``None``. Each
property has a declared SI dimension in ``FIELD_DIMS`` and a physical range checked
by ``Material.validate()``.

The built-in database values are representative handbook figures, not certified
data. Each entry cites its origin in ``source`` and states its spread in
``uncertainty``. See ``reality/MATERIAL_DATABASE.md``.

Friction and restitution are deliberately NOT material properties: they depend on the
pair of surfaces in contact and are modelled per contact pair (see PHYSICS_MODELS.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import units as U

# Field -> SI dimension. Used for dimension-checked access via Material.q().
FIELD_DIMS: Dict[str, U.Dim] = {
    "density": U.DENSITY,                              # kg/m^3
    "youngs_modulus": U.PRESSURE,                      # Pa
    "poisson_ratio": U.DIMENSIONLESS,
    "yield_strength": U.PRESSURE,                      # Pa
    "tensile_strength": U.PRESSURE,                    # Pa, nominal (flaw-dependent for brittle solids)
    "fracture_toughness": U.FRACTURE_TOUGHNESS,        # Pa*sqrt(m)
    "specific_heat": U.SPECIFIC_HEAT,                  # J/(kg K)
    "thermal_conductivity": U.THERMAL_CONDUCTIVITY,    # W/(m K)
    "melting_temperature": U.TEMPERATURE,              # K
    "latent_heat_fusion": U.LATENT_HEAT,               # J/kg
    "dynamic_viscosity": U.DYNAMIC_VISCOSITY,          # Pa*s
    "refractive_index": U.DIMENSIONLESS,
    # Electrical conductivity sigma is S/m = A^2 s^3 kg^-1 m^-3 -> exponents (M, L, T, I) = (-1, -3, 3, 2).
    "electrical_conductivity": U.Dim((-1, -3, 3, 2, 0, 0, 0)),
}

PHASES = ("solid", "liquid", "gas", "granular")
BEHAVIORS = ("brittle", "ductile", "elastomer", "fluid", "gas", "granular")


@dataclass
class Material:
    name: str
    category: str
    phase: str
    behavior: str
    density: float                                   # kg/m^3
    specific_heat: float                             # J/(kg K)
    thermal_conductivity: float                      # W/(m K)
    youngs_modulus: Optional[float] = None           # Pa
    poisson_ratio: Optional[float] = None
    yield_strength: Optional[float] = None           # Pa
    tensile_strength: Optional[float] = None         # Pa
    fracture_toughness: Optional[float] = None       # Pa*sqrt(m)
    melting_temperature: Optional[float] = None      # K
    latent_heat_fusion: Optional[float] = None       # J/kg
    dynamic_viscosity: Optional[float] = None        # Pa*s
    refractive_index: Optional[float] = None         # dimensionless, 589 nm unless noted
    electrical_conductivity: Optional[float] = None  # S/m
    source: str = ""
    uncertainty: str = ""
    notes: str = ""

    # ------------------------------------------------------------------ access
    def q(self, field_name: str) -> U.Q:
        """Return a dimensioned quantity for a property. Raises if the property is unset."""
        if field_name not in FIELD_DIMS:
            raise KeyError(f"unknown material property {field_name!r}")
        value = getattr(self, field_name)
        if value is None:
            raise ValueError(f"{self.name} has no value for {field_name!r}")
        return U.Q(float(value), FIELD_DIMS[field_name])

    def has(self, field_name: str) -> bool:
        return getattr(self, field_name) is not None

    # --------------------------------------------------------------- validation
    def validate(self) -> List[str]:
        """Return a list of physical-consistency errors (empty list means valid)."""
        errs: List[str] = []
        if self.phase not in PHASES:
            errs.append(f"phase {self.phase!r} not in {PHASES}")
        if self.behavior not in BEHAVIORS:
            errs.append(f"behavior {self.behavior!r} not in {BEHAVIORS}")
        if not self.density > 0:
            errs.append("density must be > 0")
        if not self.specific_heat > 0:
            errs.append("specific_heat must be > 0")
        if not self.thermal_conductivity > 0:
            errs.append("thermal_conductivity must be > 0")
        if self.youngs_modulus is not None and not self.youngs_modulus > 0:
            errs.append("youngs_modulus must be > 0")
        if self.poisson_ratio is not None and not (-1.0 < self.poisson_ratio < 0.5):
            # Isotropic linear elasticity requires -1 < nu < 0.5 for positive-definite stiffness.
            errs.append("poisson_ratio must lie in (-1, 0.5)")
        if self.yield_strength is not None and not self.yield_strength > 0:
            errs.append("yield_strength must be > 0")
        if self.tensile_strength is not None and not self.tensile_strength > 0:
            errs.append("tensile_strength must be > 0")
        if self.fracture_toughness is not None and not self.fracture_toughness > 0:
            errs.append("fracture_toughness must be > 0")
        if self.melting_temperature is not None and not self.melting_temperature > 0:
            errs.append("melting_temperature must be > 0 K")
        if self.latent_heat_fusion is not None and not self.latent_heat_fusion >= 0:
            errs.append("latent_heat_fusion must be >= 0")
        if self.dynamic_viscosity is not None and not self.dynamic_viscosity > 0:
            errs.append("dynamic_viscosity must be > 0")
        if self.refractive_index is not None and not self.refractive_index >= 1.0:
            errs.append("refractive_index must be >= 1")
        if self.electrical_conductivity is not None and not self.electrical_conductivity >= 0:
            errs.append("electrical_conductivity must be >= 0")
        if self.behavior == "brittle" and self.fracture_toughness is None:
            errs.append("brittle materials must define fracture_toughness")
        if self.behavior == "ductile" and self.yield_strength is None:
            errs.append("ductile materials must define yield_strength")
        if self.behavior == "fluid" and self.dynamic_viscosity is None:
            errs.append("fluids must define dynamic_viscosity")
        if self.phase == "gas" and self.behavior != "gas":
            errs.append("gas phase requires behavior 'gas'")
        if self.phase == "granular" and self.behavior != "granular":
            errs.append("granular phase requires behavior 'granular'")
        if self.phase == "solid" and self.behavior in ("fluid", "gas"):
            errs.append("solid phase cannot have fluid/gas behavior")
        if not self.source:
            errs.append("every material must cite a source")
        return errs


class MaterialDatabase:
    """Registry of materials keyed by lowercase name. Custom materials can be added."""

    def __init__(self) -> None:
        self._materials: Dict[str, Material] = {}

    def add(self, material: Material, *, replace: bool = False) -> Material:
        errs = material.validate()
        if errs:
            raise ValueError(f"invalid material {material.name!r}: " + "; ".join(errs))
        key = material.name.lower()
        if key in self._materials and not replace:
            raise KeyError(f"material {material.name!r} already exists (use replace=True)")
        self._materials[key] = material
        return material

    def get(self, name: str) -> Material:
        key = name.lower()
        if key not in self._materials:
            raise KeyError(f"unknown material {name!r}; known: {sorted(self._materials)}")
        return self._materials[key]

    def names(self) -> List[str]:
        return sorted(self._materials)

    def __contains__(self, name: str) -> bool:
        return name.lower() in self._materials

    def __len__(self) -> int:
        return len(self._materials)

    def __iter__(self):
        return iter(self._materials[k] for k in sorted(self._materials))


def _builtin_materials() -> List[Material]:
    H = "CRC Handbook of Chemistry and Physics (typical room-temperature values)"
    return [
        Material(
            name="water", category="fluid", phase="liquid", behavior="fluid",
            density=998.2, specific_heat=4182.0, thermal_conductivity=0.598,
            dynamic_viscosity=1.002e-3, melting_temperature=273.15,
            latent_heat_fusion=333.55e3, refractive_index=1.333,
            source="IAPWS R6-95 (2018 release) for properties at 20 degC; CRC Handbook for refractive index at 589 nm",
            uncertainty="density and cp within ~0.1 %; viscosity ~1 %; n within ~0.001",
        ),
        Material(
            name="air", category="gas", phase="gas", behavior="gas",
            density=1.204, specific_heat=1005.0, thermal_conductivity=0.0257,
            dynamic_viscosity=1.81e-5, refractive_index=1.000293,
            source="US Standard Atmosphere 1976 / Incropera et al., Table A.4 (20 degC, 1 atm)",
            uncertainty="density depends on T, p, humidity; use gas law for other conditions",
        ),
        Material(
            name="iron", category="metal", phase="solid", behavior="ductile",
            density=7874.0, youngs_modulus=211e9, poisson_ratio=0.29,
            yield_strength=100e6, tensile_strength=210e6,
            specific_heat=449.0, thermal_conductivity=80.4,
            melting_temperature=1811.0, latent_heat_fusion=247e3,
            electrical_conductivity=1.0e7,
            source=H + "; Ashby & Jones, Engineering Materials 1",
            uncertainty="yield strength of pure annealed iron varies ~50-150 MPa with purity and grain size",
        ),
        Material(
            name="steel", category="metal", phase="solid", behavior="ductile",
            density=7850.0, youngs_modulus=200e9, poisson_ratio=0.29,
            yield_strength=370e6, tensile_strength=440e6,
            specific_heat=486.0, thermal_conductivity=51.9,
            melting_temperature=1760.0, latent_heat_fusion=270e3,
            electrical_conductivity=6.99e6,
            source="Low-carbon structural steel (AISI 1018-class) typical values; ASM Handbook Vol. 1; Incropera Table A.1",
            uncertainty="yield 250-550 MPa depending on grade and heat treatment",
            notes="Representative of carbon steel; alloy grades must be entered explicitly.",
        ),
        Material(
            name="aluminum", category="metal", phase="solid", behavior="ductile",
            density=2700.0, youngs_modulus=68.9e9, poisson_ratio=0.33,
            yield_strength=276e6, tensile_strength=310e6,
            specific_heat=896.0, thermal_conductivity=167.0,
            melting_temperature=855.0, latent_heat_fusion=397e3,
            electrical_conductivity=3.77e7,
            source="Aluminum 6061-T6 typical values; ASM Handbook Vol. 2; Incropera Table A.1",
            uncertainty="temper-dependent; yield 240-300 MPa for T6 variants",
        ),
        Material(
            name="copper", category="metal", phase="solid", behavior="ductile",
            density=8960.0, youngs_modulus=117e9, poisson_ratio=0.34,
            yield_strength=70e6, tensile_strength=220e6,
            specific_heat=385.0, thermal_conductivity=401.0,
            melting_temperature=1358.0, latent_heat_fusion=205e3,
            electrical_conductivity=5.96e7,
            source=H + "; Incropera Table A.1 (annealed C11000)",
            uncertainty="E 110-130 GPa depending on orientation; yield 33-70 MPa annealed vs cold-worked",
        ),
        Material(
            name="gold", category="metal", phase="solid", behavior="ductile",
            density=19320.0, youngs_modulus=79e9, poisson_ratio=0.44,
            yield_strength=100e6, tensile_strength=120e6,
            specific_heat=129.0, thermal_conductivity=318.0,
            melting_temperature=1337.33, latent_heat_fusion=64.4e3,
            electrical_conductivity=4.10e7,
            source=H,
            uncertainty="yield strength highly processing dependent (annealed ~30-100 MPa); treat as indicative",
        ),
        Material(
            name="silver", category="metal", phase="solid", behavior="ductile",
            density=10490.0, youngs_modulus=83e9, poisson_ratio=0.37,
            yield_strength=50e6, tensile_strength=140e6,
            specific_heat=235.0, thermal_conductivity=429.0,
            melting_temperature=1234.93, latent_heat_fusion=104.6e3,
            electrical_conductivity=6.30e7,
            source=H,
            uncertainty="yield strength processing dependent; indicative only",
        ),
        Material(
            name="diamond", category="ceramic", phase="solid", behavior="brittle",
            density=3510.0, youngs_modulus=1140e9, poisson_ratio=0.10,
            fracture_toughness=3.4e6, tensile_strength=1.0e9,
            specific_heat=509.0, thermal_conductivity=2000.0,
            refractive_index=2.417,
            source="Natural/synthetic diamond; Field, The Properties of Natural and Synthetic Diamond (1992); CRC Handbook",
            uncertainty="E 1050-1220 GPa; K_Ic 3-5 MPa*sqrt(m); tensile strength is flaw-dependent (very high for pristine stones)",
        ),
        Material(
            name="glass", category="glass", phase="solid", behavior="brittle",
            density=2500.0, youngs_modulus=72e9, poisson_ratio=0.20,
            fracture_toughness=0.75e6, tensile_strength=45e6,
            specific_heat=840.0, thermal_conductivity=1.0,
            refractive_index=1.52,
            source="SODA-LIME glass (not BK7). K_Ic 0.75 MPa*sqrt(m) and nu 0.20 (DTIC ARL-TR-8187 as cited by Saiwei Glass); "
                   "E 70-73 GPa (fabdigit.com ~72, Saiwei Glass 73, industrialengineeringstudio 70); density 2500 kg/m^3 "
                   "(industrialengineeringstudio); n ~1.52 is a textbook value, not checked in Phase 1",
            uncertainty="practical annealed tensile strength 30-50 MPa is flaw-limited; K_Ic 0.7-0.8 MPa*sqrt(m). "
                        "Schott N-BK7 (E 82 GPa, nu 0.21, density 2510 kg/m^3) is a different glass and is not used here",
            notes="Glass has no sharp melting point; softening occurs over ~700-730 C.",
        ),
        Material(
            name="wood", category="wood", phase="solid", behavior="brittle",
            density=500.0, youngs_modulus=10e9, poisson_ratio=0.35,
            fracture_toughness=0.4e6, tensile_strength=60e6,
            specific_heat=1700.0, thermal_conductivity=0.12,
            source="Softwood (pine-class), dry, along-grain, isotropic approximation; Wood Handbook (USDA FPL-GTR-190)",
            uncertainty="wood is orthotropic; along-grain E ~9-13 GPa, across-grain ~0.5-1 GPa; density 350-600 kg/m^3",
            notes="Isotropic approximation: results are only indicative for along-grain loading.",
        ),
        Material(
            name="concrete", category="ceramic", phase="solid", behavior="brittle",
            density=2350.0, youngs_modulus=30e9, poisson_ratio=0.20,
            fracture_toughness=1.0e6, tensile_strength=3.0e6,
            specific_heat=880.0, thermal_conductivity=1.7,
            source="Normal-weight structural concrete; Mindess, Young & Darwin, Concrete (2nd ed.); ACI 318 typical values",
            uncertainty="E 20-40 GPa, K_Ic 0.6-1.4 MPa*sqrt(m) depending on mix and age",
        ),
        Material(
            name="rubber", category="polymer", phase="solid", behavior="elastomer",
            density=1100.0, youngs_modulus=5e6, poisson_ratio=0.499,
            tensile_strength=25e6,
            specific_heat=1900.0, thermal_conductivity=0.14,
            source="Natural rubber vulcanizate, small-strain values; Treloar, The Physics of Rubber Elasticity (1975)",
            uncertainty="strongly nonlinear hyperelastic; E is a small-strain secant only; linear model invalid beyond ~10 % strain",
            notes="Use a hyperelastic model (Neo-Hookean/Mooney-Rivlin) for large strains; not implemented yet.",
        ),
        Material(
            name="plastic_hdpe", category="polymer", phase="solid", behavior="ductile",
            density=950.0, youngs_modulus=0.8e9, poisson_ratio=0.42,
            yield_strength=26e6, tensile_strength=30e6,
            specific_heat=2300.0, thermal_conductivity=0.45,
            melting_temperature=408.0, latent_heat_fusion=210e3,
            source="High-density polyethylene; Callister, Materials Science and Engineering; Brandrup et al., Polymer Handbook",
            uncertainty="E 0.8-1.1 GPa; yield 20-30 MPa; heat of fusion depends on crystallinity (200-290 kJ/kg)",
        ),
        Material(
            name="sand", category="granular", phase="granular", behavior="granular",
            density=1600.0, specific_heat=800.0, thermal_conductivity=0.3,
            source="Dry quartz sand, bulk density; Lambe & Whitman, Soil Mechanics; Incropera-class conductivity",
            uncertainty="bulk density 1450-1700 kg/m^3; not a linear elastic solid, so no Young's modulus is assigned",
            notes="Granular media require a contact/Mohr-Coulomb or DEM model; this entry is for thermal and mass only.",
        ),
        Material(
            name="soil", category="granular", phase="granular", behavior="granular",
            density=1300.0, specific_heat=800.0, thermal_conductivity=0.25,
            source="Generic dry loam, bulk values; Lambe & Whitman, Soil Mechanics",
            uncertainty="bulk density 1100-1600 kg/m^3; strongly moisture dependent",
            notes="Generic placeholder class of soils; site-specific data required for engineering use.",
        ),
        Material(
            name="ice", category="ice", phase="solid", behavior="brittle",
            density=917.0, youngs_modulus=9.5e9, poisson_ratio=0.33,
            fracture_toughness=0.15e6, tensile_strength=1.0e6,
            specific_heat=2100.0, thermal_conductivity=2.2,
            melting_temperature=273.15, latent_heat_fusion=333.55e3,
            source="Ice Ih at 0 degC; Petrenko & Whitworth, Physics of Ice (1999); IAPWS R6-95 for latent heat",
            uncertainty="ice is rate- and temperature-dependent (creeps); K_Ic and tensile values indicative",
        ),
        Material(
            name="cortical_bone", category="biological", phase="solid", behavior="brittle",
            density=1900.0, youngs_modulus=17e9, poisson_ratio=0.30,
            fracture_toughness=3.0e6, tensile_strength=110e6,
            specific_heat=1300.0, thermal_conductivity=0.5,
            source="Human cortical bone, longitudinal; Currey, Bones: Structure and Mechanics (2002); Cowin (ed.), Bone Mechanics Handbook",
            uncertainty="E 12-20 GPa; K_Ic 2-5 MPa*sqrt(m); strongly age and site dependent; quasi-brittle",
            notes="Biological tissue: values are population averages, not a validated patient model.",
        ),
    ]


def default_database() -> MaterialDatabase:
    """Build a database populated with the built-in validated materials."""
    db = MaterialDatabase()
    for m in _builtin_materials():
        db.add(m)
    return db
