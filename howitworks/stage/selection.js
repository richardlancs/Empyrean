// Which hotspot is open. Pure state: no DOM, no three.js.

/**
 * Track one open id out of a fixed set.
 * onChange(current, previous) fires only when the open id really changes.
 */
export function createSelection({ ids, onChange = () => {} }) {
  const known = new Set(ids);
  let current = null;

  function set(next) {
    if (next === current) return;
    const previous = current;
    current = next;
    onChange(current, previous);
  }

  return {
    get current() {
      return current;
    },
    /** Open id, replacing whatever was open. */
    open(id) {
      if (!known.has(id)) throw new RangeError(`Unknown hotspot: ${id}`);
      set(id);
    },
    /** Close whatever is open. */
    close() {
      set(null);
    },
    /** Open id, or close it if it is already open. */
    toggle(id) {
      if (current === id) set(null);
      else this.open(id);
    },
  };
}
