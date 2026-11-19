// Application shell: scene picker, transport controls, live contact parameters, readouts and the frame loop.

import { planSteps } from "../core/loop";
import { World, loadScene } from "../physics/scene";
import { Viewer } from "../render/viewer";

/** Physics step, seconds. Matches the Python kernel's default so the viewer and the reference agree. */
export const PHYSICS_DT = 1e-4;
/** Hard cap on physics steps per rendered frame (about 0.1 s of simulation at PHYSICS_DT). */
const MAX_STEPS_PER_FRAME = 1000;

const SCENE_CHOICES: { id: string; label: string }[] = [
  { id: "rolling-sphere", label: "Rolling sphere: slides, then rolls" },
  { id: "ramp-roll", label: "Ramp: rolls down 20 degrees" },
  { id: "bouncing-sphere", label: "Bouncing sphere: restitution 0.7" },
];

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node as T;
}

const fmt = (x: number, digits = 3) => (Math.abs(x) < 5e-10 ? "0" : x.toFixed(digits));
const vecText = (v: readonly number[], digits = 3) => `(${v.map((x) => fmt(x, digits)).join(", ")})`;

class App {
  private viewer: Viewer;
  private world: World | null = null;
  private playing = true;
  private timeScale = 1;
  private acc = 0;
  private lastFrame = 0;
  private lastReadout = 0;
  private stepsWindow = 0;
  private windowStart = 0;
  private stepsPerSecond = 0;
  private sceneCache = new Map<string, unknown>();

  constructor() {
    const canvas = el<HTMLCanvasElement>("view");
    this.viewer = new Viewer(canvas);
    const select = el<HTMLSelectElement>("sceneSelect");
    for (const s of SCENE_CHOICES) {
      const o = document.createElement("option");
      o.value = s.id;
      o.textContent = s.label;
      select.appendChild(o);
    }
    select.addEventListener("change", () => void this.load(select.value));

    el<HTMLButtonElement>("playBtn").addEventListener("click", () => this.togglePlay());
    el<HTMLButtonElement>("stepBtn").addEventListener("click", () => this.stepFrame());
    el<HTMLButtonElement>("resetBtn").addEventListener("click", () => this.reset());

    const speed = el<HTMLInputElement>("speed");
    speed.addEventListener("input", () => {
      this.timeScale = Number(speed.value);
      el<HTMLElement>("speedLabel").textContent = `${this.timeScale.toFixed(2)}x`;
    });
    this.timeScale = Number(speed.value);

    const friction = el<HTMLInputElement>("friction");
    const restitution = el<HTMLInputElement>("restitution");
    const applyContact = () => {
      if (!this.world) return;
      this.world.setContact(Number(friction.value), Number(restitution.value));
      el<HTMLElement>("frictionLabel").textContent = Number(friction.value).toFixed(2);
      el<HTMLElement>("restitutionLabel").textContent = Number(restitution.value).toFixed(2);
    };
    friction.addEventListener("input", applyContact);
    restitution.addEventListener("input", applyContact);
    this.applyContactToSliders = (f: number, e: number) => {
      friction.value = String(f);
      restitution.value = String(e);
      el<HTMLElement>("frictionLabel").textContent = f.toFixed(2);
      el<HTMLElement>("restitutionLabel").textContent = e.toFixed(2);
    };

    el<HTMLInputElement>("trailChk").addEventListener("change", (ev) => {
      this.viewer.showTrail = (ev.target as HTMLInputElement).checked;
    });
    el<HTMLInputElement>("arrowChk").addEventListener("change", (ev) => {
      this.viewer.showArrow = (ev.target as HTMLInputElement).checked;
    });
    el<HTMLInputElement>("followChk").addEventListener("change", (ev) => {
      this.viewer.follow = (ev.target as HTMLInputElement).checked;
    });

    window.addEventListener("keydown", (ev) => {
      if (ev.target instanceof HTMLInputElement || ev.target instanceof HTMLSelectElement) return;
      if (ev.code === "Space") { ev.preventDefault(); this.togglePlay(); }
      else if (ev.key === "r" || ev.key === "R") this.reset();
      else if (ev.key === ".") this.stepFrame();
    });

    this.lastFrame = performance.now();
    this.windowStart = this.lastFrame;
    requestAnimationFrame((t) => this.frame(t));
    void this.load(select.value);
  }

  private applyContactToSliders!: (f: number, e: number) => void;

  private async fetchScene(id: string): Promise<unknown> {
    const cached = this.sceneCache.get(id);
    if (cached) return cached;
    const res = await fetch(`${import.meta.env.BASE_URL}scenes/${id}.json`);
    if (!res.ok) throw new Error(`cannot load scene ${id}: HTTP ${res.status}`);
    const doc = await res.json();
    this.sceneCache.set(id, doc);
    return doc;
  }

  async load(id: string): Promise<void> {
    try {
      const spec = loadScene(await this.fetchScene(id));
      this.world = new World(spec, PHYSICS_DT);
      this.viewer.setScene(spec);
      this.acc = 0;
      this.applyContactToSliders(spec.contact.friction, spec.contact.restitution);
      el<HTMLElement>("sceneName").textContent = spec.name;
      el<HTMLElement>("sceneInfo").textContent =
        `${spec.materialName ?? "given"} sphere, R ${spec.radius} m, m ${spec.mass.toFixed(4)} kg, ` +
        `${spec.planeIds.length} plane(s)`;
      el<HTMLElement>("errorBox").textContent = "";
      this.viewer.sync(this.world);
    } catch (err) {
      el<HTMLElement>("errorBox").textContent = err instanceof Error ? err.message : String(err);
    }
  }

  private togglePlay(): void {
    this.playing = !this.playing;
    el<HTMLButtonElement>("playBtn").textContent = this.playing ? "Pause" : "Play";
  }

  private stepFrame(): void {
    if (!this.world) return;
    this.playing = false;
    el<HTMLButtonElement>("playBtn").textContent = "Play";
    this.world.step(Math.round(0.01 / PHYSICS_DT)); // 10 ms of simulation per press
    this.viewer.sync(this.world);
  }

  private reset(): void {
    if (!this.world) return;
    this.world.reset();
    this.viewer.resetTrail();
    this.acc = 0;
    this.viewer.sync(this.world);
  }

  private frame(now: number): void {
    const frameSeconds = (now - this.lastFrame) / 1000;
    this.lastFrame = now;
    if (this.world) {
      const plan = planSteps(this.acc, frameSeconds, this.playing ? this.timeScale : 0, PHYSICS_DT, MAX_STEPS_PER_FRAME);
      this.acc = plan.accumulator;
      if (plan.steps > 0) {
        this.world.step(plan.steps);
        this.stepsWindow += plan.steps;
      }
      this.viewer.sync(this.world);
      this.updateReadouts(now);
    }
    requestAnimationFrame((t) => this.frame(t));
  }

  private updateReadouts(now: number): void {
    if (now - this.windowStart >= 1000) {
      this.stepsPerSecond = (this.stepsWindow * 1000) / (now - this.windowStart);
      this.stepsWindow = 0;
      this.windowStart = now;
    }
    if (now - this.lastReadout < 100 || !this.world) return;
    this.lastReadout = now;
    const w = this.world;
    const b = w.body;
    const speed = Math.hypot(b.velocity[0], b.velocity[1], b.velocity[2]);
    const omega = Math.hypot(b.omegaBody[0], b.omegaBody[1], b.omegaBody[2]);
    el<HTMLElement>("rTime").textContent = `${w.time.toFixed(3)} s`;
    el<HTMLElement>("rPos").textContent = vecText(b.position);
    el<HTMLElement>("rVel").textContent = `${vecText(b.velocity)}  |v| ${speed.toFixed(3)} m/s`;
    el<HTMLElement>("rOmega").textContent = `|omega| ${omega.toFixed(2)} rad/s`;
    el<HTMLElement>("rKE").textContent = `${w.kineticEnergy().toExponential(3)} J`;
    el<HTMLElement>("rContact").textContent = w.lastTouching.length
      ? `touching ${w.lastTouching.map((i) => w.spec.planeIds[i]).join(", ")}`
      : "in the air";
    el<HTMLElement>("rPerf").textContent =
      `${(this.stepsPerSecond / (1 / PHYSICS_DT)).toFixed(1)}x real time, ${Math.round(this.stepsPerSecond).toLocaleString()} steps/s`;
  }
}

new App();
