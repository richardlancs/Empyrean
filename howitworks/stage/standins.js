// Simple-shape stand-ins for each part of the kit. Used until (or instead of)
// a generated model, so the page never waits on an asset.

/** Read the page's design tokens once so the scene matches the dashboard. */
export function readPalette() {
  const style = getComputedStyle(document.documentElement);
  const token = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  return {
    ink: token("--color-text", "#1F1F1F"),
    muted: token("--color-text-secondary", "#57524A"),
    line: token("--color-border-control", "#7A7367"),
    paper: token("--color-surface", "#FFFFFF"),
    sunken: token("--color-surface-sunken", "#F1EDE5"),
    accent: token("--color-accent", "#1947B8"),
    danger: token("--color-danger", "#B42318"),
  };
}

function mesh(THREE, geometry, color, options = {}) {
  const material = new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0.05, ...options });
  return new THREE.Mesh(geometry, material);
}

function at(object, x, y, z) {
  object.position.set(x, y, z);
  return object;
}

function glasses(THREE, palette) {
  const group = new THREE.Group();
  const lens = () => mesh(THREE, new THREE.BoxGeometry(0.27, 0.19, 0.03), palette.ink, { roughness: 0.25 });
  group.add(at(lens(), -0.165, 0, 0), at(lens(), 0.165, 0, 0));
  group.add(at(mesh(THREE, new THREE.BoxGeometry(0.08, 0.03, 0.03), palette.ink), 0, 0.04, 0));
  const arm = () => mesh(THREE, new THREE.BoxGeometry(0.02, 0.025, 0.52), palette.ink);
  group.add(at(arm(), -0.3, 0.05, -0.26), at(arm(), 0.3, 0.05, -0.26));
  // The webcam on the bridge, tilted about 20 degrees down.
  const camera = new THREE.Group();
  camera.add(mesh(THREE, new THREE.BoxGeometry(0.13, 0.08, 0.09), palette.muted));
  const eye = mesh(THREE, new THREE.CylinderGeometry(0.028, 0.028, 0.03, 24), palette.accent, { roughness: 0.2 });
  eye.rotation.x = Math.PI / 2;
  camera.add(at(eye, 0, 0, 0.055));
  camera.rotation.x = 0.35;
  group.add(at(camera, 0, 0.13, 0.03));
  return group;
}

function backpack(THREE, palette) {
  const group = new THREE.Group();
  group.add(mesh(THREE, new THREE.BoxGeometry(0.72, 0.86, 0.32), palette.muted));
  group.add(at(mesh(THREE, new THREE.BoxGeometry(0.5, 0.34, 0.08), palette.line), 0, -0.14, 0.2));
  // The laptop, showing above the open top.
  group.add(at(mesh(THREE, new THREE.BoxGeometry(0.58, 0.2, 0.035), palette.paper, { roughness: 0.3, metalness: 0.4 }), 0, 0.5, 0));
  const strap = () => mesh(THREE, new THREE.BoxGeometry(0.07, 0.8, 0.03), palette.ink);
  group.add(at(strap(), -0.22, 0, 0.19), at(strap(), 0.22, 0, 0.19));
  return group;
}

function speaker(THREE, palette) {
  const group = new THREE.Group();
  const body = mesh(THREE, new THREE.CapsuleGeometry(0.075, 0.12, 6, 16), palette.accent);
  body.rotation.z = Math.PI / 2;
  group.add(body);
  group.add(at(mesh(THREE, new THREE.TorusGeometry(0.035, 0.008, 8, 20), palette.ink), 0.16, 0, 0));
  return group;
}

const BUILDERS = { glasses, backpack, speaker };

/** Build the stand-in for one part: "glasses", "backpack" or "speaker". */
export function buildStandIn(THREE, name, palette = readPalette()) {
  const build = BUILDERS[name];
  if (!build) throw new Error(`Unknown part: ${name}`);
  const group = build(THREE, palette);
  group.name = name;
  return group;
}
