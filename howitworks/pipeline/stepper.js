// Step index and play/pause for a fixed list of steps. Pure state: no DOM.

/**
 * Create a stepper.
 * onChange(index, step) fires when the index really changes.
 * onPlayingChange(playing) fires when play starts or stops.
 */
export function createStepper({
  steps,
  onChange = () => {},
  onPlayingChange = () => {},
  intervalMs = 2500,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
}) {
  const last = steps.length - 1;
  let index = 0;
  let playing = false;
  let timer = null;

  function move(next) {
    if (next === index) return;
    index = next;
    onChange(index, steps[index]);
  }

  function cancel() {
    if (timer !== null) clearTimer(timer);
    timer = null;
  }

  function setPlaying(value) {
    if (playing === value) return;
    playing = value;
    onPlayingChange(playing);
  }

  function pause() {
    cancel();
    setPlaying(false);
  }

  function schedule() {
    timer = setTimer(() => {
      timer = null;
      move(Math.min(index + 1, last));
      if (index >= last) setPlaying(false);
      else schedule();
    }, intervalMs);
  }

  return {
    get index() {
      return index;
    },
    get playing() {
      return playing;
    },
    /** Go forward one step; stays on the last. */
    next() {
      pause();
      move(Math.min(index + 1, last));
    },
    /** Go back one step; stays on the first. */
    back() {
      pause();
      move(Math.max(index - 1, 0));
    },
    /** Go to step i. Throws RangeError when i is not a step. */
    goTo(i) {
      if (!Number.isInteger(i) || i < 0 || i > last) throw new RangeError(`No step ${i}`);
      pause();
      move(i);
    },
    /** Go to the first step that involves nodeId; no change if none does. */
    jumpToNode(nodeId) {
      pause();
      const found = steps.findIndex((step) => step.from === nodeId || step.to.includes(nodeId));
      if (found >= 0) move(found);
    },
    /** Run through the steps, restarting from the first if already at the end. */
    play() {
      cancel();
      if (index >= last) move(0);
      if (last === 0) return;
      setPlaying(true);
      schedule();
    },
    pause,
    destroy() {
      cancel();
      playing = false;
    },
  };
}
