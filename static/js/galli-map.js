/* ==========================================================================
   Galli Maps integration.

   Two things are needed anywhere in the app:
     1. picking a location  -> initLocationPicker()
     2. showing the route Dijkstra produced -> initRouteMap()

   The access token is rendered into the page by Flask (it comes from .env),
   and the address lookup goes through our own /api/reverse-geocode route so
   the token is not put into a URL the browser fetches directly.
   ========================================================================== */

(function () {
  "use strict";

  /* The plugin builds its map asynchronously, so anything drawn on the map has
     to wait until the map object actually exists. */
  function whenMapReady(plugin, callback, attempt) {
    attempt = attempt || 0;
    var ready = plugin && plugin.map && typeof plugin.map.getCanvas === "function";
    if (ready) {
      callback();
    } else if (attempt < 60) {
      setTimeout(function () { whenMapReady(plugin, callback, attempt + 1); }, 100);
    }
  }

  function createPlugin(options) {
    if (typeof window.GalliMapPlugin !== "function") {
      return null;
    }
    try {
      return new window.GalliMapPlugin(options);
    } catch (error) {
      console.error("Galli Maps failed to start:", error);
      return null;
    }
  }

  function showMapError(containerId, message) {
    var box = document.getElementById(containerId);
    if (box) {
      box.className = "map-missing";
      box.textContent = message;
    }
  }

  /* ----------------------------------------------------------------------
     Location picker: click the map, drop a marker, fill the hidden inputs.
     ---------------------------------------------------------------------- */
  window.initLocationPicker = function (config) {
    var latInput = document.getElementById(config.latInput);
    var lngInput = document.getElementById(config.lngInput);
    var addressInput = config.addressInput
      ? document.getElementById(config.addressInput)
      : null;
    var status = document.getElementById(config.statusId);
    var marker = null;
    var plugin = null;

    function setStatus(html) {
      if (status) { status.innerHTML = html; }
    }

    /* Ask our own Flask route what this point is called. */
    function lookupAddress(lat, lng) {
      fetch("/api/reverse-geocode?lat=" + lat + "&lng=" + lng)
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (data.ok && data.address) {
            if (addressInput && !addressInput.dataset.userEdited) {
              addressInput.value = data.address;
            }
            setStatus(
              "<strong>Selected:</strong> " + escapeHtml(data.address) +
              "<br><small>" + lat.toFixed(5) + ", " + lng.toFixed(5) + "</small>"
            );
          } else {
            setStatus(
              "<strong>Location selected.</strong><br><small>" +
              lat.toFixed(5) + ", " + lng.toFixed(5) +
              " &middot; address name unavailable</small>"
            );
          }
        })
        .catch(function () {
          setStatus(
            "<strong>Location selected.</strong><br><small>" +
            lat.toFixed(5) + ", " + lng.toFixed(5) + "</small>"
          );
        });
    }

    function select(lat, lng) {
      latInput.value = lat.toFixed(6);
      lngInput.value = lng.toFixed(6);

      if (marker && plugin) {
        try { plugin.removePinMarker(marker); } catch (e) { /* already gone */ }
      }
      if (plugin) {
        marker = plugin.displayPinMarker({
          color: "#0f766e",
          draggable: false,
          latLng: [lat, lng]
        });
      }
      if (config.onSelect) { config.onSelect(lat, lng); }
      setStatus("<strong>Looking up address...</strong>");
      lookupAddress(lat, lng);
    }

    if (!config.token) {
      showMapError(
        config.container,
        "The map is not configured. Add GALLI_ACCESS_TOKEN to your .env file."
      );
      return;
    }

    plugin = createPlugin({
      accessToken: config.token,
      map: {
        container: config.container,
        center: [config.center[0], config.center[1]],
        zoom: config.zoom || 13,
        maxZoom: 19,
        minZoom: 10,
        clickable: true
      },
      pano: { container: "pano" },
      customClickFunctions: [function (event) {
        if (event && event.lngLat) {
          select(event.lngLat.lat, event.lngLat.lng);
        }
      }]
    });

    if (!plugin) {
      showMapError(config.container, "The map could not be loaded. Check your internet connection.");
      return;
    }

    /* If the form is being redisplayed, put the marker back where it was. */
    whenMapReady(plugin, function () {
      var existingLat = parseFloat(latInput.value);
      var existingLng = parseFloat(lngInput.value);
      if (!isNaN(existingLat) && !isNaN(existingLng)) {
        marker = plugin.displayPinMarker({
          color: "#0f766e", draggable: false, latLng: [existingLat, existingLng]
        });
      }
    });

    if (addressInput) {
      addressInput.addEventListener("input", function () {
        addressInput.dataset.userEdited = "1";
      });
    }
  };

  /* ----------------------------------------------------------------------
     Place map: one marker, one place. Used by the admin to look at where a
     single provider works from. There is no route and no second point, so it
     needs none of the routing machinery below.
     ---------------------------------------------------------------------- */
  window.initPlaceMap = function (config) {
    if (!config.token) {
      showMapError(config.container,
                   "The map is not configured. Add GALLI_ACCESS_TOKEN to your .env file.");
      return;
    }

    var lat = parseFloat(config.lat);
    var lng = parseFloat(config.lng);
    if (isNaN(lat) || isNaN(lng)) {
      showMapError(config.container, "This provider has no location saved.");
      return;
    }

    var plugin = createPlugin({
      accessToken: config.token,
      map: {
        container: config.container,
        center: [lat, lng],
        zoom: config.zoom || 16,
        maxZoom: 19,
        minZoom: 9
      },
      pano: { container: "pano" }
    });

    if (!plugin) {
      showMapError(config.container,
                   "The map could not be loaded. Check your internet connection.");
      return;
    }

    whenMapReady(plugin, function () {
      plugin.displayPinMarker({
        color: config.color || "#0f766e",
        draggable: false,
        latLng: [lat, lng]
      });
    });
  };

  /* ----------------------------------------------------------------------
     Route map: draws the path Dijkstra returned, plus the two end markers.
     ---------------------------------------------------------------------- */
  window.initRouteMap = function (config) {
    if (!config.token) {
      showMapError(config.container, "The map is not configured. Add GALLI_ACCESS_TOKEN to your .env file.");
      return;
    }
    if (!config.points || config.points.length < 2) {
      showMapError(config.container, "No route is available to display.");
      return;
    }

    var start = config.points[0];
    var end = config.points[config.points.length - 1];
    var centre = {
      lat: (start.lat + end.lat) / 2,
      lng: (start.lng + end.lng) / 2
    };
    var status = config.statusId ? document.getElementById(config.statusId) : null;

    function setStatus(html, kind) {
      if (!status) { return; }
      status.innerHTML = html;
      status.className = kind === "error" ? "alert alert-error" : "map-status";
    }

    var plugin = createPlugin({
      accessToken: config.token,
      map: {
        container: config.container,
        center: [centre.lat, centre.lng],
        zoom: config.zoom || 12,
        maxZoom: 19,
        minZoom: 9
      },
      pano: { container: "pano" }
    });

    if (!plugin) {
      showMapError(config.container, "The map could not be loaded. Check your internet connection.");
      return;
    }

    whenMapReady(plugin, function () {
      /* The two ends are always shown, whether or not a route can be found. */
      plugin.displayPinMarker({ color: "#1d4ed8", draggable: false, latLng: [start.lat, start.lng] });
      plugin.displayPinMarker({ color: "#b91c1c", draggable: false, latLng: [end.lat, end.lng] });
      fitTo(plugin, [[start.lat, start.lng], [end.lat, end.lng]]);

      setStatus("Finding the road route&hellip;");

      /* The road geometry comes from the routing engine through our own Flask
         route. If it cannot produce one, the markers stay and the customer is
         told - a straight line between the two points is never drawn, because
         that would not be a real route. */
      var url = "/api/route?srcLat=" + start.lat + "&srcLng=" + start.lng +
                "&dstLat=" + end.lat + "&dstLng=" + end.lng;

      fetch(url)
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (!data.ok) {
            setStatus("Road route unavailable: " + escapeHtml(data.error || "unknown problem") +
                      " Both locations are still shown on the map.", "error");
            return;
          }

          /* Start and end are the same place - there is no line to draw, so
             say that instead of drawing a zero-length route. */
          if (data.same_location) {
            setStatus("<strong>Same location.</strong> The job address is the " +
                      "provider's own address, so there is no route to travel.");
            return;
          }

          /* GeoJSON wants [longitude, latitude]; the API gave us [lat, lng]. */
          var coordinates = data.points.map(function (p) { return [p[1], p[0]]; });

          drawRouteLine(plugin.map, coordinates);
          fitTo(plugin, data.points);

          setStatus(
            "<strong>" + data.distance_km + " km by road</strong> &middot; about " +
            data.duration_min + " min driving" +
            "<br><small>Route geometry from the Galli routing engine (" +
            data.points.length + " points along real roads).</small>"
          );
        })
        .catch(function () {
          setStatus("Could not reach the routing service. Both locations are " +
                    "still shown on the map.", "error");
        });
    });
  };

  /* Draw the road route as a line on the map.

     The plugin's own drawPolygon() is not used here. It only draws when
     map.loaded() is true, and otherwise waits for the map's "load" event - but
     by the time the route has come back from /api/route that event has already
     been and gone, so the line was never drawn and only the two markers
     appeared. Adding the source and layer here does exactly what drawPolygon
     does internally, without that wait.

     Named constants so redrawing replaces the old line instead of stacking a
     new one on top of it. */
  var ROUTE_SOURCE = "road-route-source";
  var ROUTE_LAYER = "road-route-line";

  function drawRouteLine(map, coordinates, attempt) {
    attempt = attempt || 0;
    try {
      if (map.getLayer(ROUTE_LAYER)) { map.removeLayer(ROUTE_LAYER); }
      if (map.getSource(ROUTE_SOURCE)) { map.removeSource(ROUTE_SOURCE); }

      map.addSource(ROUTE_SOURCE, {
        type: "geojson",
        data: {
          type: "Feature",
          geometry: { type: "LineString", coordinates: coordinates }
        }
      });
      map.addLayer({
        id: ROUTE_LAYER,
        type: "line",
        source: ROUTE_SOURCE,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#0f766e",
          "line-width": 6,
          "line-opacity": 0.9
        }
      });
      return true;
    } catch (error) {
      /* The map style was not finished yet, which is the one case where
         adding a layer is rejected. Wait a moment and try again. */
      if (attempt < 50) {
        setTimeout(function () {
          drawRouteLine(map, coordinates, attempt + 1);
        }, 100);
        return true;
      }
      console.error("Could not draw the route line:", error);
      return false;
    }
  }

  /* Zoom and pan so the whole route fits on screen. */
  function fitTo(plugin, latLngPairs) {
    try {
      var minLat = 90, maxLat = -90, minLng = 180, maxLng = -180;
      latLngPairs.forEach(function (p) {
        minLat = Math.min(minLat, p[0]); maxLat = Math.max(maxLat, p[0]);
        minLng = Math.min(minLng, p[1]); maxLng = Math.max(maxLng, p[1]);
      });
      plugin.map.fitBounds(
        [[minLng, minLat], [maxLng, maxLat]],
        { padding: 50, duration: 0 }
      );
    } catch (error) {
      /* Not fatal - the map simply keeps its initial view. */
      console.warn("Could not fit the map to the route:", error);
    }
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
})();
