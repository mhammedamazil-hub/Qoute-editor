import { describe, expect, it } from "vitest";
import { planSteps } from "../src/core/loop";

describe("planSteps", () => {
  it("runs the right number of steps for real time at 60 fps and dt = 1e-4", () => {
    const dt = 1e-4;
    let acc = 0;
    let total = 0;
    for (let f = 0; f < 600; f++) { // 10 s of frames at 60 Hz
      const p = planSteps(acc, 1 / 60, 1, dt, 100000);
      total += p.steps;
      acc = p.accumulator;
    }
    // 10 s of simulated time = 100000 steps (one step of slack for float rounding)
    expect(Math.abs(total - 100000)).toBeLessThanOrEqual(1);
  });

  it("scales with the time scale and pauses at zero", () => {
    expect(planSteps(0, 1 / 60, 0, 1e-4, 1000).steps).toBe(0);
    const half = planSteps(0, 1 / 60, 0.5, 1e-4, 1000).steps;
    const full = planSteps(0, 1 / 60, 1, 1e-4, 1000).steps;
    expect(Math.abs(half * 2 - full)).toBeLessThanOrEqual(1);
  });

  it("clamps a long stall to 0.1 s of simulation and never replays dropped time", () => {
    const p = planSteps(0, 5, 1, 1e-4, 100000); // a 5 s stall
    expect(p.steps).toBe(1000); // 0.1 s
    expect(p.accumulator).toBeLessThan(1e-4);
  });

  it("drops the excess and reports clamping when maxSteps is exceeded", () => {
    const p = planSteps(0, 0.1, 1, 1e-4, 100);
    expect(p.clamped).toBe(true);
    expect(p.steps).toBe(100);
    expect(p.accumulator).toBe(0);
  });

  it("keeps the leftover below one step", () => {
    const p = planSteps(0, 0.01234567, 1, 1e-4, 100000);
    expect(p.accumulator).toBeGreaterThanOrEqual(0);
    expect(p.accumulator).toBeLessThan(1e-4);
  });

  it("rejects invalid arguments", () => {
    expect(() => planSteps(0, 0.01, 1, 0, 10)).toThrow();
    expect(() => planSteps(0, 0.01, -1, 1e-4, 10)).toThrow();
  });
});
