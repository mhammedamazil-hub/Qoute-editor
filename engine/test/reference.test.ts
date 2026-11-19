// Cross-check against the Python kernel. The fixtures are written by reality/tools/export_engine_assets.py,
// which runs reality.control.simulate.run with the same scene, dt and record interval.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { World, loadScene } from "../src/physics/scene";

interface Record_ {
  t: number;
  position: number[];
  velocity: number[];
  quaternion: number[];
  omega_body: number[];
}
interface Fixture {
  source: string;
  reality_version: string;
  dt: number;
  duration: number;
  scene: unknown;
  records: Record_[];
}

const names = ["rolling-sphere", "bouncing-sphere", "ramp-roll"];

function maxDiff(a: readonly number[], b: readonly number[]): number {
  return Math.max(...a.map((x, i) => Math.abs(x - b[i])));
}

describe("browser physics vs Python kernel (recorded trajectories)", () => {
  for (const name of names) {
    it(`${name}: every record matches the kernel to 1e-9`, () => {
      const fx: Fixture = JSON.parse(readFileSync(join(__dirname, "fixtures", `${name}.json`), "utf8"));
      const world = new World(loadScene(fx.scene), fx.dt);
      let worst = { pos: 0, vel: 0, quat: 0, omega: 0 };
      for (const rec of fx.records.slice(1)) {
        const target = Math.round(rec.t / fx.dt);
        world.step(target - world.steps);
        const b = world.body;
        worst = {
          pos: Math.max(worst.pos, maxDiff(b.position, rec.position)),
          vel: Math.max(worst.vel, maxDiff(b.velocity, rec.velocity)),
          quat: Math.max(worst.quat, maxDiff(b.quaternion, rec.quaternion)),
          omega: Math.max(worst.omega, maxDiff(b.omegaBody, rec.omega_body)),
        };
      }
      // Bound on the worst difference over the whole run. The measured values are printed so the margin is visible.
      console.log(`${name}: worst |diff| pos ${worst.pos.toExponential(2)} vel ${worst.vel.toExponential(2)} quat ${worst.quat.toExponential(2)} omega ${worst.omega.toExponential(2)}`);
      expect(worst.pos).toBeLessThan(1e-9);
      expect(worst.vel).toBeLessThan(1e-9);
      expect(worst.quat).toBeLessThan(1e-9);
      expect(worst.omega).toBeLessThan(1e-9);
    });
  }

  it("mass and inertia-derived quantities match the kernel's steel sphere", () => {
    const fx: Fixture = JSON.parse(readFileSync(join(__dirname, "fixtures", "rolling-sphere.json"), "utf8"));
    const spec = loadScene(fx.scene);
    // reality.control.scene.mass_properties for steel (7850 kg/m^3), R = 0.05 m
    expect(spec.mass).toBeCloseTo(4.110250388446646, 12);
    expect(spec.density).toBe(7850);
  });
});
