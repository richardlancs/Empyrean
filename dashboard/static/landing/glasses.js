// A procedural, physically lit model of the Empyrean glasses: acetate frame,
// iridescent lenses and the bridge camera. Built from three.js primitives, no model files.
import * as THREE from "three";

const CURVE = 0.09; // how much the front wraps around the face

/** Trace one lens outline; mirror = -1 for the left eye. */
function lensPath(target, w, h, cx, mirror) {
  const p = (x, y) => [cx + x * mirror, y];
  target.moveTo(...p(-w * 0.5, h * 0.30));
  target.bezierCurveTo(...p(-w * 0.2, h * 0.5), ...p(w * 0.3, h * 0.52), ...p(w * 0.5, h * 0.42));
  target.bezierCurveTo(...p(w * 0.56, h * 0.2), ...p(w * 0.48, -h * 0.3), ...p(w * 0.32, -h * 0.44));
  target.bezierCurveTo(...p(w * 0.12, -h * 0.56), ...p(-w * 0.16, -h * 0.54), ...p(-w * 0.34, -h * 0.38));
  target.bezierCurveTo(...p(-w * 0.48, -h * 0.22), ...p(-w * 0.54, h * 0.12), ...p(-w * 0.5, h * 0.30));
  return target;
}

/** Wrap a front-facing geometry around the face. */
function wrap(geometry) {
  const pos = geometry.attributes.position;
  for (let i = 0; i < pos.count; i += 1) {
    const x = pos.getX(i);
    pos.setZ(i, pos.getZ(i) - CURVE * x * x);
  }
  pos.needsUpdate = true;
  return geometry;
}

/** Dome a lens so reflections sweep across it instead of sitting flat. */
function dome(geometry, cx, rx, ry, depth) {
  const pos = geometry.attributes.position;
  const nrm = geometry.attributes.normal;
  for (let i = 0; i < pos.count; i += 1) {
    const u = (pos.getX(i) - cx) / rx, v = pos.getY(i) / ry;
    pos.setZ(i, pos.getZ(i) + depth * Math.max(0, 1 - u * u - v * v));
    if (nrm.getZ(i) > 0.5) {
      // Tilt the face normal to match the dome so shading sweeps across the lens.
      const n = new THREE.Vector3(u * 0.9, v * 0.9, 1).normalize();
      nrm.setXYZ(i, n.x, n.y, n.z);
    }
  }
  return geometry;
}

function roundedRect(w, h, r) {
  const s = new THREE.Shape();
  s.moveTo(-w / 2 + r, -h / 2);
  s.lineTo(w / 2 - r, -h / 2); s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  s.lineTo(w / 2, h / 2 - r); s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  s.lineTo(-w / 2 + r, h / 2); s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  s.lineTo(-w / 2, -h / 2 + r); s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  return s;
}

/** A studio of soft light boxes, used only for reflections. */
function studio(renderer) {
  const room = new THREE.Scene();
  room.add(new THREE.Mesh(new THREE.BoxGeometry(14, 14, 14), new THREE.MeshBasicMaterial({ color: 0x9a9ca0, side: THREE.BackSide })));
  addPanels(room);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = pmrem.fromScene(room, 0.03).texture;
  pmrem.dispose();
  return env;
}

function addPanels(room) {
  const panel = (w, h, color, strength, position, look) => {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(strength), side: THREE.DoubleSide }));
    mesh.position.set(...position);
    mesh.lookAt(...look);
    room.add(mesh);
  };
  panel(8, 2.4, 0xffffff, 6, [0, 5.5, 1], [0, 0, 0]);    // overhead softbox
  panel(1.2, 7, 0xffffff, 4, [-6, 0.5, 2], [0, 0, 0]);   // left strip
  panel(1.2, 7, 0xffffff, 3, [6, 0.5, -1], [0, 0, 0]);   // right strip
  panel(5, 1.6, 0xffffff, 2.2, [0, -1, 6], [0, 0, 0]);   // low front fill
  panel(1.4, 5, 0xffffff, 5, [3.5, 2.5, 5], [0, 0, 0]);  // diagonal streak across the lenses
  panel(3, 0.5, 0xffffff, 3, [-2.5, 3, 5], [0, 0, 0]);  // edge kick
}

function contactShadow() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const ctx = canvas.getContext("2d");
  const g = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
  g.addColorStop(0, "rgba(0,0,0,.55)"); g.addColorStop(.5, "rgba(0,0,0,.18)"); g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, 256, 256);
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(3.6, 1.5), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false }));
  mesh.rotation.x = -Math.PI / 2;
  return mesh;
}

function buildGlasses() {
  const group = new THREE.Group();
  const acetate = new THREE.MeshPhysicalMaterial({ color: 0x020203, roughness: 0.18, metalness: 0.0, clearcoat: 1, clearcoatRoughness: 0.03, envMapIntensity: 0.7 });
  const metal = new THREE.MeshPhysicalMaterial({ color: 0xd4d9e0, metalness: 1, roughness: 0.22 });
  const hingeMetal = new THREE.MeshPhysicalMaterial({ color: 0x6b727c, metalness: 1, roughness: 0.3 });
  const lensMat = new THREE.MeshPhysicalMaterial({
    color: 0x0a0f16, metalness: 0.85, roughness: 0.06, clearcoat: 1, clearcoatRoughness: 0.02,
    iridescence: 0.25, iridescenceIOR: 1.8, envMapIntensity: 2.2,
  });
  const W = 1.15, H = 0.82, CX = 0.72;
  const bevel = { bevelEnabled: true, bevelThickness: 0.022, bevelSize: 0.022, bevelSegments: 5, curveSegments: 72 };

  for (const m of [-1, 1]) {
    const rim = lensPath(new THREE.Shape(), W + 0.15, H + 0.14, CX * m, m);
    rim.holes.push(lensPath(new THREE.Path(), W, H, CX * m, m));
    group.add(new THREE.Mesh(wrap(new THREE.ExtrudeGeometry(rim, { depth: 0.09, ...bevel })), acetate));

    const lens = new THREE.ExtrudeGeometry(lensPath(new THREE.Shape(), W + 0.02, H + 0.02, CX * m, m),
      { depth: 0.012, bevelEnabled: true, bevelThickness: 0.006, bevelSize: 0.006, bevelSegments: 2, curveSegments: 72 });
    lens.translate(0, 0, 0.02);
    group.add(new THREE.Mesh(wrap(dome(lens, CX * m, W * 0.62, H * 0.62, 0.09)), lensMat));

    // Hinge and temple arm.
    const hx = (CX + (W + 0.15) * 0.52) * m;
    const hz = -CURVE * hx * hx;
    const hinge = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.12, 24), hingeMetal);
    hinge.position.set(hx, 0.18, hz - 0.02);
    group.add(hinge);

    const L = 2.5;
    const arm = new THREE.Shape();
    arm.moveTo(0, 0.055); arm.lineTo(L - 0.65, 0.04);
    arm.quadraticCurveTo(L - 0.2, 0.03, L, -0.34); arm.lineTo(L - 0.06, -0.38);
    arm.quadraticCurveTo(L - 0.28, -0.04, L - 0.65, -0.035); arm.lineTo(0, -0.055); arm.closePath();
    const temple = new THREE.Mesh(new THREE.ExtrudeGeometry(arm, { depth: 0.05, bevelEnabled: true, bevelThickness: 0.014, bevelSize: 0.014, bevelSegments: 4, curveSegments: 32 }), acetate);
    temple.rotation.y = Math.PI / 2 - 0.06 * m; // splay slightly outward
    temple.position.set(hx - 0.025, 0.18, hz - 0.06);
    group.add(temple);
  }

  // Bridge.
  const bridgeCurve = new THREE.CatmullRomCurve3([new THREE.Vector3(-0.16, 0.17, 0.05), new THREE.Vector3(0, 0.27, 0.07), new THREE.Vector3(0.16, 0.17, 0.05)]);
  group.add(new THREE.Mesh(new THREE.TubeGeometry(bridgeCurve, 40, 0.055, 20), acetate));

  // Camera module on the bridge.
  const cam = new THREE.Group();
  const housing = new THREE.ExtrudeGeometry(roundedRect(0.36, 0.26, 0.07), { depth: 0.12, bevelEnabled: true, bevelThickness: 0.035, bevelSize: 0.03, bevelSegments: 6, curveSegments: 24 });
  cam.add(new THREE.Mesh(housing, new THREE.MeshPhysicalMaterial({ color: 0x15181d, metalness: 0.6, roughness: 0.35, clearcoat: 0.6 })));
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.082, 0.014, 20, 64), metal);
  ring.position.z = 0.158;
  cam.add(ring);
  const glass = new THREE.Mesh(new THREE.CircleGeometry(0.075, 64), new THREE.MeshPhysicalMaterial({ color: 0x020305, roughness: 0, clearcoat: 1, iridescence: 0.6, envMapIntensity: 2 }));
  glass.position.z = 0.16;
  cam.add(glass);
  const iris = new THREE.Mesh(new THREE.RingGeometry(0.024, 0.04, 48), new THREE.MeshStandardMaterial({ color: 0x000000, emissive: 0xffffff, emissiveIntensity: 1.2 }));
  iris.position.z = 0.162;
  cam.add(iris);
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.012, 16, 16), new THREE.MeshStandardMaterial({ color: 0x000000, emissive: 0x7dff9c, emissiveIntensity: 3 }));
  led.position.set(0.13, 0.08, 0.158);
  cam.add(led);
  cam.position.set(0, 0.33, 0.0);
  group.add(cam);

  group.position.y = -0.18;
  return { group, iris, led, camera: cam };
}


/** Mount the model in a canvas; returns controls for the page transition. */
export function mountGlasses(canvas, { reduced = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  scene.environment = studio(renderer);
  const key = new THREE.DirectionalLight(0xffffff, 1.4);
  key.position.set(2, 4, 3);
  scene.add(key, new THREE.AmbientLight(0xffffff, 0.5));

  const view = new THREE.PerspectiveCamera(30, 1, 0.05, 100);
  const home = new THREE.Vector3(0, 0.15, 7.2);
  view.position.copy(home);

  const rig = new THREE.Group();
  const { group, iris, led } = buildGlasses();
  rig.add(group);
  const shadow = contactShadow();
  shadow.position.y = -0.8;
  rig.add(shadow);
  scene.add(rig);


  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  window.addEventListener("pointermove", (e) => {
    pointer.tx = (e.clientX / window.innerWidth) * 2 - 1;
    pointer.ty = (e.clientY / window.innerHeight) * 2 - 1;
  });

  function resize() {
    const { clientWidth: w, clientHeight: h } = canvas;
    renderer.setSize(w, h, false);
    view.aspect = w / h;
    view.updateProjectionMatrix();
    const visibleWidth = 2 * home.z * Math.tan(THREE.MathUtils.degToRad(view.fov / 2)) * view.aspect;
    const fit = Math.min(1.15, (visibleWidth * 0.86) / 3.0);
    rig.scale.setScalar(fit);
  }
  window.addEventListener("resize", resize);
  resize();

  let warpStart = 0;
  const clock = new THREE.Clock();
  function frame() {
    const t = clock.getElapsedTime();
    pointer.x += (pointer.tx - pointer.x) * 0.05;
    pointer.y += (pointer.ty - pointer.y) * 0.05;
    const intro = reduced ? 1 : Math.min(1, t / 2.2);
    const ease = 1 - Math.pow(1 - intro, 3);
    rig.rotation.y = -0.5 + (1 - ease) * -1.6 + (reduced ? 0 : Math.sin(t * 0.35) * 0.32 + pointer.x * 0.35);
    rig.rotation.x = 0.14 + (reduced ? 0 : pointer.y * 0.12);
    rig.position.y = 0.35 + (reduced ? 0 : Math.sin(t * 1.1) * 0.05) - (1 - ease) * 0.6;
    group.position.y = -0.18;
    shadow.material.opacity = 0.9 - (reduced ? 0 : Math.sin(t * 1.1) * 0.15);
    iris.material.emissiveIntensity = 0.9 + Math.sin(t * 2.4) * 0.3;
    led.material.emissiveIntensity = (Math.sin(t * 3) > 0.6) ? 4 : 0.6;

    if (warpStart) {
      const k = Math.min(1, (t - warpStart) / 0.9);
      const e = k * k * k;
      rig.rotation.y *= 1 - e;
      rig.rotation.x *= 1 - e;
      view.position.set(0, home.y + e * 0.4, home.z - e * 6.4);
      renderer.toneMappingExposure = 1.05 + e * 1.5;
    }
    view.lookAt(0, 0.3, 0);
    renderer.render(scene, view);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  return {
    warp() { warpStart = clock.getElapsedTime(); },
    reset() { warpStart = 0; view.position.copy(home); renderer.toneMappingExposure = 1.05; },
  };
}
