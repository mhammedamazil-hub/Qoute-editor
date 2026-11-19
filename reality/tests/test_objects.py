"""Phase 2: physical object model (mass, centre of mass, inertia, thermal and translational state)."""

import math

import pytest

from reality import constants as C
from reality import units as U
from reality.materials import Material, default_database
from reality.objects import Box, Cylinder, PhysicalObject, Sphere

DB = default_database()


def _mat(density=1000.0, **kw):
    base = dict(name="m", category="test", phase="solid", behavior="brittle", density=density,
                specific_heat=1000.0, thermal_conductivity=1.0, fracture_toughness=1e6,
                source="test fixture", uncertainty="none")
    base.update(kw)
    return Material(**base)


# ------------------------------------------------------------- geometry and mass
def test_sphere_mass_and_volume():
    obj = PhysicalObject("s", Sphere(0.5), _mat(1000.0))
    assert obj.volume().value == pytest.approx(4.0 / 3.0 * math.pi * 0.125)
    assert obj.mass().value == pytest.approx(1000.0 * 4.0 / 3.0 * math.pi * 0.125)


def test_cube_inertia_is_isotropic():
    obj = PhysicalObject("c", Box((0.3, 0.3, 0.3)), _mat(500.0))
    ix, iy, iz = (q.value for q in obj.principal_inertia())
    assert ix == pytest.approx(iy) == pytest.approx(iz)


def test_principal_inertia_independent_of_position_and_velocity():
    a = PhysicalObject("a", Box((1, 2, 3)), _mat(), position=(0, 0, 0))
    b = PhysicalObject("b", Box((1, 2, 3)), _mat(), position=(10, -4, 2), velocity=(1, 2, 3))
    assert [q.value for q in a.principal_inertia()] == [q.value for q in b.principal_inertia()]


def test_centre_of_mass_is_geometric_centre_for_uniform_density():
    assert PhysicalObject("c", Cylinder(0.1, 0.4), _mat()).centre_of_mass() == (0.0, 0.0, 0.0)


def test_parallel_axis_tensor_is_symmetric_and_trace_consistent():
    obj = PhysicalObject("b", Box((0.2, 0.4, 0.6)), _mat(2000.0))
    d = (0.3, -0.1, 0.2)
    tensor = obj.inertia_about_point(d)
    vals = [[tensor[i][j].value for j in range(3)] for i in range(3)]
    for i in range(3):
        for j in range(3):
            assert vals[i][j] == pytest.approx(vals[j][i])
    # trace(I') = trace(I_cm) + 2 m |d|^2
    m = obj.mass().value
    trace_cm = sum(q.value for q in obj.principal_inertia())
    assert sum(vals[i][i] for i in range(3)) == pytest.approx(trace_cm + 2.0 * m * sum(x * x for x in d))


def test_parallel_axis_zero_offset_returns_centroidal_tensor():
    obj = PhysicalObject("s", Sphere(0.2), _mat(800.0))
    tensor = obj.inertia_about_point((0.0, 0.0, 0.0))
    diag = [tensor[i][i].value for i in range(3)]
    assert diag == pytest.approx([q.value for q in obj.principal_inertia()])
    assert tensor[0][1].value == 0.0


# ----------------------------------------------------------- dimensions and values
def test_quantities_carry_si_dimensions():
    obj = PhysicalObject("o", Sphere(0.1), _mat(), temperature=300.0, velocity=(1.0, 0.0, 0.0))
    assert obj.mass().dim == U.MASS
    assert obj.volume().dim == U.VOLUME
    assert obj.principal_inertia()[0].dim == U.MOMENT_OF_INERTIA
    assert obj.weight().dim == U.FORCE
    assert obj.kinetic_energy().dim == U.ENERGY
    assert obj.heat_capacity().dim == U.ENERGY / U.TEMPERATURE


def test_adding_mass_and_volume_is_a_dimension_error():
    obj = PhysicalObject("o", Sphere(0.1), _mat())
    with pytest.raises(U.DimensionError):
        _ = obj.mass() + obj.volume()


def test_weight_uses_standard_gravity_by_default():
    obj = PhysicalObject("o", Box((1, 1, 1)), _mat(917.0))
    assert obj.weight().value == pytest.approx(917.0 * C.STANDARD_GRAVITY)
    assert obj.weight(1.62).value == pytest.approx(917.0 * 1.62)


def test_kinetic_energy_and_heat_capacity():
    obj = PhysicalObject("o", Box((1, 1, 1)), _mat(2.0), velocity=(3.0, 4.0, 0.0))
    assert obj.kinetic_energy().value == pytest.approx(0.5 * 2.0 * 25.0)
    assert obj.heat_capacity().value == pytest.approx(2.0 * 1000.0)


def test_melting_state_against_material_melting_point():
    ice = DB.get("ice")
    assert PhysicalObject("i", Box((1, 1, 1)), ice, temperature=280.0).above_melting_point() is True
    assert PhysicalObject("i", Box((1, 1, 1)), ice, temperature=260.0).above_melting_point() is False
    assert PhysicalObject("g", Box((1, 1, 1)), DB.get("glass")).above_melting_point() is None


# ------------------------------------------------------------------ rejection
@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_sphere_radius_is_rejected(bad):
    with pytest.raises(ValueError):
        Sphere(bad)


def test_invalid_box_and_cylinder_dimensions_are_rejected():
    with pytest.raises(ValueError):
        Box((1.0, 1.0))
    with pytest.raises(ValueError):
        Box((1.0, -1.0, 1.0))
    with pytest.raises(ValueError):
        Cylinder(0.1, 0.0)


def test_non_positive_temperature_is_rejected():
    with pytest.raises(ValueError):
        PhysicalObject("o", Sphere(0.1), _mat(), temperature=0.0)


def test_wrong_length_position_or_velocity_is_rejected():
    with pytest.raises(ValueError):
        PhysicalObject("o", Sphere(0.1), _mat(), position=(0.0, 0.0))
    with pytest.raises(ValueError):
        PhysicalObject("o", Sphere(0.1), _mat(), velocity=(1.0, 2.0, 3.0, 4.0))


def test_invalid_material_makes_object_invalid():
    with pytest.raises(ValueError):
        PhysicalObject("o", Sphere(0.1), _mat(density=-5.0))


def test_validate_returns_errors_without_raising_for_bad_temperature():
    obj = PhysicalObject("o", Sphere(0.1), _mat())
    obj.temperature = -3.0
    assert obj.validate() and "temperature" in obj.validate()[0]
