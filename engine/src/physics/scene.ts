// Load a reality.scene v1 document (see reality/SCENE_SCHEMA.md) into a physics spec, and run it at a fixed step.
// Mass and contact selection follow reality.control.scene.mass_properties and reality.control.simulate.run.

import { MATERIAL_DENSITY_KG_M3 } from "./materials.generated";
import { ContactParams, Plane, SphereState, makePlane, stepSphere } from "./sphere";
import { Vec3, Quat } from "./vec";

export interface SceneSpec {
  readonly name: string;
  readonly gravity: Vec3;
  readonly bodyId: string;
  readonly radius: number;
  readonly mass: number;
  readonly density: number;
  readonly materialName: string | null;
  readonly initialPosition: Vec3;
  readonly initialVelocity: Vec3;
  readonly initialOmegaBody: Vec3;
  readonly planeIds: readonly string[];
  readonly planes: readonly Plane[];
  readonly contact: ContactParams;
}

export class SceneError extends Error {}

function vec3(value: unknown, what: string): Vec3 {
  if (!Array.isArray(value) || value.length !== 3 || !value.every((x) => typeof x === "number" && Number.isFinite(x))) {
    throw new SceneError(`${what} must be three finite numbers`);
  }
  return [value[0], value[1], value[2]];
}

export function sphereVolume(radius: number): number {
  return (4 / 3) * Math.PI * radius * radius * radius;
}

/** Parse and check a reality.scene v1 object. Throws SceneError with a message that names the problem. */
export function loadScene(doc: unknown): SceneSpec {
  if (typeof doc !== "object" || doc === null) throw new SceneError("scene must be a JSON object");
  const d = doc as Record<string, any>;
  if (d.schema !== "reality.scene") throw new SceneError(`schema must be "reality.scene"`);
  if (d.schema_version !== 1) throw new SceneError("only schema_version 1 is supported");
  const gravity = vec3(d.environment?.gravity, "environment.gravity");

  const bodies: any[] = Array.isArray(d.bodies) ? d.bodies : [];
  if (bodies.length !== 1) throw new SceneError("the engine runs exactly one body in schema v1");
  const b = bodies[0];
  if (b.type !== "sphere") throw new SceneError(`unsupported body type ${String(b.type)}; only "sphere"`);
  const radius = Number(b.radius);
  if (!(radius > 0)) throw new SceneError("radius must be > 0");

  const sources = ["material", "mass", "density"].filter((k) => b[k] !== undefined);
  if (sources.length !== 1) throw new SceneError("give exactly one of material, mass or density");
  let mass: number;
  let density: number;
  let materialName: string | null = null;
  if (b.material !== undefined) {
    materialName = String(b.material).toLowerCase();
    if (!Object.prototype.hasOwnProperty.call(MATERIAL_DENSITY_KG_M3, materialName)) {
      throw new SceneError(`unknown material ${materialName}`);
    }
    density = MATERIAL_DENSITY_KG_M3[materialName];
    mass = density * sphereVolume(radius);
  } else if (b.mass !== undefined) {
    mass = Number(b.mass);
    if (!(mass > 0)) throw new SceneError("mass must be > 0");
    density = mass / sphereVolume(radius);
  } else {
    density = Number(b.density);
    if (!(density > 0)) throw new SceneError("density must be > 0");
    mass = density * sphereVolume(radius);
  }

  const planeById = new Map<string, any>();
  for (const p of Array.isArray(d.planes) ? d.planes : []) planeById.set(String(p.id), p);
  const contacts: any[] = (Array.isArray(d.contacts) ? d.contacts : []).filter((c: any) => c.body === b.id);
  const planeIds: string[] = [];
  const planes: Plane[] = [];
  for (const c of contacts) {
    const p = planeById.get(String(c.plane));
    if (!p) throw new SceneError(`contact refers to unknown plane ${String(c.plane)}`);
    planeIds.push(String(c.plane));
    planes.push(makePlane(vec3(p.normal, "plane normal"), Number(p.offset)));
  }
  const first = contacts[0];
  const contact: ContactParams = first
    ? { friction: Number(first.friction), restitution: Number(first.restitution) }
    : { friction: 0, restitution: 0 };
  if (!(contact.friction >= 0)) throw new SceneError("friction must be >= 0");
  if (!(contact.restitution >= 0 && contact.restitution <= 1)) throw new SceneError("restitution must be in [0, 1]");

  return {
    name: String(d.name ?? "scene"),
    gravity,
    bodyId: String(b.id),
    radius,
    mass,
    density,
    materialName,
    initialPosition: vec3(b.position ?? [0, 0, 0], "position"),
    initialVelocity: vec3(b.velocity ?? [0, 0, 0], "velocity"),
    initialOmegaBody: vec3(b.omega ?? [0, 0, 0], "omega"),
    planeIds,
    planes,
    contact,
  };
}

export const IDENTITY_QUAT: Quat = [1, 0, 0, 0];

export function initialState(spec: SceneSpec): SphereState {
  return {
    mass: spec.mass,
    radius: spec.radius,
    position: [...spec.initialPosition] as Vec3,
    velocity: [...spec.initialVelocity] as Vec3,
    quaternion: [...IDENTITY_QUAT] as Quat,
    omegaBody: [...spec.initialOmegaBody] as Vec3,
  };
}

/** Fixed-step simulation of one scene. Time is steps * dt, exactly as in the kernel. */
export class World {
  private state: SphereState;
  private contact: ContactParams;
  steps = 0;
  lastTouching: number[] = [];

  constructor(readonly spec: SceneSpec, readonly dt: number) {
    if (!(dt > 0)) throw new SceneError("dt must be > 0");
    this.state = initialState(spec);
    this.contact = { ...spec.contact };
  }

  get time(): number {
    return this.steps * this.dt;
  }

  get body(): Readonly<SphereState> {
    return this.state;
  }

  get friction(): number {
    return this.contact.friction;
  }

  get restitution(): number {
    return this.contact.restitution;
  }

  setContact(friction: number, restitution: number): void {
    this.contact = { friction, restitution };
  }

  step(n = 1): void {
    for (let i = 0; i < n; i++) {
      this.lastTouching = stepSphere(this.state, this.dt, this.spec.gravity, this.spec.planes, this.contact);
      this.steps++;
    }
  }

  reset(): void {
    this.state = initialState(this.spec);
    this.steps = 0;
    this.lastTouching = [];
  }

  kineticEnergy(): number {
    const m = this.spec.mass;
    const I = 0.4 * m * this.spec.radius * this.spec.radius;
    const v = this.state.velocity;
    const w = this.state.omegaBody;
    return 0.5 * m * (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) + 0.5 * I * (w[0] * w[0] + w[1] * w[1] + w[2] * w[2]);
  }
}
