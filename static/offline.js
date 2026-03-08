(function () {
  const STORAGE_KEY = "nova_shipments_v1";
  const ADMIN_USER_KEY = "nova_admin_user";
  const ADMIN_PASS_KEY = "nova_admin_pass";
  const ADMIN_SESSION_KEY = "nova_is_admin";
  const ADMIN_GATE_KEY = "nova_admin_gate_until";

  const STATUS_META = {
    "label-created": { label: "Label Created", progress: 10 },
    "picked-up": { label: "Picked Up", progress: 25 },
    "in-transit": { label: "In Transit", progress: 55 },
    "arrived-hub": { label: "Arrived at Hub", progress: 72 },
    "out-for-delivery": { label: "Out for Delivery", progress: 90 },
    delivered: { label: "Delivered", progress: 100 },
    exception: { label: "Delivery Exception", progress: 65 }
  };

  const SERVICE_ETA_DAYS = {
    "same-day": 0,
    express: 1,
    standard: 3,
    international: 7
  };

  function getShipments() {
    try {
      const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  }

  function setShipments(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  }

  function getAdminUsername() {
    return localStorage.getItem(ADMIN_USER_KEY) || "admin";
  }

  function getAdminPassword() {
    return localStorage.getItem(ADMIN_PASS_KEY) || "admin";
  }

  function isAdmin() {
    return sessionStorage.getItem(ADMIN_SESSION_KEY) === "1";
  }

  function setAdminSession(value) {
    if (value) {
      sessionStorage.setItem(ADMIN_SESSION_KEY, "1");
    } else {
      sessionStorage.removeItem(ADMIN_SESSION_KEY);
    }
  }

  function normalizeLower(value) {
    return String(value || "").trim().toLowerCase();
  }

  function unlockAdminLogin() {
    const expiresAt = Date.now() + 120000;
    sessionStorage.setItem(ADMIN_GATE_KEY, String(expiresAt));
  }

  function isAdminLoginUnlocked() {
    const raw = sessionStorage.getItem(ADMIN_GATE_KEY) || "0";
    const expiresAt = Number(raw);
    return Number.isFinite(expiresAt) && expiresAt > Date.now();
  }

  function bindAdminShortcut() {
    document.addEventListener("keydown", (event) => {
      if (!event.ctrlKey || !event.shiftKey || String(event.key).toLowerCase() !== "a") {
        return;
      }
      event.preventDefault();
      unlockAdminLogin();
      location.href = "admin-login.html";
    });
  }

  function nowISO() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  function makeEta(service) {
    const now = new Date();
    if (service === "same-day") {
      now.setHours(now.getHours() + 6);
      return now.toISOString().replace(/\.\d{3}Z$/, "Z");
    }
    const days = SERVICE_ETA_DAYS[service] ?? 3;
    now.setDate(now.getDate() + days);
    return now.toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  function randomHex(length) {
    const chars = "0123456789ABCDEF";
    let out = "";
    for (let i = 0; i < length; i += 1) {
      out += chars[Math.floor(Math.random() * chars.length)];
    }
    return out;
  }

  function generateTrackingId(existingItems) {
    const d = new Date();
    const datePart = `${String(d.getUTCFullYear()).slice(-2)}${String(d.getUTCMonth() + 1).padStart(2, "0")}${String(d.getUTCDate()).padStart(2, "0")}`;
    for (let i = 0; i < 30; i += 1) {
      const candidate = `FDX-${datePart}-${randomHex(8)}`;
      if (!existingItems.some((s) => s.tracking_id === candidate)) {
        return candidate;
      }
    }
    throw new Error("Could not generate unique tracking ID.");
  }

  function toNum(value, fieldName) {
    const n = Number(value);
    if (!Number.isFinite(n)) {
      throw new Error(`${fieldName} must be a number.`);
    }
    return n;
  }

  function readShipmentForm(form) {
    const fd = new FormData(form);
    const payload = {
      sender_name: String(fd.get("sender_name") || "").trim(),
      sender_email: String(fd.get("sender_email") || "").trim(),
      sender_phone: String(fd.get("sender_phone") || "").trim(),
      origin_label: String(fd.get("origin_label") || "").trim(),
      origin_lat: toNum(fd.get("origin_lat"), "Origin latitude"),
      origin_lng: toNum(fd.get("origin_lng"), "Origin longitude"),
      receiver_name: String(fd.get("receiver_name") || "").trim(),
      receiver_email: String(fd.get("receiver_email") || "").trim(),
      receiver_phone: String(fd.get("receiver_phone") || "").trim(),
      destination_label: String(fd.get("destination_label") || "").trim(),
      destination_lat: toNum(fd.get("destination_lat"), "Destination latitude"),
      destination_lng: toNum(fd.get("destination_lng"), "Destination longitude"),
      package_description: String(fd.get("package_description") || "").trim(),
      weight_kg: toNum(fd.get("weight_kg"), "Weight"),
      service_level: String(fd.get("service_level") || "standard").trim()
    };

    const required = [
      "sender_name",
      "origin_label",
      "receiver_name",
      "destination_label",
      "package_description"
    ];

    for (const key of required) {
      if (!payload[key]) {
        throw new Error(`${key.replace(/_/g, " ")} is required.`);
      }
    }

    if (!Object.prototype.hasOwnProperty.call(SERVICE_ETA_DAYS, payload.service_level)) {
      throw new Error("Service level is invalid.");
    }

    if (payload.weight_kg <= 0) {
      throw new Error("Weight must be greater than 0.");
    }

    return payload;
  }

  function createShipment(payload, createdBy) {
    const items = getShipments();
    const trackingId = generateTrackingId(items);
    const now = nowISO();
    const shipment = {
      id: trackingId,
      tracking_id: trackingId,
      ...payload,
      status: "label-created",
      eta_utc: makeEta(payload.service_level),
      created_by: createdBy,
      created_at_utc: now,
      updated_at_utc: now,
      events: [
        {
          status: "label-created",
          location_label: payload.origin_label,
          note: "Shipment registered and label generated.",
          event_time_utc: now
        }
      ]
    };

    items.unshift(shipment);
    setShipments(items);
    return trackingId;
  }

  function findShipment(trackingId) {
    const normalized = String(trackingId || "").trim().toUpperCase();
    return getShipments().find((s) => s.tracking_id === normalized) || null;
  }

  function updateStatus(form) {
    const fd = new FormData(form);
    const trackingId = String(fd.get("tracking_id") || "").trim().toUpperCase();
    const status = String(fd.get("status") || "").trim();
    let location = String(fd.get("location_label") || "").trim();
    let note = String(fd.get("note") || "").trim();

    if (!STATUS_META[status]) {
      throw new Error("Invalid status selected.");
    }

    const items = getShipments();
    const idx = items.findIndex((s) => s.tracking_id === trackingId);
    if (idx < 0) {
      throw new Error("Tracking ID not found.");
    }

    const ship = items[idx];
    if (!location) {
      location = status === "delivered" ? ship.destination_label : ship.origin_label;
    }
    if (!note) {
      note = `Status changed to ${STATUS_META[status].label} by operations team.`;
    }

    const now = nowISO();
    ship.status = status;
    ship.updated_at_utc = now;
    ship.events.unshift({
      status,
      location_label: location,
      note,
      event_time_utc: now
    });

    items[idx] = ship;
    setShipments(items);

    return { trackingId, label: STATUS_META[status].label };
  }

  function showFlash(message, type) {
    const wrap = document.getElementById("flash-container");
    if (!wrap) return;
    const el = document.createElement("div");
    el.className = `flash flash-${type || "success"}`;
    el.textContent = message;
    wrap.appendChild(el);
  }

  function initHome() {
    const form = document.getElementById("home-track-form");
    if (!form) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const id = String(new FormData(form).get("tracking_id") || "").trim().toUpperCase();
      if (!id) {
        showFlash("Tracking number is required.", "error");
        return;
      }
      location.href = `track.html?id=${encodeURIComponent(id)}`;
    });
  }

  function initShip() {
    const form = document.getElementById("ship-form");
    if (!form) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      try {
        const payload = readShipmentForm(form);
        const id = createShipment(payload, "user");
        location.href = `track.html?id=${encodeURIComponent(id)}&created=1`;
      } catch (error) {
        showFlash(error.message || "Could not create shipment.", "error");
      }
    });
  }

  function initAdminLogin() {
    if (!isAdmin() && !isAdminLoginUnlocked()) {
      location.href = "index.html";
      return;
    }

    const form = document.getElementById("admin-login-form");
    if (!form) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const fd = new FormData(form);
      const user = normalizeLower(fd.get("username"));
      const pass = normalizeLower(fd.get("password"));

      if (user === normalizeLower(getAdminUsername()) && pass === normalizeLower(getAdminPassword())) {
        setAdminSession(true);
        sessionStorage.removeItem(ADMIN_GATE_KEY);
        location.href = "admin.html";
        return;
      }

      showFlash("Invalid admin credentials.", "error");
    });
  }

  function renderAdminTable() {
    const tbody = document.getElementById("admin-shipments-body");
    if (!tbody) return;

    const items = getShipments();
    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6">No shipments yet.</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    for (const item of items) {
      const tr = document.createElement("tr");
      tr.innerHTML = [
        `<td>${escapeHtml(item.tracking_id)}</td>`,
        `<td>${escapeHtml(item.origin_label)}</td>`,
        `<td>${escapeHtml(item.destination_label)}</td>`,
        `<td>${escapeHtml((STATUS_META[item.status] || { label: item.status }).label)}</td>`,
        `<td>${escapeHtml(item.updated_at_utc)}</td>`,
        `<td><a href="track.html?id=${encodeURIComponent(item.tracking_id)}">Open</a></td>`
      ].join("");
      tbody.appendChild(tr);
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function initAdmin() {
    if (!isAdmin()) {
      location.href = "index.html";
      return;
    }

    const logoutBtn = document.getElementById("admin-logout-btn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => {
        setAdminSession(false);
        location.href = "index.html";
      });
    }

    const createForm = document.getElementById("admin-create-form");
    if (createForm) {
      createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        try {
          const payload = readShipmentForm(createForm);
          const id = createShipment(payload, "admin");
          showFlash(`Shipment created by operations team. Tracking ID: ${id}`, "success");
          createForm.reset();
          renderAdminTable();
        } catch (error) {
          showFlash(error.message || "Could not create shipment.", "error");
        }
      });
    }

    const statusForm = document.getElementById("admin-status-form");
    if (statusForm) {
      statusForm.addEventListener("submit", (event) => {
        event.preventDefault();
        try {
          const result = updateStatus(statusForm);
          showFlash(`${result.trackingId} updated to ${result.label}.`, "success");
          statusForm.reset();
          renderAdminTable();
        } catch (error) {
          showFlash(error.message || "Could not update status.", "error");
        }
      });
    }

    renderAdminTable();
  }

  function initTrack() {
    const params = new URLSearchParams(location.search);
    const id = String(params.get("id") || "").trim().toUpperCase();
    const created = params.get("created") === "1";

    const foundSection = document.getElementById("track-found");
    const missingSection = document.getElementById("track-not-found");
    const eventsSection = document.getElementById("track-events");
    const missingLabel = document.getElementById("missing-id-label");

    const lookupForm = document.getElementById("track-lookup-form");
    if (lookupForm) {
      lookupForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const wanted = String(new FormData(lookupForm).get("tracking_id") || "").trim().toUpperCase();
        if (!wanted) {
          showFlash("Tracking number is required.", "error");
          return;
        }
        location.href = `track.html?id=${encodeURIComponent(wanted)}`;
      });
    }

    if (!id) {
      if (missingSection) missingSection.hidden = false;
      return;
    }

    const ship = findShipment(id);
    if (!ship) {
      if (missingLabel) {
        missingLabel.textContent = `${id} was not found`;
      }
      if (missingSection) missingSection.hidden = false;
      return;
    }

    if (created) {
      showFlash(`Shipment created. Tracking ID: ${ship.tracking_id}`, "success");
    }

    if (foundSection) foundSection.hidden = false;
    if (eventsSection) eventsSection.hidden = false;
    if (missingSection) missingSection.hidden = true;

    const meta = STATUS_META[ship.status] || { label: ship.status, progress: 0 };

    setText("tracking-id-title", ship.tracking_id);
    setText("tracking-status-label", meta.label);
    setText("tracking-route", `${ship.origin_label} to ${ship.destination_label}`);
    setText("tracking-sender", ship.sender_name);
    setText("tracking-receiver", ship.receiver_name);
    setText("tracking-weight", `${ship.weight_kg} kg`);
    setText("tracking-service", ship.service_level);
    setText("tracking-description", ship.package_description);
    setText("tracking-eta", ship.eta_utc);
    setText("track-map-line", `Route line: ${ship.origin_label} -> ${ship.destination_label}`);

    const progress = document.getElementById("tracking-progress");
    if (progress) {
      progress.style.width = `${meta.progress}%`;
    }

    renderTimeline(ship.events || []);
    renderRouteMap(ship);
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function renderTimeline(events) {
    const timeline = document.getElementById("timeline-list");
    if (!timeline) return;
    timeline.innerHTML = "";

    if (!events.length) {
      timeline.innerHTML = "<li><div>No tracking events yet.</div></li>";
      return;
    }

    for (const event of events) {
      const li = document.createElement("li");
      const label = (STATUS_META[event.status] || { label: event.status }).label;
      li.innerHTML = `
        <span class="dot on"></span>
        <div>
          <strong>${escapeHtml(label)} - ${escapeHtml(event.note)}</strong><br/>
          <small>${escapeHtml(event.location_label)} - ${escapeHtml(event.event_time_utc)}</small>
        </div>
      `;
      timeline.appendChild(li);
    }
  }

  function renderRouteMap(ship) {
    if (typeof L === "undefined") {
      return;
    }

    const mapEl = document.getElementById("route-map");
    if (!mapEl) return;

    const origin = [ship.origin_lat, ship.origin_lng];
    const destination = [ship.destination_lat, ship.destination_lng];

    const map = L.map("route-map");
    const bounds = L.latLngBounds([origin, destination]);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);

    L.marker(origin).addTo(map).bindPopup(`Origin: ${escapeHtml(ship.origin_label)}`);
    L.marker(destination).addTo(map).bindPopup(`Destination: ${escapeHtml(ship.destination_label)}`);
    L.polyline([origin, destination], { color: "#4d148c", weight: 4, opacity: 0.9 }).addTo(map);

    const meta = STATUS_META[ship.status] || { progress: 0 };
    const t = Math.max(0, Math.min(1, Number(meta.progress || 0) / 100));
    const routePoint = [
      origin[0] + (destination[0] - origin[0]) * t,
      origin[1] + (destination[1] - origin[1]) * t
    ];
    const planeIcon = L.divIcon({
      className: "plane-icon",
      html: "&#9992;",
      iconSize: [30, 30],
      iconAnchor: [15, 15]
    });
    L.marker(routePoint, { icon: planeIcon }).addTo(map).bindPopup("Plane position based on shipment status");

    map.fitBounds(bounds.pad(0.35));
  }

  function initWorldMap() {
    if (typeof L === "undefined") {
      return;
    }

    const map = L.map("world-map", { worldCopyJump: true }).setView([20, 0], 2);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);

    const form = document.getElementById("map-link-form");
    const fromInput = document.getElementById("from-place");
    const toInput = document.getElementById("to-place");
    const feedback = document.getElementById("map-feedback");
    const routeLine = document.getElementById("map-route-line");

    let originMarker = null;
    let destinationMarker = null;
    let activeLine = null;
    let animatedLine = null;
    let planeMarker = null;
    let animationTimer = null;

    async function geocode(place) {
      const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(place)}`;
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error("Geocoding service unavailable.");
      }
      const data = await response.json();
      if (!Array.isArray(data) || data.length === 0) {
        throw new Error(`Place not found: ${place}`);
      }
      return {
        lat: Number(data[0].lat),
        lng: Number(data[0].lon),
        label: data[0].display_name
      };
    }

    function clearRoute() {
      if (animationTimer) {
        cancelAnimationFrame(animationTimer);
        animationTimer = null;
      }
      if (originMarker) map.removeLayer(originMarker);
      if (destinationMarker) map.removeLayer(destinationMarker);
      if (activeLine) map.removeLayer(activeLine);
      if (animatedLine) map.removeLayer(animatedLine);
      if (planeMarker) map.removeLayer(planeMarker);
      originMarker = null;
      destinationMarker = null;
      activeLine = null;
      animatedLine = null;
      planeMarker = null;
    }

    function animateRoute(from, to) {
      const points = [];
      const steps = 150;

      for (let i = 0; i <= steps; i += 1) {
        const t = i / steps;
        points.push([from.lat + (to.lat - from.lat) * t, from.lng + (to.lng - from.lng) * t]);
      }

      activeLine = L.polyline(
        [
          [from.lat, from.lng],
          [to.lat, to.lng]
        ],
        {
          color: "#4d148c",
          weight: 2,
          opacity: 0.35,
          dashArray: "8 8"
        }
      ).addTo(map);

      animatedLine = L.polyline([], {
        color: "#ff6600",
        weight: 4,
        opacity: 0.95
      }).addTo(map);

      const planeIcon = L.divIcon({
        className: "plane-icon",
        html: "&#9992;",
        iconSize: [30, 30],
        iconAnchor: [15, 15]
      });
      planeMarker = L.marker(points[0], { icon: planeIcon }).addTo(map);

      let index = 0;
      const draw = () => {
        if (!animatedLine) return;
        index = Math.min(index + 2, points.length);
        animatedLine.setLatLngs(points.slice(0, index));
        if (planeMarker && index > 0) {
          planeMarker.setLatLng(points[index - 1]);
        }
        if (index < points.length) {
          animationTimer = requestAnimationFrame(draw);
        }
      };

      draw();
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fromPlace = fromInput.value.trim();
      const toPlace = toInput.value.trim();

      if (!fromPlace || !toPlace) {
        feedback.textContent = "Both places are required.";
        if (routeLine) routeLine.textContent = "";
        return;
      }

      feedback.textContent = "Finding places and drawing route...";

      try {
        clearRoute();
        const [from, to] = await Promise.all([geocode(fromPlace), geocode(toPlace)]);

        originMarker = L.marker([from.lat, from.lng]).addTo(map).bindPopup(`From: ${from.label}`);
        destinationMarker = L.marker([to.lat, to.lng]).addTo(map).bindPopup(`To: ${to.label}`);
        map.fitBounds(
          L.latLngBounds([
            [from.lat, from.lng],
            [to.lat, to.lng]
          ]).pad(0.35)
        );

        animateRoute(from, to);
        feedback.textContent = `Route linked: ${from.label} to ${to.label}`;
        if (routeLine) routeLine.textContent = `Line: ${from.label} -> ${to.label}`;
      } catch (error) {
        feedback.textContent = error.message || "Could not link places right now.";
        if (routeLine) routeLine.textContent = "";
      }
    });
  }

  function init() {
    bindAdminShortcut();

    const page = document.body.dataset.page;
    if (page === "portal") {
      location.href = "index.html";
      return;
    }
    if (page === "home") initHome();
    if (page === "ship") initShip();
    if (page === "admin-login") initAdminLogin();
    if (page === "admin") initAdmin();
    if (page === "track") initTrack();
    if (page === "world-map") initWorldMap();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
