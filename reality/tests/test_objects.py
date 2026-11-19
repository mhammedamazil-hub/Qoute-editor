"""Phase 2 unit tests: rigid uniform-density objects (objects.py)."""

import math

import pytest

from reality import constants as C
from reality import objects as O
from reality.materials import default_database

DB = default_database()


def _mat(name):
    return DB.get(name)


def test_sphere_mass_and_volume():
    obj = O.PhysicalObject("ball", O.Sphere(0.1), _mat("ice"))
    assert obj.volume().value == pytest.approx(4.0 / 3.0 * math.pi * 1e-3, rel=1e-14)
    assert obj.mass().value == pytest.approx(917.0 * 4.0 / 3.0 * math.pi * 1e-3, rel=1e-14)


def test_principal_inertia_sphere_is_isotropic():
    obj = O.PhysicalObject("ball", O.Sphere(0.2), _mat("steel"))
    ix, iy, iz = (q.value for q in obj.principal_inertia())
    assert ix == pytest.approx(iy) == pytest.approx(iz)
    assert ix == pytest.approx(0.4 * obj.mass().value * 0.04, rel=1e-14)


def test_inertia_about_origin_equals_principal_inertia():
    obj = O.PhysicalObject("box", O.Box((0.2, 0.4, 0.6)), _mat("concrete"))
    tensor = obj.inertia_about_point((0.0, 0.0, 0.0))
    principal = [q.value for q in obj.principal_inertia()]
    for i in range(3):
        assert tensor[i][i].value == pytest.approx(principal[i], rel=1e-14)
        for j in range(3):
            if i != j:
                assert tensor[i][j].value == pytest.approx(0.0, abs=1e-18)


def test_parallel_axis_about_surface_point_of_sphere():
    # I about a point on the surface, along a diameter-perpendicular axis: m(2/5 R^2 + R^2)
    r = 0.1
    obj = O.PhysicalObject("ball", O.Sphere(r), _mat("steel"))
    tensor = obj.inertia_about_point((r, 0.0, 0.0))
    m = obj.mass().value
    assert tensor[1][1].value == pytest.approx(m * (0.4 + 1.0) * r * r, rel=1e-12)
    assert tensor[0][0].value == pytest.approx(m * 0.4 * r * r, rel=1e-12)  # axis through the point


def test_weight_and_kinetic_energy():
    obj = O.PhysicalObject("block", O.Box((1.0, 1.0, 1.0)), _mat("ice"), velocity=(3.0, 0.0, 4.0))
    assert obj.weight().value == pytest.approx(917.0 * C.STANDARD_GRAVITY, rel=1e-14)
    assert obj.kinetic_energy().value == pytest.approx(0.5 * 917.0 * 25.0, rel=1e-14)


def test_heat_capacity_uses_specific_heat():
    obj = O.PhysicalObject("cube", O.Box((0.1, 0.1, 0.1)), _mat("water"))
    assert obj.heat_capacity().value == pytest.approx(
        _mat("water").density * 1e-3 * _mat("water").specific_heat, rel=1e-14)


def test_above_melting_point_returns_none_without_stored_melting_point():
    from reality.materials import Material
    no_melt = Material(name="test-no-melt", category="test", phase="solid", behavior="ductile", yield_strength=1e8,
                       density=1000.0, specific_heat=1000.0, thermal_conductivity=1.0,
                       source="test fixture", uncertainty="none")
    obj = O.PhysicalObject("block", O.Box((0.1, 0.1, 0.1)), no_melt, temperature=1000.0)
    assert obj.above_melting_point() is None


def test_above_melting_point_true_and_false_for_ice():
    melt = _mat("ice").melting_temperature
    assert melt is not None
    hot = O.PhysicalObject("ice", O.Box((0.1, 0.1, 0.1)), _mat("ice"), temperature=melt + 5.0)
    cold = O.PhysicalObject("ice", O.Box((0.1, 0.1, 0.1)), _mat("ice"), temperature=melt - 5.0)
    assert hot.above_melting_point() is True
    assert cold.above_melting_point() is False


def test_cylinder_axial_and_transverse_inertia():
    r, h = 0.05, 0.3
    obj = O.PhysicalObject("rod", O.Cylinder(r, h), _mat("steel"))
    m = obj.mass().value
    ix, iy, iz = (q.value for q in obj.principal_inertia())
    assert ix == pytest.approx(m * (3 * r * r + h * h) / 12.0, rel=1e-14)
    assert iz == pytest.approx(m * r * r / 2.0, rel=1e-14)
    assert ix == pytest.approx(iy)


@pytest.mark.parametrize("bad", [
    lambda: O.Sphere(0.0),
    lambda: O.Sphere(-1.0),
    lambda: O.Sphere(float("nan")),
    lambda: O.Box((1.0, 0.0, 1.0)),
    lambda: O.Box((1.0, 1.0)),
    lambda: O.Cylinder(0.1, -0.2),
])
def test_shape_dimension_errors(bad):
    with pytest.raises(ValueError):
        bad()


def test_object_rejects_bad_temperature_and_material():
    with pytest.raises(ValueError):
        O.PhysicalObject("x", O.Sphere(0.1), _mat("steel"), temperature=0.0)
    with pytest.raises(ValueError):
        O.PhysicalObject("x", O.Sphere(0.1), _mat("steel"), temperature=float("inf"))


def test_object_rejects_bad_vector_inputs():
    with pytest.raises(ValueError):
        O.PhysicalObject("x", O.Sphere(0.1), _mat("steel"), position=(0.0, 1.0))
    with pytest.raises(ValueError):
        O.PhysicalObject("x", O.Sphere(0.1), _mat("steel"), velocity=(0.0, float("nan"), 0.0))
