// Three.js view of a World. Physics is z-up (reality convention); the view is y-up. The map
// (x, y, z)_phys -> (x, z, -y)_view is a proper rotation, so handedness is preserved.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { SceneSpec, World } from "../physics/scene";

const TRAIL_MAX = 400;

/** Physics position -> view position. */
export function toView(p: readonly number[]): THREE.Vector3 {
  return new THREE.Vector3(p[0], p[2], -p[1]);
}

// Rotation that takes physics axes to view axes (about x by -90 degrees).
const C_TO_VIEW = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2);
const C_INV = C_TO_VIEW.clone().invert();

/** Body->world quaternion [w,x,y,z] in physics axes -> view quaternion. */
export function quatToView(q: readonly number[]): THREE.Quaternion {
  const qp = new THREE.Quaternion(q[1], q[2], q[3], q[0]);
  return C_TO_VIEW.clone().multiply(qp).multiply(C_INV);
}

function stripeTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 256;
  const g = c.getContext("2d");
  if (!g) throw new Error("2D canvas unavailable");
  // Four meridian-like bands plus one equatorial band, so spin is visible.
  for (let i = 0; i < 8; i++) {
    g.fillStyle = i % 2 === 0 ? "#e8eef5" : "#2d6fb3";
    g.fillRect((i * 512) / 8, 0, 512 / 8, 256);
  }
  g.fillStyle = "#e0a030";
  g.fillRect(0, 118, 512, 20);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function checkerTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 256;
  const g = c.getContext("2d");
  if (!g) throw new Error("2D canvas unavailable");
  g.fillStyle = "#4a4f57";
  g.fillRect(0, 0, 256, 256);
  g.fillStyle = "#6b717b";
  g.fillRect(0, 0, 128, 128);
  g.fillRect(128, 128, 128, 128);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(40, 40);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export class Viewer {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  readonly controls: OrbitControls;
  private ball: THREE.Mesh;
  private ballMat: THREE.MeshStandardMaterial;
  private trail: THREE.Line;
  private trailPts: THREE.Vector3[] = [];
  private arrow: THREE.ArrowHelper;
  private planeMeshes: THREE.Mesh[] = [];
  private lastTrailTime = -1;
  showTrail = true;
  showArrow = true;
  follow = true;

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.setClearColor(0x161a22, 1);

    this.scene.fog = new THREE.Fog(0x161a22, 25, 70);
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.01, 200);
    this.camera.position.set(1.6, 0.9, 1.6);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0.05, 0);
    this.controls.minDistance = 0.1;
    this.controls.maxDistance = 60;

    this.scene.add(new THREE.HemisphereLight(0xbfd6ff, 0x30261c, 0.9));
    const sun = new THREE.DirectionalLight(0xffffff, 2.2);
    sun.position.set(3, 6, 2);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    const cam = sun.shadow.camera;
    cam.left = -4; cam.right = 4; cam.top = 4; cam.bottom = -4; cam.near = 0.5; cam.far = 20;
    sun.shadow.bias = -0.0005;
    this.scene.add(sun);

    this.ballMat = new THREE.MeshStandardMaterial({
      map: stripeTexture(), metalness: 0.35, roughness: 0.4, emissive: 0xff7a1a, emissiveIntensity: 0,
    });
    this.ball = new THREE.Mesh(new THREE.SphereGeometry(1, 64, 40), this.ballMat);
    this.ball.castShadow = true;
    this.scene.add(this.ball);

    const trailGeo = new THREE.BufferGeometry();
    trailGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(TRAIL_MAX * 3), 3));
    trailGeo.setDrawRange(0, 0);
    this.trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: 0xffd166 }));
    this.scene.add(this.trail);

    this.arrow = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 0.1, 0x7ee787);
    this.scene.add(this.arrow);

    this.resize();
    window.addEventListener("resize", () => this.resize());
  }

  resize(): void {
    const canvas = this.renderer.domElement;
    const w = canvas.clientWidth || canvas.width;
    const h = canvas.clientHeight || canvas.height;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / Math.max(1, h);
    this.camera.updateProjectionMatrix();
  }

  /** Rebuild scene-dependent objects (planes, ball radius, trail reset). */
  setScene(spec: SceneSpec): void {
    for (const m of this.planeMeshes) {
      this.scene.remove(m);
      m.geometry.dispose();
      (m.material as THREE.Material).dispose();
    }
    this.planeMeshes = [];
    const checker = checkerTexture();
    for (const p of spec.planes) {
      const nView = toView(p.normal);
      const geo = new THREE.PlaneGeometry(80, 80);
      const mat = new THREE.MeshStandardMaterial({ map: checker, roughness: 0.85, metalness: 0, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), nView);
      mesh.position.copy(nView.clone().multiplyScalar(p.offset));
      mesh.receiveShadow = true;
      this.scene.add(mesh);
      this.planeMeshes.push(mesh);
    }
    this.ball.scale.setScalar(spec.radius);
    this.resetTrail();
    this.controls.target.copy(toView(spec.initialPosition));
  }

  /** Forget the recorded path (call after a reset). */
  resetTrail(): void {
    this.trailPts = [];
    this.lastTrailTime = -1;
    this.trail.geometry.setDrawRange(0, 0);
  }

  /** Draw the world's current state. Call once per frame. */
  sync(world: World): void {
    const b = world.body;
    const pos = toView(b.position);
    this.ball.position.copy(pos);
    this.ball.quaternion.copy(quatToView(b.quaternion));
    this.ballMat.emissiveIntensity = world.lastTouching.length ? 0.6 : 0;

    const t = world.time;
    if (this.showTrail && t - this.lastTrailTime >= 0.01) {
      this.lastTrailTime = t;
      this.trailPts.push(pos.clone());
      if (this.trailPts.length > TRAIL_MAX) this.trailPts.shift();
      const attr = this.trail.geometry.getAttribute("position") as THREE.BufferAttribute;
      this.trailPts.forEach((p, i) => attr.setXYZ(i, p.x, p.y, p.z));
      attr.needsUpdate = true;
      this.trail.geometry.setDrawRange(0, this.trailPts.length);
    }
    this.trail.visible = this.showTrail;

    const v = toView(b.velocity);
    const speed = v.length();
    this.arrow.visible = this.showArrow && speed > 1e-6;
    if (this.arrow.visible) {
      this.arrow.position.copy(pos);
      this.arrow.setDirection(v.clone().normalize());
      this.arrow.setLength(Math.min(0.6, 0.15 * speed + 0.05), 0.06, 0.04);
    }

    if (this.follow) {
      this.controls.target.lerp(pos, 0.2);
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}

