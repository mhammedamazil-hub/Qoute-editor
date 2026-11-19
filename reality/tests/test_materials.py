import pytest

from reality import units as U
from reality.materials import FIELD_DIMS, Material, MaterialDatabase, default_database

REQUIRED_MATERIALS = {
    "water", "air", "iron", "steel", "aluminum", "copper", "gold", "silver", "diamond",
    "glass", "wood", "concrete", "rubber", "plastic_hdpe", "sand", "soil", "ice", "cortical_bone",
}


def test_database_contains_all_required_materials():
    db = default_database()
    missing = REQUIRED_MATERIALS - set(db.names())
    assert not missing, f"missing materials: {missing}"


def test_all_builtin_materials_validate():
    for m in default_database():
        assert m.validate() == [], m.name


def test_every_builtin_material_cites_a_source():
    for m in default_database():
        assert m.source, m.name
        assert m.uncertainty, f"{m.name} must state its uncertainty"


def test_glass_is_brittle_and_steel_is_ductile():
    db = default_database()
    assert db.get("glass").behavior == "brittle"
    assert db.get("steel").behavior == "ductile"
    assert db.get("glass").fracture_toughness is not None
    assert db.get("steel").yield_strength is not None


def test_property_dimensions_are_bound():
    glass = default_database().get("glass")
    assert glass.q("youngs_modulus").dim == U.PRESSURE
    assert glass.q("density").dim == U.DENSITY
    assert glass.q("fracture_toughness").dim == U.FRACTURE_TOUGHNESS
    assert set(FIELD_DIMS) >= {"density", "youngs_modulus", "fracture_toughness", "specific_heat"}


def test_unset_property_raises():
    water = default_database().get("water")
    with pytest.raises(ValueError):
        water.q("youngs_modulus")
    with pytest.raises(KeyError):
        water.q("not_a_property")


def test_custom_material_can_be_registered_and_is_validated():
    db = MaterialDatabase()
    m = Material(name="my_alloy", category="metal", phase="solid", behavior="ductile",
                 density=7000.0, specific_heat=500.0, thermal_conductivity=30.0,
                 youngs_modulus=150e9, poisson_ratio=0.3, yield_strength=400e6,
                 source="test")
    db.add(m)
    assert "MY_ALLOY" in db
    assert db.get("my_alloy").density == 7000.0


def test_invalid_material_is_rejected():
    db = MaterialDatabase()
    bad = Material(name="bad", category="metal", phase="solid", behavior="ductile",
                   density=-1.0, specific_heat=500.0, thermal_conductivity=30.0,
                   poisson_ratio=0.7, yield_strength=None, source="x")
    with pytest.raises(ValueError) as exc:
        db.add(bad)
    assert "density" in str(exc.value) and "poisson_ratio" in str(exc.value)


def test_brittle_without_toughness_is_invalid():
    m = Material(name="b", category="glass", phase="solid", behavior="brittle",
                 density=2500, specific_heat=800, thermal_conductivity=1.0, source="x")
    assert any("fracture_toughness" in e for e in m.validate())


def test_duplicate_requires_replace():
    db = MaterialDatabase()
    m = Material(name="x", category="metal", phase="solid", behavior="ductile",
                 density=1000, specific_heat=100, thermal_conductivity=1, yield_strength=1e6, source="s")
    db.add(m)
    with pytest.raises(KeyError):
        db.add(m)
    db.add(m, replace=True)


def test_unknown_material_lookup_lists_known_names():
    with pytest.raises(KeyError) as exc:
        default_database().get("unobtainium")
    assert "glass" in str(exc.value)


def test_glass_row_is_soda_lime_and_not_bk7():
    # Phase 1 reconciliation: the `glass` row is soda-lime; BK7 has different constants.
    from reality import constants as C

    glass = default_database().get("glass")
    assert "SODA-LIME" in glass.source
    assert glass.youngs_modulus != pytest.approx(C.BK7_YOUNGS_MODULUS)
    assert glass.poisson_ratio != pytest.approx(C.BK7_POISSON_RATIO)
    assert glass.density != pytest.approx(C.BK7_DENSITY)
    assert 70e9 <= glass.youngs_modulus <= 73e9
