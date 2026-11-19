// The view maps physics (z-up) to three.js (y-up). A wrong map would show the ball moving or spinning the wrong way.
import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { quatToView, toView } from "../src/render/viewer";
import { quatNormalize, quatToMatrix, matVec } from "../src/physics/vec";

describe("physics -> view mapping", () => {
  it("maps z-up to y-up with the expected axes", () => {
    const v = toView([1, 2, 3]);
    expect([v.x, v.y, v.z]).toEqual([1, 3, -2]);
  });

  it("is a proper rotation (no mirror): e_x x e_y = e_z after mapping", () => {
    const ex = toView([1, 0, 0]);
    const ey = toView([0, 1, 0]);
    const ez = toView([0, 0, 1]);
    const c = ex.clone().cross(ey);
    expect(c.distanceTo(ez)).toBeLessThan(1e-12);
  });

  it("maps physics rotations to the same physical rotation in view (position and orientation agree)", () => {
    const cases: [number, number, number, number][] = [
      [1, 0, 0, 0],
      [Math.cos(0.3), 0, 0, Math.sin(0.3)],
      [0.6, 0.48, -0.36, 0.52],
      [0.9, 0.1, 0.3, -0.2],
    ];
    const probe: [number, number, number] = [0.2, -0.7, 0.4];
    for (const raw of cases) {
      const q = quatNormalize(raw);
      const rotatedPhys = matVec(quatToMatrix(q), probe);
      const viewRotated = toView(rotatedPhys);
      const viaQuat = toView(probe).applyQuaternion(quatToView(q));
      expect(viaQuat.distanceTo(viewRotated)).toBeLessThan(1e-12);
    }
  });

  it("a spin about physics z appears as a spin about view y with the same angle", () => {
    const th = 0.5;
    const q = quatToView([Math.cos(th / 2), 0, 0, Math.sin(th / 2)]);
    const angle = 2 * Math.acos(Math.min(1, Math.abs(q.w)));
    expect(angle).toBeCloseTo(th, 12);
    const axis = new THREE.Vector3(q.x, q.y, q.z).normalize();
    expect(Math.abs(axis.y)).toBeCloseTo(1, 12);
  });
});
