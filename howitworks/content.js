// All copy and data for the How It Works page. One place to edit.
// Figures and message names follow SPEC.md sections 2, 3, 4.6, 5 and 7.

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const key of Object.keys(value)) deepFreeze(value[key]);
  }
  return value;
}

/** Camera position and look-at target when nothing is selected. */
export const HOME_VIEW = deepFreeze({ position: [2.6, 1.9, 3.4], target: [0, 1.0, 0.3] });

/** The five parts of the rig a visitor can open. anchor/view are scene coordinates. */
export const HOTSPOTS = deepFreeze([
  {
    id: "camera",
    label: "Camera",
    does: "Sees the objects and hands in front of the wearer.",
    builtWith: "Logitech webcam, OpenCV, YOLO11s with ByteTrack, MediaPipe Hands",
    number: "5 frames a second at 640 x 360",
    stepId: "frame",
    anchor: [0, 1.66, 0.42],
    view: { position: [0.9, 1.9, 1.5], target: [0, 1.55, 0.3] },
  },
  {
    id: "pointing",
    label: "Pointing",
    does: "Works out which object the wearer's finger is pointing at.",
    builtWith: "A ray from the extended finger and a small state machine",
    number: "Speech starts within 1 second",
    stepId: "touch",
    anchor: [0.3, 1.08, 1.0],
    view: { position: [1.5, 1.5, 2.2], target: [0.2, 1.0, 1.2] },
  },
  {
    id: "laptop",
    label: "Laptop",
    does: "Runs everything as one program, names objects and keeps a history.",
    builtWith: "Python message bus, Grok vision, Tiger Data",
    number: "A name is stored within 2 seconds of an object settling",
    stepId: "name-request",
    anchor: [0, 1.12, -0.62],
    view: { position: [1.3, 1.7, -1.9], target: [0, 0.7, -0.6] },
  },
  {
    id: "speaker",
    label: "Speaker",
    does: "Says the object's name. The alarm interrupts everything else.",
    builtWith: "pyttsx3 offline speech, pygame alarm tone, JBL Go 3",
    number: "The alarm always outranks speech",
    stepId: "outputs",
    anchor: [0.48, 0.98, -0.2],
    view: { position: [1.7, 1.2, 0.7], target: [0.4, 0.9, -0.25] },
  },
  {
    id: "hazard",
    label: "Hazard watch",
    does: "Checks every frame for things worth a warning, on its own path.",
    builtWith: "YOLO classes plus a Grok vision check",
    number: "Alarm within 0.5 seconds (fast tier) or 3 seconds",
    stepId: "hazard-frame",
    anchor: [-0.55, 1.42, 1.25],
    view: { position: [-1.9, 1.9, 2.4], target: [-0.2, 1.3, 0.9] },
  },
]);

/** Pipeline nodes: five on the main line, three branches. */
export const NODES = deepFreeze([
  { id: "camera", label: "Camera" },
  { id: "vision", label: "Vision" },
  { id: "scene", label: "Scene" },
  { id: "namer", label: "Grok namer" },
  { id: "audio", label: "Audio" },
  { id: "hazard", label: "Hazard" },
  { id: "storage", label: "Tiger Data" },
  { id: "dashboard", label: "Dashboard" },
]);

/** One touch, from camera to speaker. */
export const TOUCH_STEPS = deepFreeze([
  {
    id: "capture",
    from: "camera",
    to: ["vision"],
    message: null,
    caption: "The camera on the glasses streams video. Vision processes 5 frames every second.",
  },
  {
    id: "frame",
    from: "vision",
    to: ["scene"],
    message: "FrameResult",
    caption: "For each frame, Vision publishes the image, the tracked objects and the fingertip positions.",
  },
  {
    id: "name-request",
    from: "scene",
    to: ["namer"],
    message: "NameRequest",
    caption: "When a new object has been steady for 1 second, Scene sends a crop of it to be named.",
  },
  {
    id: "name-result",
    from: "namer",
    to: ["scene"],
    message: "NameResult",
    caption: "Grok looks at the crop and replies with a specific name, which Scene stores on the object.",
  },
  {
    id: "touch",
    from: "scene",
    to: ["audio", "storage", "dashboard"],
    message: "TouchEvent",
    caption: "The wearer points. After 0.4 seconds on the same object, Scene announces the touch.",
  },
  {
    id: "outputs",
    from: "audio",
    to: ["storage", "dashboard"],
    message: null,
    caption: "The speaker says the name, Tiger Data logs it and the dashboard highlights the object.",
  },
]);

/** The parallel hazard path. */
export const HAZARD_STEPS = deepFreeze([
  {
    id: "hazard-frame",
    from: "vision",
    to: ["hazard"],
    message: "FrameResult",
    caption: "Every frame also goes to the hazard detector, which never waits behind anything else.",
  },
  {
    id: "hazard-event",
    from: "hazard",
    to: ["audio", "storage", "dashboard"],
    message: "HazardEvent",
    caption: "On a hazard, the alarm cuts in ahead of any speech. This is a prototype warning, not a guarantee.",
  },
]);
