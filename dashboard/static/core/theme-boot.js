// Classic (non-module) script loaded in <head> before the stylesheets, so the
// saved theme is applied before first paint and there is no flash of the wrong
// theme. Keep the key and values in step with core/preferences.js.
(function () {
  "use strict";
  var theme = "light";
  try {
    var saved = window.localStorage.getItem("empyrean.theme");
    if (saved === '"high-contrast"' || saved === "high-contrast") {
      theme = "high-contrast";
    } else if (saved === null && window.matchMedia && window.matchMedia("(prefers-contrast: more)").matches) {
      theme = "high-contrast";
    }
  } catch (error) {
    // Storage blocked: stay on light. core/preferences.js warns once after load.
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
