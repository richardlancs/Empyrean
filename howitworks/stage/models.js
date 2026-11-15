// Assemble the kit: one model per part (generated GLB if present, stand-in
// otherwise) plus the drawn extras that explain how the parts relate.

import { buildStandIn, readPalette } from "./standins.js";

/** Where each part sits, as worn. */
export const PART_LAYOUT = Object.freeze({
  glasses: Object.freeze([0, 1.55, 0.3]),
  backpack: Object.freeze([0, 0.68, -0.6]),
  speaker: Object.freeze([0.4, 0.92, -0.2]),
});

const FINGERTIP = [0.3, 1.02, 1.0];
const BOTTLE = [0.12, 0.92, 1.62];

function line(THREE, points, color, dashed = false) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points.map((p) => new THREE.Vector3(...p)));
  const material = dashed
    ? new THREE.LineDashedMaterial({ color, dashSize: 0.04, gapSize: 0.035 })
    : new THREE.LineBasicMaterial({ color });
  const object = new THREE.Line(geometry, material);
  if (dashed) object.computeLineDistances();
  return object;
}

function extras(THREE, palette) {
  const group = new THREE.Group();
  group.name = "extras";

  // USB cable from the camera, along the arm, down into the backpack.
  const cable = new THREE.CatmullRomCurve3(
    [[0.06, 1.68, 0.3], [0.3, 1.62, 0.1], [0.32, 1.55, -0.22], [0.2, 1.3, -0.5], [0.1, 1.2, -0.6]].map((p) => new THREE.Vector3(...p)),
  );
  group.add(new THREE.Mesh(
    new THREE.TubeGeometry(cable, 40, 0.008, 6),
    new THREE.MeshStandardMaterial({ color: palette.ink, roughness: 0.8 }),
  ));

  // Bluetooth: a dotted arc from the laptop to the speaker.
  const arc = new THREE.QuadraticBezierCurve3(
    new THREE.Vector3(0.1, 1.15, -0.6), new THREE.Vector3(0.75, 1.35, -0.4), new THREE.Vector3(0.45, 0.98, -0.2),
  );
  group.add(line(THREE, arc.getPoints(24).map((p) => p.toArray()), palette.accent, true));

  // What the camera sees: a faint cone, a fingertip, its ray and an object.
  const cone = new THREE.Mesh(
    new THREE.ConeGeometry(0.5, 1.5, 32, 1, true),
    new THREE.MeshBasicMaterial({ color: palette.accent, transparent: true, opacity: 0.06, side: THREE.DoubleSide, depthWrite: false }),
  );
  // Apex at the camera lens, opening forward and about 20 degrees down.
  const forward = new THREE.Vector3(0, -0.34, 0.94).normalize();
  cone.position.set(0, 1.68, 0.36).addScaledVector(forward, 0.75);
  cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), forward.clone().negate());
  group.add(cone);

  const tip = new THREE.Mesh(new THREE.SphereGeometry(0.035, 16, 12), new THREE.MeshStandardMaterial({ color: palette.accent }));
  tip.position.set(...FINGERTIP);
  group.add(tip);
  group.add(line(THREE, [FINGERTIP, BOTTLE], palette.accent, true));

  const bottle = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.24, 24), new THREE.MeshStandardMaterial({ color: palette.danger, roughness: 0.4 }));
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.05, 0.1, 24), new THREE.MeshStandardMaterial({ color: palette.paper, roughness: 0.4 }));
  neck.position.y = 0.17;
  bottle.add(body, neck);
  bottle.position.set(BOTTLE[0], BOTTLE[1] - 0.02, BOTTLE[2]);
  group.add(bottle);
  const table = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 0.02, 40), new THREE.MeshStandardMaterial({ color: palette.sunken, roughness: 0.9 }));
  table.position.set(BOTTLE[0], BOTTLE[1] - 0.15, BOTTLE[2]);
  group.add(table);
  return group;
}

/** Scale and centre a loaded model so it occupies the same box as its stand-in. */
function fitTo(THREE, model, standIn) {
  const want = new THREE.Box3().setFromObject(standIn);
  const have = new THREE.Box3().setFromObject(model);
  const wantSize = want.getSize(new THREE.Vector3());
  const haveSize = have.getSize(new THREE.Vector3());
  const longest = Math.max(haveSize.x, haveSize.y, haveSize.z);
  if (!(longest > 0)) throw new Error("Model has no size");
  model.scale.multiplyScalar(Math.max(wantSize.x, wantSize.y, wantSize.z) / longest);
  const centre = new THREE.Box3().setFromObject(model).getCenter(new THREE.Vector3());
  model.position.sub(centre).add(want.getCenter(new THREE.Vector3()));
}

async function loadPart(THREE, loader, baseUrl, name, standIn) {
  const gltf = await loader.loadAsync(`${baseUrl}${name}.glb`);
  const holder = new THREE.Group();
  holder.add(gltf.scene);
  fitTo(THREE, gltf.scene, standIn);
  holder.name = name;
  return holder;
}

/** Names of the generated models that exist, from assets/models/manifest.json. */
async function availableModels(baseUrl) {
  try {
    const response = await fetch(`${baseUrl}manifest.json`);
    if (!response.ok) return new Set();
    const data = await response.json();
    return new Set(Array.isArray(data.models) ? data.models : []);
  } catch {
    return new Set();
  }
}

/**
 * Build the whole kit. Never rejects: any part whose model is missing or
 * broken is replaced by its stand-in and reported through onFallback(name).
 */
export async function loadRig(THREE, { baseUrl, onFallback = () => {} }) {
  const palette = readPalette();
  const rig = new THREE.Group();
  rig.name = "rig";
  let loader = null;
  try {
    const [{ GLTFLoader }, { MeshoptDecoder }] = await Promise.all([
      import("three/addons/loaders/GLTFLoader.js"),
      import("three/addons/libs/meshopt_decoder.module.js"),
    ]);
    loader = new GLTFLoader();
    loader.setMeshoptDecoder(MeshoptDecoder);
  } catch {
    loader = null;
  }
  const available = await availableModels(baseUrl);
  await Promise.all(Object.entries(PART_LAYOUT).map(async ([name, position]) => {
    const standIn = buildStandIn(THREE, name, palette);
    let part = standIn;
    try {
      if (!loader || !available.has(name)) throw new Error("No generated model");
      part = await loadPart(THREE, loader, baseUrl, name, standIn);
    } catch {
      onFallback(name);
    }
    part.position.set(...position);
    rig.add(part);
  }));
  rig.add(extras(THREE, palette));
  return rig;
}
