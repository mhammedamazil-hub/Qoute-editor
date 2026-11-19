"""Physical constants and reference data, each with its origin.

Nothing in this module is a tuning parameter. Every value cites a source so the
provenance can be audited (PROJECT REALITY rule: never use undocumented constants).
Values marked "approximate" carry the uncertainty stated next to them.
"""

# --- Exact SI-defined constants (BIPM SI Brochure, 9th ed., 2019) -------------
R_GAS = 8.314462618            # J/(mol K), molar gas constant (exact in SI 2019)
SIGMA_SB = 5.670374419e-8      # W/(m^2 K^4), Stefan-Boltzmann constant (exact in SI 2019)
STANDARD_GRAVITY = 9.80665     # m/s^2, standard gravity g0 (3rd CGPM 1901, exact)
ZERO_CELSIUS_K = 273.15        # K, offset between Celsius and kelvin (exact)

# --- CODATA 2018 (Tiesinga et al., Rev. Mod. Phys. 93, 025010, 2021) ----------
G_NEWTON = 6.67430e-11         # m^3/(kg s^2), relative standard uncertainty 2.2e-5

# --- Gravitational parameters GM and mean radii ---------------------------------
GM_EARTH = 3.986004418e14      # m^3/s^2 (IERS Conventions 2010, TN36)
R_EARTH_MEAN = 6.371008771e6   # m (IAU 2015 nominal mean Earth radius)
GM_MOON = 4.9028e12            # m^3/s^2 (approximate, ~1e-4 relative uncertainty)
R_MOON_MEAN = 1.7374e6         # m (mean radius)
GM_MARS = 4.282837e13          # m^3/s^2 (approximate, ~1e-4 relative uncertainty)
R_MARS_MEAN = 3.3895e6         # m (mean radius)

# --- Air and sound (US Standard Atmosphere 1976; Kinsler et al., Fundamentals of Acoustics) ---
M_AIR = 0.0289647              # kg/mol, dry air molar mass
GAMMA_AIR = 1.4                # ratio of specific heats, diatomic ideal gas near room temperature
P_REF_AIR_SOUND = 20e-6        # Pa, reference pressure for sound pressure level (ISO 1683)
P_ATM = 101325.0               # Pa, standard atmosphere

# --- Water (IAPWS R6-95 and CRC Handbook) ---------------------------------------
LATENT_HEAT_FUSION_WATER = 333.55e3   # J/kg at 0 degC
CP_WATER_NEAR_20C = 4182.0            # J/(kg K) near 20 degC
C_WATER_DEFAULT = 4186.0              # J/(kg K), thermochemical-calorie convention (CRC)

# --- Refractive index of air (approximate, 550 nm, STP) -------------------------
N_AIR_550NM = 1.000293

# --- Schott BK7 Sellmeier coefficients (Schott optical glass datasheet) --------
# n^2(lambda) - 1 = sum_i B_i lambda^2 / (lambda^2 - C_i), lambda in micrometres.
BK7_B = (1.03961212, 0.231792344, 1.01046945)
BK7_C = (0.00600069867, 0.0200179144, 103.560653)  # um^2
