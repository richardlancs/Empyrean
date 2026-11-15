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
    does: "Watches the camera feed for things worth a warning, on its own path.",
    builtWith: "YOLO classes plus a Grok vision check",
    number: "Alarm within 0.5 seconds (fast tier) or 3 seconds",
    stepId: "hazard-frame",
    anchor: [-0.55, 1.42, 1.25],
    view: { position: [-1.9, 1.9, 2.4], target: [-0.2, 1.3, 0.9] },
  },
]);

/** Pipeline modules, each with the role it plays and what it is built with. */
export const NODES = deepFreeze([
  {
    id: "camera",
    label: "Camera",
    role: "The eyes. A webcam on the glasses streams what is in front of the wearer.",
    description: "Mounted on the bridge of the sunglasses and angled slightly down, the camera keeps nearby objects and the wearer's hands in the same view. A USB cable carries the video to the laptop in the backpack. OpenCV captures the images; the camera itself does not identify objects or decide what to say.",
    tech: "Logitech USB webcam, OpenCV",
  },
  {
    id: "vision",
    label: "Vision",
    role: "Finds objects and fingertips in 5 frames every second and follows them from frame to frame.",
    description: "Each processed image is resized to 640 by 360 pixels. YOLO finds objects, ByteTrack gives them consistent IDs across frames, and MediaPipe locates the hands and finger joints. Vision publishes these together as a FrameResult, so both scene tracking and hazard detection can work from the same image without waiting for one another.",
    tech: "YOLO11s, ByteTrack, MediaPipe Hands",
  },
  {
    id: "scene",
    label: "Scene",
    role: "The memory. Keeps track of every object in view and decides when a finger is pointing at one.",
    description: "Scene keeps an object's name and state attached to its tracking ID, including briefly after a hand hides it from the camera. A steady new object produces a NameRequest. An extended finger casts a ray toward the objects; pointing at the same one for two processed frames produces a TouchEvent. Letting go and pointing again creates a fresh announcement.",
    tech: "In-memory state and a small state machine",
  },
  {
    id: "namer",
    label: "Grok namer",
    role: "Gives each object a specific name, such as a brand, and answers spoken questions about the scene.",
    description: "When Scene requests a name, a background worker sends Grok a crop of that object. It asks for a short name and includes a brand only when the printed label is readable. The NameResult returns to Scene for future touches. A separate worker answers questions using the current full image, keeping those requests independent of object naming and hazard detection.",
    tech: "Grok vision over the Grok API",
  },
  {
    id: "audio",
    label: "Audio",
    role: "The voice. Speaks names and answers; the alarm always plays ahead of speech.",
    description: "Audio turns touch announcements and requested answers into speech on the laptop, then plays them through the Bluetooth speaker. Speech runs offline. A HazardEvent interrupts the current phrase and clears waiting speech so the warning can play immediately. The queue keeps only one waiting phrase, preventing old descriptions from building up behind newer events.",
    tech: "Offline text to speech, pygame alarm tone",
  },
  {
    id: "hazard",
    label: "Hazard",
    role: "Watches the feed for things worth a warning, on a path nothing else can delay.",
    description: "Two checks run alongside the touch flow. A local check looks for vehicle boxes growing quickly in the image. A background Grok check looks for an immediate stair edge, drop, vehicle or obstacle in the walking path. A positive check publishes a HazardEvent to audio, storage and the dashboard. One webcam cannot measure distance, and the checks can miss hazards.",
    tech: "YOLO classes plus a Grok vision check",
  },
  {
    id: "storage",
    label: "Tiger Data",
    role: "The history. Logs every touch and warning so the wearer can ask where something was last touched.",
    description: "A background worker records touch and hazard events with their timestamps in Tiger Data. Touch records include the object's name and nearby objects, giving a later search some context. An explicit last-touch or last-seen question searches those records and returns the most recent match. If the database is unavailable, the rest of the app continues running.",
    tech: "Tiger Data (Postgres time series)",
  },
  {
    id: "dashboard",
    label: "Dashboard",
    role: "Shows a helper the live feed, the objects in view and what is being touched.",
    description: "FastAPI serves the page from the laptop. An MJPEG stream carries the camera view, while one WebSocket updates the object list, touch state, recent events and module status. Typed or transcribed questions become messages on the same bus as the other modules. The page reflects the running system; the wearer receives names and answers through the speaker.",
    tech: "FastAPI, MJPEG video, one WebSocket",
  },
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
    caption: "The hazard detector publishes a HazardEvent to audio, storage and the dashboard.",
  },
]);
