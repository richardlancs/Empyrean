// Loads one feature entry module and mounts it, independently of the others.
// A feature that fails to load or mount is reported (console + visible message in
// its own mounts); the rest of the dashboard keeps working.

/**
 * @typedef {object} FeatureSpec
 * @property {string} name        "experience" | "operations"
 * @property {string} url         module URL, e.g. "/static/features/experience/index.js"
 * @property {string} exportName  "mountExperience" | "mountOperations"
 * @property {string[]} areas     mount keys this feature owns
 */

/** Error raised when a feature cannot be loaded or mounted. phase: "load" | "mount". */
export class FeatureError extends Error {
  constructor(spec, phase, cause) {
    const what = phase === "load" ? `could not be loaded from ${spec.url}` : `failed while starting`;
    super(`The ${spec.name} feature ${what}`, { cause });
    this.name = "FeatureError";
    this.feature = spec.name;
    this.phase = phase;
  }
}

/**
 * Import spec.url, call its mount export with context, and return
 * { name, status: "mounted" | "failed", cleanup, error }.
 * Never throws; failures go to onError(error, spec) and the result.
 */
export async function loadFeature(spec, { context, importModule = (url) => import(url), onError }) {
  let module;
  try {
    module = await importModule(spec.url);
  } catch (cause) {
    return fail(new FeatureError(spec, "load", cause));
  }
  const mount = module?.[spec.exportName];
  if (typeof mount !== "function") {
    return fail(new FeatureError(spec, "load", new TypeError(`${spec.url} does not export ${spec.exportName}()`)));
  }
  let result;
  try {
    result = await mount(context);
  } catch (cause) {
    return fail(new FeatureError(spec, "mount", cause));
  }
  return { name: spec.name, status: "mounted", cleanup: typeof result === "function" ? result : null, error: null };

  function fail(error) {
    onError?.(error, spec);
    return { name: spec.name, status: "failed", cleanup: null, error };
  }
}
