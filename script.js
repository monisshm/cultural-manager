"use strict";

const state = { user: null, events: [], updates: [], reports: [], toastTimer: null };
const roleNames = { admin: "Admin", organizer: "Organizer", participant: "Participant", volunteer: "Volunteer" };
const viewTitles = { dashboard: "Overview", events: "Events", schedule: "Schedule", announcements: "Updates & results", reports: "Reports" };
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status}).`);
  return payload;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.remove("hidden");
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => toast.classList.add("hidden"), 3600);
}

function setFormMessage(element, message = "") {
  element.textContent = message;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function formatDate(value) {
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function canManage(event) {
  return state.user && (state.user.role === "admin" || (state.user.role === "organizer" && event.created_by === state.user.id));
}

function isManager() {
  return state.user && ["admin", "organizer"].includes(state.user.role);
}

async function loadApp() {
  const data = await api("/api/me");
  state.user = data.user;
  $("#login-screen").classList.add("hidden");
  $("#app-shell").classList.remove("hidden");
  $("#profile-name").textContent = state.user.name;
  $("#profile-role").textContent = roleNames[state.user.role];
  $("#profile-avatar").textContent = state.user.name.trim().charAt(0).toUpperCase();
  $("#welcome-heading").textContent = `Welcome, ${state.user.name.split(/\s+/)[0]}`;
  showView("dashboard");
  document.querySelectorAll(".nav-link[data-roles]").forEach((link) => {
    link.classList.toggle("hidden", !link.dataset.roles.split(",").includes(state.user.role));
  });
  $("#new-event-button").classList.toggle("hidden", !isManager());
  $("#update-form").classList.toggle("hidden", !isManager());
  await refreshData();
}

async function refreshData() {
  const [eventData, updateData] = await Promise.all([api("/api/events"), api("/api/updates")]);
  state.events = eventData.events;
  state.updates = updateData.updates;
  renderDashboard();
  renderEvents();
  renderSchedule();
  renderUpdates();
  fillUpdateEventOptions();
  if (isManager()) {
    await renderReports();
  } else {
    state.reports = [];
    $("#report-summary").textContent = "";
    $("#reports-body").innerHTML = "";
  }
}

function renderDashboard() {
  const eventCount = state.events.length;
  const registrationCount = state.events.reduce((sum, event) => sum + event.registration_count, 0);
  const myRegistrations = state.events.reduce((sum, event) => sum + (event.my_status === "registered" ? 1 : 0), 0);
  const stats = state.user.role === "participant"
    ? [["Available events", eventCount], ["Your registrations", myRegistrations], ["Fest updates", state.updates.length]]
    : [["Fest events", eventCount], ["Registrations", registrationCount], ["Fest updates", state.updates.length]];
  $("#dashboard-stats").innerHTML = stats.map(([label, count]) => `<article class="stat-card"><span>${escapeHtml(label)}</span><strong>${count}</strong></article>`).join("");
  const upcoming = [...state.events].sort((a, b) => `${a.date}${a.start_time}`.localeCompare(`${b.date}${b.start_time}`)).slice(0, 3);
  $("#dashboard-events").innerHTML = upcoming.length ? upcoming.map(eventCard).join("") : emptyState("No events have been added yet.");
  $("#dashboard-updates").innerHTML = state.updates.length ? state.updates.slice(0, 3).map(updateCard).join("") : emptyState("There are no updates yet.");
}

function eventCard(event) {
  const controls = [];
  if (state.user.role === "participant") {
    if (event.my_status === "registered") {
      controls.push('<span class="registered-label">Registered</span>');
      controls.push(`<button class="button button-secondary" type="button" data-action="unregister" data-id="${event.id}">Cancel registration</button>`);
    } else {
      controls.push(`<button class="button button-primary" type="button" data-action="register" data-id="${event.id}" ${event.registration_count >= event.capacity ? "disabled" : ""}>${event.registration_count >= event.capacity ? "Full" : "Register"}</button>`);
    }
  }
  if (canManage(event)) {
    controls.push(`<button class="button button-secondary" type="button" data-action="edit-event" data-id="${event.id}">Edit</button>`);
    controls.push(`<button class="button button-danger" type="button" data-action="delete-event" data-id="${event.id}">Delete</button>`);
    controls.push(`<button class="button button-secondary" type="button" data-action="assign-volunteer" data-id="${event.id}">Assign volunteer</button>`);
  }
  if (state.user.role === "volunteer") {
    const assigned = event.volunteer_assigned;
    controls.push(`<span class="registered-label">${assigned ? "Assigned to help" : "Not assigned"}</span>`);
  }
  return `<article class="event-card">
    <div class="event-card-top"><span class="category-tag">${escapeHtml(event.category)}</span><span class="capacity-note">${event.registration_count} / ${event.capacity} spots</span></div>
    <h3>${escapeHtml(event.name)}</h3><p class="event-description">${escapeHtml(event.description)}</p>
    <div class="event-meta"><span>${escapeHtml(formatDate(event.date))} · ${escapeHtml(event.start_time)}–${escapeHtml(event.end_time)}</span><span>${escapeHtml(event.venue)}</span></div>
    <div class="event-actions">${controls.join("") || '<span class="muted">Event details</span>'}</div>
  </article>`;
}

function emptyState(message) {
  return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderEvents() {
  $("#events-list").innerHTML = state.events.length ? state.events.map(eventCard).join("") : emptyState("No events are available yet.");
}

function renderSchedule() {
  const body = $("#schedule-body");
  body.innerHTML = state.events.length ? [...state.events]
    .sort((a, b) => `${a.date}${a.start_time}`.localeCompare(`${b.date}${b.start_time}`))
    .map((event) => `<tr><td>${escapeHtml(event.name)}</td><td>${escapeHtml(formatDate(event.date))}</td><td>${escapeHtml(event.start_time)}–${escapeHtml(event.end_time)}</td><td>${escapeHtml(event.venue)}</td><td>${escapeHtml(event.category)}</td></tr>`).join("")
    : '<tr><td colspan="5">No scheduled events.</td></tr>';
}

function updateCard(update) {
  const kind = update.kind === "result" ? "Competition result" : "Announcement";
  const event = update.event_name ? `<span class="update-event">Related event: ${escapeHtml(update.event_name)}</span>` : "";
  const date = new Date(`${update.created_at}Z`);
  const dateLabel = Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `<article class="update-card"><div class="update-header"><span class="update-kind ${update.kind === "result" ? "result" : ""}">${kind}</span><time>${escapeHtml(dateLabel)}</time></div><h3>${escapeHtml(update.title)}</h3><p>${escapeHtml(update.body)}</p>${event}</article>`;
}

function renderUpdates() {
  $("#updates-list").innerHTML = state.updates.length ? state.updates.map(updateCard).join("") : emptyState("No announcements or results have been published.");
}

function fillUpdateEventOptions() {
  const select = $("#update-event");
  const selected = select.value;
  select.innerHTML = '<option value="">General update</option>' + state.events.map((event) => `<option value="${event.id}">${escapeHtml(event.name)}</option>`).join("");
  if (state.events.some((event) => String(event.id) === selected)) select.value = selected;
}

async function renderReports() {
  const data = await api("/api/reports");
  state.reports = data.reports;
  const total = state.reports.reduce((sum, report) => sum + report.registration_count, 0);
  $("#report-summary").textContent = `${state.reports.length} events · ${total} active registrations`;
  $("#reports-body").innerHTML = state.reports.length ? state.reports.map((report) => {
    const fillRate = report.capacity ? Math.round((report.registration_count / report.capacity) * 100) : 0;
    return `<tr><td>${escapeHtml(report.name)}</td><td>${escapeHtml(formatDate(report.date))}</td><td>${escapeHtml(report.venue)}</td><td>${report.registration_count}</td><td>${report.capacity}</td><td>${fillRate}%</td></tr>`;
  }).join("") : '<tr><td colspan="6">No event registration data yet.</td></tr>';
}

function showView(name) {
  document.querySelectorAll(".view-section").forEach((section) => section.classList.toggle("hidden", section.id !== `view-${name}`));
  document.querySelectorAll(".nav-link").forEach((link) => link.classList.toggle("active", link.dataset.view === name));
  $("#page-title").textContent = viewTitles[name] || viewTitles.dashboard;
}

function resetEventForm() {
  $("#event-form").reset();
  $("#event-id").value = "";
  $("#event-form-title").textContent = "Create an event";
  setFormMessage($("#event-form-message"));
  $("#event-form").classList.add("hidden");
}

async function handleEventAction(button) {
  const id = button.dataset.id;
  const event = state.events.find((item) => String(item.id) === id);
  if (!event) return;
  try {
    if (button.dataset.action === "register") {
      await api(`/api/events/${id}/registrations`, { method: "POST", body: "{}" });
      showToast("You are registered for this event.");
    } else if (button.dataset.action === "unregister") {
      await api(`/api/events/${id}/registrations`, { method: "DELETE" });
      showToast("Your registration has been cancelled.");
    } else if (button.dataset.action === "edit-event") {
      $("#event-id").value = event.id;
      $("#event-name").value = event.name;
      $("#event-category").value = event.category;
      $("#event-date").value = event.date;
      $("#event-venue").value = event.venue;
      $("#event-start").value = event.start_time;
      $("#event-end").value = event.end_time;
      $("#event-capacity").value = event.capacity;
      $("#event-description").value = event.description;
      $("#event-form-title").textContent = "Edit event";
      $("#event-form").classList.remove("hidden");
      $("#event-form").scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (button.dataset.action === "delete-event") {
      if (!window.confirm(`Delete "${event.name}" and its registrations? This cannot be undone.`)) return;
      await api(`/api/events/${id}`, { method: "DELETE" });
      showToast("Event deleted.");
    } else if (button.dataset.action === "assign-volunteer") {
      const username = window.prompt("Enter the volunteer's username:");
      if (username === null) return;
      if (!username.trim()) throw new Error("Enter a volunteer username.");
      await api(`/api/events/${id}/volunteers`, { method: "POST", body: JSON.stringify({ username: username.trim() }) });
      showToast("Volunteer assigned.");
    }
    await refreshData();
  } catch (error) {
    showToast(error.message, true);
  }
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  setFormMessage($("#login-message"));
  try {
    const form = new FormData(event.currentTarget);
    await api("/api/login", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) });
    await loadApp();
  } catch (error) { setFormMessage($("#login-message"), error.message); }
});

$("#signup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  setFormMessage($("#signup-message"));
  try {
    const form = new FormData(event.currentTarget);
    await api("/api/signup", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) });
    await loadApp();
  } catch (error) { setFormMessage($("#signup-message"), error.message); }
});

$("#show-signup").addEventListener("click", () => {
  $("#login-form").classList.add("hidden");
  $("#signup-form").classList.remove("hidden");
});
$("#show-login").addEventListener("click", () => {
  $("#signup-form").classList.add("hidden");
  $("#login-form").classList.remove("hidden");
});

$("#logout-button").addEventListener("click", async () => {
  try {
    await api("/api/logout", { method: "POST", body: "{}" });
    state.user = null;
    $("#app-shell").classList.add("hidden");
    $("#login-screen").classList.remove("hidden");
    $("#login-form").reset();
  } catch (error) { showToast(error.message, true); }
});

document.querySelectorAll(".nav-link").forEach((link) => link.addEventListener("click", () => showView(link.dataset.view)));
document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.go)));

$("#new-event-button").addEventListener("click", () => {
  resetEventForm();
  $("#event-form").classList.remove("hidden");
  $("#event-form").scrollIntoView({ behavior: "smooth", block: "start" });
});
$("#cancel-event-edit").addEventListener("click", resetEventForm);

$("#event-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  setFormMessage($("#event-form-message"));
  const eventId = $("#event-id").value;
  const payload = {
    name: $("#event-name").value.trim(), category: $("#event-category").value.trim(),
    date: $("#event-date").value, venue: $("#event-venue").value.trim(),
    start_time: $("#event-start").value, end_time: $("#event-end").value,
    capacity: Number($("#event-capacity").value), description: $("#event-description").value.trim(),
  };
  try {
    await api(eventId ? `/api/events/${eventId}` : "/api/events", { method: eventId ? "PUT" : "POST", body: JSON.stringify(payload) });
    resetEventForm();
    showToast(eventId ? "Event updated." : "Event created.");
    await refreshData();
  } catch (error) { setFormMessage($("#event-form-message"), error.message); }
});

$("#events-list").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (button) handleEventAction(button);
});
$("#dashboard-events").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (button) handleEventAction(button);
});

$("#update-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  setFormMessage($("#update-message"));
  const payload = {
    kind: $("#update-kind").value, event_id: $("#update-event").value || null,
    title: $("#update-title").value.trim(), body: $("#update-body").value.trim(),
  };
  try {
    await api("/api/updates", { method: "POST", body: JSON.stringify(payload) });
    event.currentTarget.reset();
    setFormMessage($("#update-message"));
    showToast("Update published.");
    await refreshData();
  } catch (error) { setFormMessage($("#update-message"), error.message); }
});

async function start() {
  try {
    await loadApp();
  } catch (error) {
    if (error.message !== "Sign in is required.") showToast(error.message, true);
  }
}
start();
