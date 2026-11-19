import pytest

from reality import units as U


def test_dimension_algebra_basic():
    assert U.VELOCITY / U.TIME == U.ACCELERATION
    assert U.FORCE == U.MASS * U.ACCELERATION
    assert U.ENERGY == U.FORCE * U.LENGTH
    assert U.PRESSURE == U.FORCE / U.AREA


def test_fracture_toughness_is_pa_sqrt_m():
    # Pa * m^(1/2) = M L^(-1/2) T^(-2)
    expected = U.Dim((1, -0.5, -2, 0, 0, 0, 0))
    assert U.FRACTURE_TOUGHNESS == expected


def test_quantity_add_requires_same_dimension():
    a = U.Q(1.0, U.LENGTH)
    b = U.Q(2.0, U.TIME)
    with pytest.raises(U.DimensionError):
        _ = a + b
    assert (a + U.Q(2.0, U.LENGTH)).value == 3.0


def test_quantity_multiplication_combines_dimensions():
    v = U.Q(10.0, U.LENGTH) / U.Q(2.0, U.TIME)
    assert v.dim == U.VELOCITY and v.value == 5.0


def test_require_dim_rejects_wrong_dimension():
    with pytest.raises(U.DimensionError):
        U.require_dim(U.Q(1.0, U.LENGTH), U.MASS, "mass")
    with pytest.raises(U.DimensionError):
        U.require_dim(1.0, U.MASS, "mass")  # bare float is not dimensioned


def test_dimensionless_and_str():
    assert (U.LENGTH / U.LENGTH).is_dimensionless
    assert str(U.FORCE) == "M L T^-2"
    assert str(U.DIMENSIONLESS) == "1"


def test_check_finite():
    U.check_finite([1.0, 2.0])
    with pytest.raises(ValueError):
        U.check_finite([1.0, float("nan")])
