// Sphere-on-planes contact stepper: a TypeScript port of reality.contact.step_sphere (Python kernel).
//
// Same algorithm, same order of operations: predict, detect from predicted gaps, impulse per touching plane
// (normal then Coulomb friction with sticking/sliding cone), move, project out residual penetration, rotate.
// For a solid sphere the inertia is isotropic (I = 2/5 m R^2), so the inverse inertia is a scalar and the
// world-frame inverse inertia is that scalar times the identity. The Python code uses the same closed forms.
//
// The kernel is the reference. tests/reference.test.ts checks this file against recorded Python trajectories.

import {
  Mat3, Quat, Vec3, add, cross, dot, matTranspose, matVec, norm, quatMul, quatNormalize, quatRotationIncrement,
  quatToMatrix, scale, sub,
} from "./vec";

export const CONTACT_TOLERANCE = 1e-9; // m; gaps below this count as touching (same as the kernel)

export interface Plane {
  /** Unit normal; the free side is n . x > offset. */
  readonly normal: Vec3;
  readonly offset: number;
}

export function makePlane(normal: Vec3, offset: number): Plane {
  const n = norm(normal);
  if (!(Number.isFinite(n) && n > 0)) throw new Error("plane normal must be finite and non-zero");
  return { normal: scale(normal, 1 / n), offset };
}

export interface SphereState {
  readonly mass: number;     // kg
  readonly radius: number;   // m
  position: Vec3;            // m, world frame
  velocity: Vec3;            // m/s, world frame
  quaternion: Quat;          // body -> world
  omegaBody: Vec3;           // rad/s, body frame
}

export interface ContactParams {
  readonly friction: number;     // Coulomb coefficient >= 0
  readonly restitution: number;  // in [0, 1]
}

export function sphereInertia(mass: number, radius: number): number {
  return 0.4 * mass * radius * radius;
}

function tangentBasis(n: Vec3): [Vec3, Vec3] {
  // Same choice as the kernel: the coordinate axis least aligned with n, then orthogonalise.
  const a: Vec3 = Math.abs(n[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
  const t1raw = cross(n, a);
  const t1 = scale(t1raw, 1 / norm(t1raw));
  const t2 = cross(n, t1);
  return [t1, t2];
}

function omegaWorld(body: SphereState): Vec3 {
  return matVec(quatToMatrix(body.quaternion), body.omegaBody);
}

function pointVelocity(body: SphereState, offsetWorld: Vec3): Vec3 {
  return add(body.velocity, cross(omegaWorld(body), offsetWorld));
}

/** Apply a world-frame impulse J at offset r (from the centre of mass). Updates velocity and omega_body. */
function applyImpulse(body: SphereState, impulse: Vec3, r: Vec3, invI: number, rot: Mat3): void {
  body.velocity = add(body.velocity, scale(impulse, 1 / body.mass));
  const wWorld = add(matVec(rot, body.omegaBody), scale(cross(r, impulse), invI));
  body.omegaBody = matVec(matTranspose(rot), wWorld);
}

function resolvePlane(body: SphereState, plane: Plane, restitution: number, friction: number, invI: number): void {
  const n = plane.normal;
  const r = scale(n, -body.radius); // centre of mass -> contact point
  const rot = quatToMatrix(body.quaternion);
  const m = body.mass;
  const eff = (a: Vec3, b: Vec3): number => dot(a, add(scale(b, 1 / m), scale(cross(cross(r, b), r), invI)));

  const vcN = dot(pointVelocity(body, r), n);
  if (vcN >= 0) return; // separating, or no approach: no normal impulse
  const kNN = eff(n, n);
  const jN = (-(1 + restitution) * vcN) / kNN;
  applyImpulse(body, scale(n, jN), r, invI, rot);

  // Tangential (friction) impulse at the updated contact velocity.
  const vc = pointVelocity(body, r);
  const vtVec = sub(vc, scale(n, dot(vc, n)));
  const [t1, t2] = tangentBasis(n);
  const vt0 = dot(vtVec, t1);
  const vt1 = dot(vtVec, t2);
  if (vt0 === 0 && vt1 === 0) return;
  const k11 = eff(t1, t1);
  const k12 = eff(t1, t2);
  const k21 = eff(t2, t1);
  const k22 = eff(t2, t2);
  const det = k11 * k22 - k12 * k21;
  const j1 = -(k22 * vt0 - k12 * vt1) / det;
  const j2 = -(-k21 * vt0 + k11 * vt1) / det;
  const maxFriction = friction * jN;
  let jt: Vec3;
  if (Math.hypot(j1, j2) <= maxFriction) {
    jt = add(scale(t1, j1), scale(t2, j2)); // sticking
  } else {
    const speed = Math.hypot(vt0, vt1);
    jt = scale(add(scale(t1, vt0), scale(t2, vt1)), -maxFriction / speed); // sliding (kinetic)
  }
  applyImpulse(body, jt, r, invI, rot);
}

/**
 * Advance one sphere by one time step h under gravity and plane contacts. Mutates `body`.
 * Returns the indices (into `planes`) of the planes that were touching in this step.
 */
export function stepSphere(
  body: SphereState, h: number, gravity: Vec3, planes: readonly Plane[], contact: ContactParams,
): number[] {
  if (!(h > 0)) throw new Error("time step must be > 0");
  if (!(body.radius > 0)) throw new Error("radius must be > 0");
  if (!(contact.restitution >= 0 && contact.restitution <= 1)) throw new Error("restitution must lie in [0, 1]");
  if (!(contact.friction >= 0)) throw new Error("friction must be >= 0");
  const invI = 1 / sphereInertia(body.mass, body.radius);
  const R = body.radius;

  // 1. predict
  const xOld = body.position;
  body.velocity = add(body.velocity, scale(gravity, h));
  const xPred = add(xOld, scale(body.velocity, h));

  // 2. detect from predicted gaps
  const touching: number[] = [];
  for (let i = 0; i < planes.length; i++) {
    const p = planes[i];
    if (dot(p.normal, xPred) - p.offset - R < CONTACT_TOLERANCE) touching.push(i);
  }

  // 3. impulses in plane order
  for (const i of touching) resolvePlane(body, planes[i], contact.restitution, contact.friction, invI);

  // 4. move, then project out residual penetration
  let xNew = add(xOld, scale(body.velocity, h));
  for (const i of touching) {
    const p = planes[i];
    const gap = dot(p.normal, xNew) - p.offset - R;
    if (gap < 0) xNew = add(xNew, scale(p.normal, -gap));
  }
  body.position = xNew;

  // 5. rotate with the post-impulse body-frame angular velocity
  const dq = quatRotationIncrement(body.omegaBody, h);
  body.quaternion = quatNormalize(quatMul(body.quaternion, dq));
  return touching;
}
