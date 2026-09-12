// Helper yang dipakai bersama halaman dashboard dan halaman detail.

export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Terjadi kesalahan.");
  }
  return payload;
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/** URL file output, dengan cache-buster dari mtime supaya render ulang langsung terlihat. */
export function outputUrl(item, file) {
  if (!item || !file) return "";
  const baseUrl = `/api/outputs/${encodeURIComponent(item.date)}/${encodeURIComponent(file.name)}`;
  const version = file.version ?? file.mtime;
  return version ? `${baseUrl}?v=${encodeURIComponent(version)}` : baseUrl;
}

export function detailUrl(date) {
  return `/detail.html?date=${encodeURIComponent(date)}`;
}

export function formatDateLabel(date) {
  try {
    return new Date(`${date}T00:00:00.000Z`).toLocaleDateString("id-ID", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return date;
  }
}

/** Jam render diambil dari mtime video; kembalikan null kalau tidak tersedia. */
export function formatTimeLabel(file) {
  const raw = file?.mtime;
  if (!raw) return null;
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleTimeString("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatBytes(size) {
  if (typeof size !== "number" || !Number.isFinite(size) || size < 0) return "-";
  if (size === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(units.length - 1, Math.floor(Math.log10(size) / 3));
  const value = size / 1000 ** exponent;
  const digits = exponent === 0 || value >= 100 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[exponent]}`;
}

export function buildHashtags(tags, limit = 6) {
  if (!Array.isArray(tags)) return [];
  return tags
    .slice(0, limit)
    .map((tag) => `#${String(tag).replace(/\s+/g, "")}`)
    .filter((tag) => tag.length > 1);
}

/** Baca script.json sebuah output. Mengembalikan null bila belum ada / gagal. */
export async function loadScriptMeta(item) {
  if (!item?.script_file) return null;
  try {
    const response = await fetch(outputUrl(item, item.script_file));
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function loadTextFile(item, file) {
  if (!file) return null;
  try {
    const response = await fetch(outputUrl(item, file));
    if (!response.ok) return null;
    return await response.text();
  } catch {
    return null;
  }
}

/**
 * Video hasil pipeline bisa portrait (1080x1920) atau landscape. Set flag
 * orientasi setelah metadata termuat supaya CSS bisa membatasi tingginya.
 */
export function tagVideoOrientation(videoElement) {
  if (!(videoElement instanceof HTMLVideoElement)) return;
  const apply = () => {
    const { videoWidth: width, videoHeight: height } = videoElement;
    if (!width || !height) return;
    videoElement.dataset.orientation = height > width ? "portrait" : "landscape";
    videoElement.style.aspectRatio = `${width} / ${height}`;
  };
  if (videoElement.readyState >= 1) {
    apply();
    return;
  }
  videoElement.addEventListener("loadedmetadata", apply, { once: true });
}
