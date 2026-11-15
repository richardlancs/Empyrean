// The 3D stage: renderer, camera, orbit controls, light, idle drift and the
// camera move used by hotspots. Libraries are imported here, on demand, so
// the rest of the page never waits for them.

import { HOME_VIEW } from "../content.js";
import { loadRig } from "./models.js";

const FLY_SECONDS = 0.9;
const DRIFT_RADIANS = 0.1;

/**
 * Create the stage inside host. Rejects when WebGL or the libraries are
 * unavailable; the caller then leaves the static page in place.
 */
export async function createStage(host, { reducedMotion = false, onFallback = () => {} } = {}) {
  const [THREE, { OrbitControls }, { CSS2DRenderer }, { gsap }] = await Promise.all([
    import("three"),
    import("three/addons/controls/OrbitControls.js"),
    import("three/addons/renderers/CSS2DRenderer.js"),
    import("gsap"),
  ]);

  const probe = document.createElement("canvas");
  if (!(probe.getContext("webgl2") || probe.getContext("webgl"))) {
    throw new Error("WebGL is not available");
  }
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.domElement.setAttribute("aria-hidden", "true");
  host.append(renderer.domElement);

  const labels = new CSS2DRenderer();
  labels.domElement.className = "how-stage__labels";
  host.append(labels.domElement);

  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0xd9d2c4, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 1.8);
  key.position.set(3, 5, 4);
  scene.add(key);

  // A soft blob on the ground instead of real shadows: cheap and calm.
  const blob = document.createElement("canvas");
  blob.width = blob.height = 128;
  const ctx = blob.getContext("2d");
  const fade = ctx.createRadialGradient(64, 64, 4, 64, 64, 64);
  fade.addColorStop(0, "rgba(31,31,31,0.22)");
  fade.addColorStop(1, "rgba(31,31,31,0)");
  ctx.fillStyle = fade;
  ctx.fillRect(0, 0, 128, 128);
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(4.4, 4.4),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(blob), transparent: true, depthWrite: false }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(0, 0.2, 0.3);
  scene.add(ground);

  const rig = await loadRig(THREE, { baseUrl: new URL("../assets/models/", import.meta.url).href, onFallback });
  scene.add(rig);

  const camera = new THREE.PerspectiveCamera(34, 16 / 9, 0.1, 50);
  camera.position.set(...HOME_VIEW.position);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(...HOME_VIEW.target);
  controls.enablePan = false;
  controls.enableZoom = false; // the wheel scrolls the page, not the model
  controls.enableDamping = !reducedMotion;
  controls.minDistance = 1.6;
  controls.maxDistance = 7;
  controls.maxPolarAngle = Math.PI * 0.5;
  controls.update();

  const frameListeners = new Set();
  let idle = false;
  let idleStart = 0;
  let idleBase = null;
  let running = false;
  let frameId = 0;
  let onScreen = true;
  let tween = null;
  let destroyed = false;

  function resize() {
    const width = host.clientWidth || 1;
    const height = host.clientHeight || 1;
    renderer.setSize(width, height, false);
    labels.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  function render(now) {
    if (idle && idleBase) {
      const angle = Math.sin((now - idleStart) / 4000) * DRIFT_RADIANS;
      const offset = idleBase.clone().applyAxisAngle(THREE.Object3D.DEFAULT_UP, angle);
      camera.position.copy(controls.target).add(offset);
    }
    controls.update();
    renderer.render(scene, camera);
    labels.render(scene, camera);
    for (const listener of frameListeners) listener(camera);
  }

  function loop(now) {
    if (!running) return;
    render(now);
    frameId = requestAnimationFrame(loop);
  }

  function syncRunning() {
    const should = !destroyed && onScreen && !document.hidden;
    if (should && !running) {
      running = true;
      frameId = requestAnimationFrame(loop);
    } else if (!should && running) {
      running = false;
      cancelAnimationFrame(frameId);
    }
  }

  function setIdle(on) {
    idle = Boolean(on) && !reducedMotion;
    if (idle) {
      idleStart = performance.now();
      idleBase = camera.position.clone().sub(controls.target);
    }
  }

  /** Move the camera to a saved view. A new call replaces one in flight. */
  function flyTo(view, { instant = false } = {}) {
    setIdle(false);
    if (tween) tween.kill();
    tween = null;
    const apply = (p) => {
      camera.position.set(p.px, p.py, p.pz);
      controls.target.set(p.tx, p.ty, p.tz);
    };
    const goal = {
      px: view.position[0], py: view.position[1], pz: view.position[2],
      tx: view.target[0], ty: view.target[1], tz: view.target[2],
    };
    if (instant || reducedMotion) {
      apply(goal);
      controls.update();
      return Promise.resolve();
    }
    const state = {
      px: camera.position.x, py: camera.position.y, pz: camera.position.z,
      tx: controls.target.x, ty: controls.target.y, tz: controls.target.z,
    };
    return new Promise((resolve) => {
      const mine = gsap.to(state, {
        ...goal,
        duration: FLY_SECONDS,
        ease: "power2.inOut",
        onUpdate: () => apply(state),
        onComplete: resolve,
        onInterrupt: resolve,
      });
      tween = mine;
    });
  }

  const stopIdle = () => setIdle(false);
  controls.addEventListener("start", stopIdle);
  host.addEventListener("keydown", stopIdle);
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(host);
  const viewObserver = new IntersectionObserver(([entry]) => {
    onScreen = entry.isIntersecting;
    syncRunning();
  });
  viewObserver.observe(host);
  document.addEventListener("visibilitychange", syncRunning);

  resize();
  setIdle(true);
  syncRunning();
  render(performance.now());

  return {
    THREE,
    scene,
    camera,
    canvas: renderer.domElement,
    labelRoot: labels.domElement,
    center: new THREE.Vector3(0, 1.0, 0.2),
    flyTo,
    setIdle,
    /** Call fn(camera) after every rendered frame. Returns an unsubscribe. */
    onFrame(fn) {
      frameListeners.add(fn);
      return () => frameListeners.delete(fn);
    },
    destroy() {
      destroyed = true;
      syncRunning();
      if (tween) tween.kill();
      controls.removeEventListener("start", stopIdle);
      host.removeEventListener("keydown", stopIdle);
      resizeObserver.disconnect();
      viewObserver.disconnect();
      document.removeEventListener("visibilitychange", syncRunning);
      controls.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      labels.domElement.remove();
    },
  };
}
