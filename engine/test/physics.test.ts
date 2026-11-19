// Physics checks in the engine itself. Closed-form results where they exist; the Python cross-check is in reference.test.ts.
import { describe, expect, it } from "vitest";
import { World, loadScene, sphereVolume } from "../src/physics/scene";
import { makePlane } from "../src/physics/sphere";

const G = 9.80665;
const R = 0.05;

function sceneDoc(opts: {
  pos: [number, number, number]; vel?: [number, number, number]; omega?: [number, number, number];
  normal?: [number, number, number]; offset?: number; friction: number; restitution: number;
  material?: string; gravity?: [number, number, number]; planeId?: string;
}) {
  const planeId = opts.planeId ?? "floor";
  return {
    schema: "reality.scene", schema_version: 1, name: "test",
    environment: { gravity: opts.gravity ?? [0, 0, -G], units: "SI" },
    bodies: [{ id: "ball", type: "sphere", radius: R, material: opts.material ?? "steel",
      position: opts.pos, velocity: opts.vel ?? [0, 0, 0], omega: opts.omega ?? [0, 0, 0] }],
    planes: [{ id: planeId, normal: opts.normal ?? [0, 0, 1], offset: opts.offset ?? 0 }],
    contacts: [{ body: "ball", plane: planeId, friction: opts.friction, restitution: opts.restitution }],
    random_seed: null,
  };
}

describe("scene loading", () => {
  it("computes steel sphere mass from density times volume", () => {
    const spec = loadScene(sceneDoc({ pos: [0, 0, R], friction: 0, restitution: 0 }));
    expect(spec.mass).toBeCloseTo(7850 * sphereVolume(R), 12);
  });

  it("accepts mass or density in place of a material", () => {
    const d = sceneDoc({ pos: [0, 0, R], friction: 0, restitution: 0 }) as any;
    d.bodies[0] = { id: "ball", type: "sphere", radius: R, mass: 2.5, position: [0, 0, R] };
    expect(loadScene(d).mass).toBe(2.5);
    d.bodies[0] = { id: "ball", type: "sphere", radius: R, density: 1000, position: [0, 0, R] };
    expect(loadScene(d).mass).toBeCloseTo(1000 * sphereVolume(R), 12);
  });

  it("rejects unsupported or invalid input with a named reason", () => {
    const two = sceneDoc({ pos: [0, 0, R], friction: 0, restitution: 0 }) as any;
    two.bodies.push({ ...two.bodies[0], id: "other" });
    expect(() => loadScene(two)).toThrow(/exactly one body/);
    const box = sceneDoc({ pos: [0, 0, R], friction: 0, restitution: 0 }) as any;
    box.bodies[0].type = "box";
    expect(() => loadScene(box)).toThrow(/unsupported body type/);
    const mat = sceneDoc({ pos: [0, 0, R], friction: 0, restitution: 0, material: "unobtainium" });
    expect(() => loadScene(mat)).toThrow(/unknown material/);
    const proto = sceneDoc({ pos: [0, 0, R], friction: 0, restitution: 0, material: "constructor" });
    expect(() => loadScene(proto)).toThrow(/unknown material/);
    const bad = sceneDoc({ pos: [0, 0, R], friction: 0, restitution: 0 }) as any;
    bad.contacts[0].restitution = 1.5;
    expect(() => loadScene(bad)).toThrow(/restitution/);
  });
});

describe("free motion", () => {
  it("follows the semi-implicit Euler closed form x = x0 + g t^2/2 + g h t/2", () => {
    // The kernel predicts v <- v + g h, then x <- x + v h. Over n steps this gives the exact result below.
    const h = 1e-4;
    const x0 = 100;
    const world = new World(loadScene(sceneDoc({ pos: [0, 0, x0], friction: 0, restitution: 0 })), h);
    world.step(5000); // 0.5 s, no contact
    const t = world.time;
    expect(t).toBeCloseTo(0.5, 12);
    const expected = x0 - 0.5 * G * t * t - 0.5 * G * h * t;
    expect(world.body.position[2]).toBeCloseTo(expected, 9);
    expect(world.body.position[0]).toBe(0);
  });
});

describe("contact", () => {
  it("rebounds at speed e times the impact speed (no friction)", () => {
    const e = 0.7;
    const h = 1e-4;
    const world = new World(loadScene(sceneDoc({ pos: [0, 0, 1], friction: 0, restitution: e })), h);
    let vImpact = 0;
    let vAfter = 0;
    for (let k = 0; k < 40000; k++) {
      const before = world.body.velocity[2];
      world.step();
      if (world.lastTouching.length && before < 0 && world.body.velocity[2] > 0 && vAfter === 0) {
        vImpact = -before;
        vAfter = world.body.velocity[2];
        break;
      }
    }
    expect(vImpact).toBeGreaterThan(0);
    // Gravity acts during the contact step, so the impulse sees the velocity after prediction. Allow one step of g.
    expect(vAfter / (vImpact + G * h)).toBeCloseTo(e, 2);
  });

  // Height of the first rebound apex for an elastic drop from `drop` metres, step h.
  function firstApex(h: number, drop: number): number {
    const world = new World(loadScene(sceneDoc({ pos: [0, 0, drop], friction: 0, restitution: 1 })), h);
    let phase = 0; // 0 falling, 1 in first contact, 2 in first rebound
    let apex = 0;
    for (let k = 0; k < Math.round(3 / h) && phase < 3; k++) {
      world.step();
      const touching = world.lastTouching.length > 0;
      if (phase === 0 && touching) phase = 1;
      else if (phase === 1 && !touching) phase = 2;
      else if (phase === 2 && touching) phase = 3;
      if (phase === 2) apex = Math.max(apex, world.body.position[2]);
    }
    expect(phase).toBeGreaterThanOrEqual(2); // a rebound happened
    return apex;
  }

  it("an elastic bounce (e = 1) returns to the drop height (first-order in dt)", () => {
    const drop = 1.0;
    const e1 = Math.abs(firstApex(1e-4, drop) - drop);
    const e2 = Math.abs(firstApex(5e-5, drop) - drop);
    expect(e1 / drop).toBeLessThan(1e-3);
    // The error is O(dt): halving the step halves the error (measured ratio about 2).
    expect(e1 / e2).toBeGreaterThan(1.8);
    expect(e1 / e2).toBeLessThan(2.2);
  });

  it("slide to roll: t = 2 v0 / (7 mu g) and final speed 5/7 v0 (solid sphere)", () => {
    const h = 1e-4;
    const mu = 0.1;
    const v0 = 2;
    const world = new World(loadScene(sceneDoc({ pos: [0, 0, R], vel: [v0, 0, 0], friction: mu, restitution: 0 })), h);
    let onset = -1;
    for (let k = 0; k < 70000 && onset < 0; k++) {
      world.step();
      // Rolling without slip: v_x = omega_y R (body frame equals world for this rotation axis).
      const slip = world.body.velocity[0] - world.body.omegaBody[1] * R;
      if (k > 100 && Math.abs(slip) < 1e-4) onset = world.time;
    }
    const analytic = (2 * v0) / (7 * mu * G);
    expect(onset).toBeGreaterThan(0);
    expect(Math.abs(onset - analytic) / analytic).toBeLessThan(2e-3);
    world.step(10000); // 1 s more
    expect(world.body.velocity[0]).toBeCloseTo((5 / 7) * v0, 3);
    expect(world.body.omegaBody[1]).toBeCloseTo(world.body.velocity[0] / R, 2);
  });

  it("ramp roll from rest: a = 5/7 g sin(theta) along the slope", () => {
    const th = (20 * Math.PI) / 180;
    const n: [number, number, number] = [-Math.sin(th), 0, Math.cos(th)];
    const up: [number, number, number] = [Math.cos(th), 0, Math.sin(th)];
    const s0 = 0.5;
    const pos: [number, number, number] = [R * n[0] + s0 * up[0], 0, R * n[2] + s0 * up[2]];
    const world = new World(loadScene(sceneDoc({ pos, normal: n, friction: 0.5, restitution: 0, planeId: "ramp" })), 1e-4);
    world.step(4000); // 0.4 s
    const t = world.time;
    const aAnalytic = (5 / 7) * G * Math.sin(th);
    const speed = Math.hypot(world.body.velocity[0], world.body.velocity[2]);
    expect(Math.abs(speed - aAnalytic * t) / (aAnalytic * t)).toBeLessThan(2e-3);
    // Distance along the slope: s = s0 - a t^2 / 2
    const s = world.body.position[0] * up[0] + world.body.position[2] * up[2];
    expect(Math.abs(s - (s0 - 0.5 * aAnalytic * t * t))).toBeLessThan(1e-3);
  });

  it("keeps the orientation quaternion normalised", () => {
    const world = new World(loadScene(sceneDoc({ pos: [0, 0, 1], vel: [1, 0, 0], omega: [0, 3, 1], friction: 0.3, restitution: 0.5 })), 1e-4);
    world.step(20000);
    const q = world.body.quaternion;
    expect(Math.abs(Math.hypot(...q) - 1)).toBeLessThan(1e-12);
  });
});

describe("plane helper", () => {
  it("normalises the normal and rejects zero", () => {
    const p = makePlane([0, 0, 5], 1);
    expect(p.normal).toEqual([0, 0, 1]);
    expect(() => makePlane([0, 0, 0], 0)).toThrow();
  });
});
