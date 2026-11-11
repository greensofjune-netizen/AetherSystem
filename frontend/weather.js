"use strict";

const WEATHER_CONFIG = Object.freeze({
  geocodingUrl: "https://geocoding-api.open-meteo.com/v1/search",
  forecastUrl: "https://api.open-meteo.com/v1/forecast",
  refreshMs: 300000,
  timeoutMs: 12000,
});
let activeCoords = { name: "Upland, CA", lat: 34.0975, lon: -117.6484 };
let busy = false;
let lastSync = null;
let latestWeatherContext = null;

const WMO_CODES = {
  0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
  45: "Fog", 48: "Rime Fog", 51: "Light Drizzle", 53: "Moderate Drizzle",
  55: "Dense Drizzle", 56: "Light Freezing Drizzle", 57: "Dense Freezing Drizzle",
  61: "Light Rain", 63: "Moderate Rain", 65: "Heavy Rain",
  66: "Light Freezing Rain", 67: "Heavy Freezing Rain",
  71: "Light Snow", 73: "Moderate Snow", 75: "Heavy Snow", 77: "Snow Grains",
  80: "Light Rain Showers", 81: "Moderate Rain Showers", 82: "Violent Rain Showers",
  85: "Light Snow Showers", 86: "Heavy Snow Showers",
  95: "Thunderstorm", 96: "Thunderstorm with Light Hail", 99: "Thunderstorm with Heavy Hail",
};
const element = (id) => document.getElementById(id);
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const decodeWeather = (code) => WMO_CODES[code] ?? "Unknown condition";

const copernicusEnabled = document.body.dataset.copernicus === "true";
element("copernicus-tab").hidden = !copernicusEnabled;
const shellTabs = [...document.querySelectorAll('[role="tab"]')].filter((tab) => !tab.hidden);
const stargazerFrame = element("stargazer-frame");

function notifyStargazerVisibility() {
  stargazerFrame.contentWindow?.postMessage({
    type: "cosmic-shell-visibility",
    visible: !element("stargazer-panel").hidden,
  }, window.location.origin);
}

function selectShellTab(index) {
  shellTabs.forEach((tab, i) => {
    tab.setAttribute("aria-selected", String(i === index));
    tab.tabIndex = i === index ? 0 : -1;
    element(tab.getAttribute("aria-controls")).hidden = i !== index;
  });
  if (shellTabs[index].id === "stargazer-tab" && !stargazerFrame.hasAttribute("src")) {
    stargazerFrame.src = stargazerFrame.dataset.src;
  }
  notifyStargazerVisibility();
}

shellTabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectShellTab(index));
  tab.addEventListener("keydown", (event) => {
    const destinations = {
      ArrowRight: (index + 1) % shellTabs.length,
      ArrowLeft: (index + shellTabs.length - 1) % shellTabs.length,
      Home: 0, End: shellTabs.length - 1,
    };
    if (!(event.key in destinations)) return;
    event.preventDefault();
    const next = destinations[event.key];
    selectShellTab(next);
    shellTabs[next].focus();
  });
});
stargazerFrame.addEventListener("load", notifyStargazerVisibility);
selectShellTab(0);

async function fetchJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), WEATHER_CONFIG.timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`Weather service returned HTTP ${response.status}.`);
    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Weather request timed out.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function validateForecast(data) {
  const current = data?.current;
  const daily = data?.daily;
  if (!current || !daily ||
      !["temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m", "cloud_cover"]
        .every((key) => finite(current[key])) ||
      current.relative_humidity_2m < 0 || current.relative_humidity_2m > 100 ||
      current.wind_speed_10m < 0 ||
      current.cloud_cover < 0 || current.cloud_cover > 100 ||
      !Number.isInteger(current.weather_code) ||
      typeof current.time !== "string" || !Number.isFinite(Date.parse(current.time)) ||
      typeof data.timezone !== "string" ||
      !["time", "weather_code", "temperature_2m_max", "temperature_2m_min"]
        .every((key) => Array.isArray(daily[key]) && daily[key].length === 5)) {
    throw new Error("Weather service returned incomplete readings.");
  }
  daily.time.forEach((date, i) => {
    if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
        !Number.isFinite(Date.parse(`${date}T12:00:00`)) ||
        !Number.isInteger(daily.weather_code[i]) ||
        !finite(daily.temperature_2m_max[i]) || !finite(daily.temperature_2m_min[i]) ||
        daily.temperature_2m_max[i] < daily.temperature_2m_min[i]) {
      throw new Error("Weather service returned an invalid forecast.");
    }
  });
}

function renderForecast(place, data) {
  element("city-title").textContent = place.name;
  element("current-temp").textContent = `${Math.round(data.current.temperature_2m)}\u00b0F`;
  element("current-cond").textContent = decodeWeather(data.current.weather_code);
  element("wind-speed").textContent = `Wind: ${Math.round(data.current.wind_speed_10m)} mph`;
  element("humidity").textContent = `Humidity: ${data.current.relative_humidity_2m}%`;
  element("cloud-cover").textContent = `Cloud cover: ${Math.round(data.current.cloud_cover)}%`;
  element("forecast-grid").replaceChildren();
  data.daily.time.forEach((date, i) => {
    const card = document.createElement("div");
    card.className = "day-card";
    const fields = [
      ["day-name", new Date(`${date}T12:00:00`).toLocaleDateString("en-US", {
        weekday: "short", month: "short", day: "numeric",
      })],
      ["day-temps", `${Math.round(data.daily.temperature_2m_max[i])}\u00b0 / ${Math.round(data.daily.temperature_2m_min[i])}\u00b0`],
      ["day-desc", decodeWeather(data.daily.weather_code[i])],
    ];
    fields.forEach(([className, text]) => {
      const field = document.createElement("div");
      field.className = className;
      field.textContent = text;
      card.append(field);
    });
    element("forecast-grid").append(card);
  });
}

async function syncTelemetry(query = "") {
  if (busy) return;
  busy = true;
  element("sync-button").disabled = true;
  element("city-input").disabled = true;
  element("weather-error").hidden = true;
  element("status-text").textContent = "CONNECTING";
  element("status-dot").classList.add("offline");
  try {
    let place = activeCoords;
    if (query) {
      const geoUrl = new URL(WEATHER_CONFIG.geocodingUrl);
      geoUrl.search = new URLSearchParams({ name: query, count: "1", language: "en", format: "json" });
      const geo = await fetchJson(geoUrl);
      if (!Array.isArray(geo?.results) || geo.results.length === 0) {
        throw new Error("City not found. Try a nearby city or a different spelling.");
      }
      const found = geo.results[0];
      if (!found || typeof found.name !== "string" ||
          !finite(found.latitude) || Math.abs(found.latitude) > 90 ||
          !finite(found.longitude) || Math.abs(found.longitude) > 180) {
        throw new Error("Weather service returned an invalid city.");
      }
      place = {
        name: [found.name, found.admin1, found.country_code].filter((part) => typeof part === "string" && part).join(", "),
        lat: found.latitude, lon: found.longitude,
      };
    }
    const url = new URL(WEATHER_CONFIG.forecastUrl);
    url.search = new URLSearchParams({
      latitude: String(place.lat), longitude: String(place.lon),
      current: "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,cloud_cover",
      daily: "weather_code,temperature_2m_max,temperature_2m_min",
      temperature_unit: "fahrenheit", wind_speed_unit: "mph",
      timezone: "auto", forecast_days: "5",
    });
    const data = await fetchJson(url);
    validateForecast(data);
    renderForecast(place, data);
    activeCoords = place;
    lastSync = new Date().toLocaleTimeString();
    element("sync-time").textContent = `Last sync: ${lastSync}. Observation: ${data.current.time.replace("T", " ")} (${data.timezone}).`;
    element("status-dot").classList.remove("offline");
    element("status-text").textContent = "LIVE TELEMETRY";
    latestWeatherContext = {
      city: place.name,
      cloud_cover_percent: data.current.cloud_cover,
      observed_at: data.current.time,
      timezone: data.timezone,
      freshness: "live",
    };
    window.dispatchEvent(new CustomEvent("weather-telemetry", {
      detail: latestWeatherContext,
    }));
  } catch (error) {
    element("status-text").textContent = lastSync ? "OFFLINE / STALE" : "OFFLINE / UNAVAILABLE";
    element("sync-time").textContent = lastSync
      ? `Showing stale readings for ${activeCoords.name} from ${lastSync}.`
      : "No weather readings available. Retry with Sync.";
    if (!lastSync) element("current-cond").textContent = "Weather unavailable";
    if (latestWeatherContext) {
      latestWeatherContext = { ...latestWeatherContext, freshness: "stale" };
      window.dispatchEvent(new CustomEvent("weather-telemetry", {
        detail: latestWeatherContext,
      }));
    }
    element("weather-error").textContent = error.message;
    element("weather-error").hidden = false;
    console.error("Weather sync failed:", error);
  } finally {
    element("sync-button").disabled = false;
    element("city-input").disabled = false;
    busy = false;
  }
}

element("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const query = element("city-input").value.trim();
  if (!query) {
    element("weather-error").textContent = "Enter a city name.";
    element("weather-error").hidden = false;
    return;
  }
  syncTelemetry(query);
});
syncTelemetry();
setInterval(() => syncTelemetry(), WEATHER_CONFIG.refreshMs);
