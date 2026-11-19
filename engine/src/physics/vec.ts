// Small vector and quaternion helpers. Plain tuples, no classes, no hidden allocation beyond the returned tuple.

export type Vec3 = [number, number, number];
/** Quaternion as [w, x, y, z], same convention as reality.rigidbody. */
export type Quat = [number, number, number, number];
/** Row-major 3x3 matrix: m[row][col]. */
export type Mat3 = [Vec3, Vec3, Vec3];

export const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const scale = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
export const norm = (a: Vec3): number => Math.sqrt(dot(a, a));

export const matVec = (m: Mat3, v: Vec3): Vec3 => [
  m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
  m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
  m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
];

export const matTranspose = (m: Mat3): Mat3 => [
  [m[0][0], m[1][0], m[2][0]],
  [m[0][1], m[1][1], m[2][1]],
  [m[0][2], m[1][2], m[2][2]],
];

export function quatMul(a: Quat, b: Quat): Quat {
  const [w1, x1, y1, z1] = a;
  const [w2, x2, y2, z2] = b;
  return [
    w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
    w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
    w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
  ];
}

export function quatNormalize(q: Quat): Quat {
  const n = Math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
  if (!(n > 0) || !Number.isFinite(n)) throw new Error("cannot normalise a zero or non-finite quaternion");
  return [q[0] / n, q[1] / n, q[2] / n, q[3] / n];
}

/** Rotation matrix R with world = R * body. */
export function quatToMatrix(q: Quat): Mat3 {
  const [w, x, y, z] = q;
  return [
    [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
    [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
    [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
  ];
}

/** Exact rotation over time h for a constant body-frame angular velocity (reality.rigidbody.quat_rotation_increment). */
export function quatRotationIncrement(omegaBody: Vec3, h: number): Quat {
  const wn = norm(omegaBody);
  if (wn === 0) return [1, 0, 0, 0];
  const half = 0.5 * wn * h;
  const s = Math.sin(half) / wn;
  return [Math.cos(half), omegaBody[0] * s, omegaBody[1] * s, omegaBody[2] * s];
}
