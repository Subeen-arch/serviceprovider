/* ==========================================================================
   Show/hide button for password boxes.

   Written as an enhancement rather than as markup in each form: every
   <input type="password"> on the page gets the button, so login, sign-up and
   the change-password form are all covered without repeating anything, and a
   new password field anywhere gets it for free.

   With JavaScript off the forms still work exactly as before - the field is
   simply always hidden, which is the safe default.
   ========================================================================== */

(function () {
  "use strict";

  var EYE =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" ' +
    'stroke="currentColor" stroke-width="2" aria-hidden="true">' +
    '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/>' +
    '<circle cx="12" cy="12" r="3"/></svg>';

  var EYE_OFF =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" ' +
    'stroke="currentColor" stroke-width="2" aria-hidden="true">' +
    '<path d="M17.9 17.9A10.7 10.7 0 0 1 12 19c-7 0-11-7-11-7a19.6 19.6 0 0 1 5.1-5.9"/>' +
    '<path d="M9.9 4.2A10.9 10.9 0 0 1 12 4c7 0 11 7 11 7a19.7 19.7 0 0 1-2.8 3.9"/>' +
    '<path d="M14.1 14.1a3 3 0 1 1-4.2-4.2"/>' +
    '<line x1="2" y1="2" x2="22" y2="22"/></svg>';

  function enhance(input) {
    if (input.dataset.revealReady) { return; }
    input.dataset.revealReady = "1";

    /* Wrap the field so the button can sit inside its right-hand edge. */
    var wrap = document.createElement("span");
    wrap.className = "pw-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var button = document.createElement("button");
    button.type = "button";              // never submits the form
    button.className = "pw-eye";
    button.innerHTML = EYE;
    button.setAttribute("aria-label", "Show password");
    button.setAttribute("aria-pressed", "false");
    button.title = "Show password";
    wrap.appendChild(button);

    button.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      button.innerHTML = showing ? EYE : EYE_OFF;
      button.setAttribute("aria-pressed", showing ? "false" : "true");
      var label = showing ? "Show password" : "Hide password";
      button.setAttribute("aria-label", label);
      button.title = label;

      /* Keep the caret where the person left it. */
      input.focus();
      try {
        var end = input.value.length;
        input.setSelectionRange(end, end);
      } catch (error) {
        /* Some browsers refuse setSelectionRange on a just-switched input. */
      }
    });
  }

  function enhanceAll() {
    var fields = document.querySelectorAll('input[type="password"]');
    Array.prototype.forEach.call(fields, enhance);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceAll);
  } else {
    enhanceAll();
  }
})();
