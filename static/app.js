const form = document.querySelector("#query");
const latitudeInput = document.querySelector("#latitude");
const longitudeInput = document.querySelector("#longitude");
const statusNode = document.querySelector("#status");
const banner = document.querySelector("#banner");
const empty = document.querySelector("#empty");
const board = document.querySelector("#board");
const provenance = document.querySelector("#provenance");
const buttons = form.querySelectorAll("button");
const STORAGE_KEY = "heather.coordinates";

const DIRECTIONS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

function format(value, digits) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function duration(seconds) {
  if (seconds === null || seconds === undefined) {
    return "—";
  }
  const total = Math.round(Number(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return `${hours} h ${minutes} min`;
}

function cardinal(degrees) {
  if (degrees === null || degrees === undefined) {
    return "—";
  }
  const index = Math.round(Number(degrees) / 22.5) % 16;
  return DIRECTIONS[(index + 16) % 16];
}

function clock(iso, timeZone) {
  if (!iso) {
    return "—";
  }
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  const options = {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric",
    timeZoneName: "short",
  };
  if (timeZone) {
    options.timeZone = timeZone;
  }
  try {
    return new Intl.DateTimeFormat(undefined, options).format(parsed);
  } catch (_error) {
    delete options.timeZone;
    return new Intl.DateTimeFormat(undefined, options).format(parsed);
  }
}

function setBusy(busy) {
  buttons.forEach((button) => {
    button.disabled = busy;
  });
  form.setAttribute("aria-busy", busy ? "true" : "false");
  statusNode.textContent = busy ? "Reading the station…" : statusNode.textContent;
}

function showError(message) {
  banner.hidden = false;
  banner.textContent = message;
  statusNode.textContent = "Reading failed.";
  if (board.hidden) {
    empty.hidden = false;
    provenance.textContent = "";
  }
}

function render(conditions) {
  const humidity = conditions.humidity.relative_percent;
  document.querySelector("#humidity-value").textContent = format(humidity, 0);
  document.querySelector("#humidity-meter").style.width = `${Math.max(0, Math.min(100, humidity || 0))}%`;
  document.querySelector("#humidity-detail").textContent =
    `Dew point ${format(conditions.humidity.dew_point_c, 1)} °C`;

  document.querySelector("#weather-value").textContent = format(conditions.weather.temperature_c, 1);
  document.querySelector("#weather-summary").textContent = conditions.weather.summary;
  const wind = `${format(conditions.weather.wind_speed_kmh, 0)} km/h ${cardinal(conditions.weather.wind_direction_deg)}`;
  document.querySelector("#weather-detail").textContent =
    `Feels ${format(conditions.weather.apparent_temperature_c, 1)} °C · ${wind} · ` +
    `cloud ${format(conditions.weather.cloud_cover_percent, 0)}% · ` +
    `rain ${format(conditions.weather.precipitation_mm, 1)} mm · ` +
    `${format(conditions.weather.pressure_hpa, 0)} hPa`;

  const radiation = conditions.sunlight.shortwave_radiation_wm2;
  document.querySelector("#sun-value").textContent = format(radiation, 0);
  document.querySelector("#sun-meter").style.width = `${Math.max(0, Math.min(100, ((radiation || 0) / 1000) * 100))}%`;
  document.querySelector("#sun-summary").textContent = conditions.sunlight.description;
  const zone = conditions.location.timezone;
  document.querySelector("#sun-detail").textContent =
    `UV ${format(conditions.sunlight.uv_index, 1)} · max today ${format(conditions.sunlight.uv_index_max_today, 1)}\n` +
    `Sunshine ${duration(conditions.sunlight.sunshine_duration_today_s)} · daylight ${duration(conditions.sunlight.daylight_duration_s)}\n` +
    `Sunrise ${clock(conditions.sunlight.sunrise, zone)} · sunset ${clock(conditions.sunlight.sunset, zone)}`;

  document.querySelector("#height-value").textContent = format(conditions.height.elevation_m, 0);
  document.querySelector("#height-summary").textContent = "Terrain elevation above sea level";
  document.querySelector("#height-detail").textContent =
    `${format(conditions.height.elevation_ft, 0)} ft at the model grid point`;

  const cacheLabel = {
    hit: "Served from the station cache",
    miss: "Fresh from the weather service",
    stale: "Cached after the weather service failed",
  }[conditions.cache.status];
  provenance.textContent =
    `${cacheLabel}. Observed ${clock(conditions.observed_at, conditions.location.timezone)}. ` +
    `Requested ${conditions.location.latitude.toFixed(4)}, ${conditions.location.longitude.toFixed(4)}. ` +
    `Grid point ${conditions.location.resolved_latitude.toFixed(4)}, ${conditions.location.resolved_longitude.toFixed(4)} ` +
    `(${conditions.location.timezone || "local time"}).`;

  banner.hidden = conditions.cache.status !== "stale";
  if (conditions.cache.status === "stale") {
    banner.textContent = "The weather service did not answer. This reading is saved from an earlier request and may be out of date.";
  }
  empty.hidden = true;
  board.hidden = false;
  statusNode.textContent = "Conditions updated.";
}

async function readConditions(latitude, longitude) {
  setBusy(true);
  try {
    const params = new URLSearchParams({
      latitude: String(latitude),
      longitude: String(longitude),
    });
    const response = await fetch(`/api/v1/conditions?${params}`);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = body.error && body.error.message
        ? body.error.message
        : `The station could not read that point (${response.status}).`;
      showError(message);
      statusNode.textContent = "Reading failed.";
      return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ latitude, longitude }));
    render(body);
  } catch (_error) {
    showError("The station could not be reached.");
    statusNode.textContent = "Reading failed.";
  } finally {
    setBusy(false);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  readConditions(latitudeInput.value, longitudeInput.value);
});

document.querySelector("#locate").addEventListener("click", () => {
  if (!navigator.geolocation) {
    statusNode.textContent = "This browser has no location service. Enter coordinates instead.";
    return;
  }
  statusNode.textContent = "Asking for this device’s location…";
  navigator.geolocation.getCurrentPosition(
    (position) => {
      latitudeInput.value = position.coords.latitude.toFixed(5);
      longitudeInput.value = position.coords.longitude.toFixed(5);
      readConditions(latitudeInput.value, longitudeInput.value);
    },
    () => {
      statusNode.textContent = "Location was not shared. Enter coordinates instead.";
    },
    { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
  );
});

form.querySelectorAll(".presets button").forEach((button) => {
  button.addEventListener("click", () => {
    latitudeInput.value = button.dataset.lat;
    longitudeInput.value = button.dataset.lon;
    readConditions(button.dataset.lat, button.dataset.lon);
  });
});

try {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  if (saved && Number.isFinite(Number(saved.latitude)) && Number.isFinite(Number(saved.longitude))) {
    latitudeInput.value = saved.latitude;
    longitudeInput.value = saved.longitude;
    readConditions(saved.latitude, saved.longitude);
  }
} catch (_error) {
  localStorage.removeItem(STORAGE_KEY);
}
