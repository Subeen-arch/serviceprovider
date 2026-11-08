/* ==========================================================================
   Ask why a booking is being cancelled.

   The Cancel button is an ordinary submit button inside an ordinary form. This
   file steps in front of it, shows the reason box, writes the answer into the
   form's hidden `reason` field and then lets the form go. With JavaScript off
   nothing here runs, the browser's own confirm() asks instead, and the booking
   is cancelled with an empty reason - which the server already allows.
   ========================================================================== */
(function () {
  "use strict";

  var dialog = document.getElementById("cancel-dialog");
  var forms = document.querySelectorAll("form[data-cancel-booking]");
  if (!dialog || !forms.length || typeof dialog.showModal !== "function") {
    return;   // old browser: the confirm() fallback stays in charge
  }

  var what = document.getElementById("cancel-what");
  var note = document.getElementById("cancel-note");
  var pending = null;         // the form waiting for an answer

  // The confirm() in the markup is only there for the no-JavaScript case, so
  // remove it now that the reason box is going to do the asking.
  for (var i = 0; i < forms.length; i++) {
    forms[i].removeAttribute("onsubmit");
    forms[i].addEventListener("submit", function (event) {
      var form = event.currentTarget;
      if (form.dataset.confirmed === "yes") {
        return;               // second time round: let it post
      }
      event.preventDefault();
      open(form);
    });
  }

  function open(form) {
    pending = form;
    what.textContent =
      "Booking #" + form.dataset.cancelBooking + " for " +
      form.dataset.service + " with " + form.dataset.provider +
      ". This cannot be undone.";

    // Start from a clean box each time it is opened.
    var chosen = dialog.querySelectorAll('input[name="chosen"]');
    for (var i = 0; i < chosen.length; i++) { chosen[i].checked = false; }
    note.value = "";

    dialog.showModal();
  }

  dialog.addEventListener("close", function () {
    if (!pending || dialog.returnValue !== "confirm") {
      pending = null;
      return;
    }

    var picked = dialog.querySelector('input[name="chosen"]:checked');
    var reason = picked ? picked.value : "";
    if (reason === "other") { reason = ""; }

    var extra = note.value.trim();
    if (reason && extra) {
      reason = reason + " - " + extra;
    } else if (extra) {
      reason = extra;
    }

    pending.querySelector('input[name="reason"]').value = reason.slice(0, 200);
    pending.dataset.confirmed = "yes";
    pending.submit();
    pending = null;
  });
})();
