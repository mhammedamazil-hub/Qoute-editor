// Fixed-step accumulator. Pure functions so the timing rules can be tested without a browser.

export interface StepPlan {
  /** Whole physics steps to run this frame. */
  readonly steps: number;
  /** Time carried to the next frame, seconds (always in [0, dt)). */
  readonly accumulator: number;
  /** True when the frame had more work than maxSteps allowed; the excess time is dropped, not replayed. */
  readonly clamped: boolean;
}

/**
 * Plan the physics steps for one rendered frame.
 * @param accumulator time already owed to the simulation, seconds
 * @param frameSeconds wall-clock time since the last frame
 * @param timeScale simulation speed multiplier (0 pauses)
 * @param dt physics step, seconds
 * @param maxSteps upper bound on steps per frame (protects against the spiral of death)
 */
export function planSteps(
  accumulator: number, frameSeconds: number, timeScale: number, dt: number, maxSteps: number,
): StepPlan {
  if (!(dt > 0)) throw new Error("dt must be > 0");
  if (!(timeScale >= 0)) throw new Error("timeScale must be >= 0");
  // A long pause (tab switched, debugger) must not feed seconds of simulation into one frame.
  const frame = Math.min(Math.max(frameSeconds, 0), 0.1);
  let acc = accumulator + frame * timeScale;
  const whole = Math.floor(acc / dt + 1e-9);
  if (whole > maxSteps) return { steps: maxSteps, accumulator: 0, clamped: true };
  acc = Math.max(0, acc - whole * dt);
  return { steps: whole, accumulator: Math.min(acc, dt), clamped: false };
}
