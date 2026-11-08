/* ==========================================================================
   Navigation behaviour: the mobile sidebar and the drop-down menus.

   The menus themselves are <details> elements, which the browser opens and
   closes on its own - so the Account menu and the Actions menu on each service
   row work even with JavaScript switched off. The only thing JavaScript adds
   is closing an open menu when you click somewhere else or press Escape.
   ========================================================================== */
(function () {
  "use strict";

  var sidebar = document.getElementById("sidebar");
  var backdrop = document.getElementById("sidebarBackdrop");
  var menuButton = document.getElementById("menuButton");

  /* ------------------------- sidebar (mobile only) ------------------------ */
  function setSidebar(open) {
    if (!sidebar || !backdrop || !menuButton) { return; }
    sidebar.classList.toggle("is-open", open);
    backdrop.classList.toggle("is-open", open);
    menuButton.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (sidebar && backdrop && menuButton) {
    menuButton.addEventListener("click", function () {
      setSidebar(!sidebar.classList.contains("is-open"));
    });
    // Tapping the dimmed area behind the sidebar closes it.
    backdrop.addEventListener("click", function () {
      setSidebar(false);
    });
  }

  /* ---------------------------- drop-down menus --------------------------- */
  /* One piece of code for every menu on the site: the Account menu in the top
     bar and the Actions menu on each row of the admin services table. */
  var menus = document.querySelectorAll("details.menu");

  function closeMenus(except) {
    for (var i = 0; i < menus.length; i++) {
      if (menus[i] !== except) {
        menus[i].open = false;
      }
    }
  }

  document.addEventListener("click", function (event) {
    for (var i = 0; i < menus.length; i++) {
      // A click inside an open menu is left alone, so its links and submit
      // buttons still do their job.
      if (menus[i].open && !menus[i].contains(event.target)) {
        menus[i].open = false;
      }
    }
  });

  // Opening one menu closes any other, so only one is ever on screen.
  for (var i = 0; i < menus.length; i++) {
    (function (menu) {
      menu.addEventListener("toggle", function () {
        if (menu.open) { closeMenus(menu); }
      });
    })(menus[i]);
  }

  // Escape closes whatever is open.
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeMenus(null);
      setSidebar(false);
    }
  });
})();
