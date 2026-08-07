import "./style.css";

const taskResult = document.getElementById("taskResult");
const outputList = document.getElementById("outputList");
const runForm = document.getElementById("run-form");
const skipUploadInput = document.getElementById("skipUpload");
const runDateInput = document.getElementById("runDate");
const appTitle = document.getElementById("app-title");
const latestPreview = document.getElementById("latestPreview");

let pollTimer = null;
let currentProfile = {
  name: "AIpreneur News",
  tag: "@aipreneur.news_",
  bio: "Daily news summary in Bahasa Indonesia · 30–60 detik",
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Terjadi kesalahan.");
  }
  return payload;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function parseDateLabel(date) {
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

function fitVideoFormat(videoElement) {
  if (!(videoElement instanceof HTMLVideoElement)) return;
  const apply = () => {
    const width = videoElement.videoWidth;
    const height = videoElement.videoHeight;
    if (!width || !height) return;
    videoElement.setAttribute("width", String(width));
    videoElement.setAttribute("height", String(height));
    videoElement.style.aspectRatio = "auto";
    if (videoElement.parentElement) {
      videoElement.parentElement.style.aspectRatio = "auto";
      videoElement.parentElement.style.height = "auto";
    }
  };

  if (videoElement.readyState >= 1) {
    apply();
    return;
  }
  videoElement.addEventListener("loadedmetadata", apply, { once: true });
}

function setLatestPreview(item) {
  if (!latestPreview) return;
  if (!item || !item.final_video) {
    latestPreview.style.display = "none";
    latestPreview.innerHTML = "";
    return;
  }
  const videoSrc = `/output/${item.date}/${item.final_video.name}`;
  const title = item.title || "Daily News Clip";
  latestPreview.style.display = "block";
  latestPreview.innerHTML = `
    <div class="caption">
      <h3>Preview: ${escapeHtml(title)}</h3>
    </div>
    <div class="preview-player">
      <video controls preload="metadata" src="${videoSrc}" playsinline></video>
    </div>
  `;
  const previewVideo = latestPreview.querySelector("video");
  fitVideoFormat(previewVideo);
}

function parseIsoDate(dateValue) {
  if (!dateValue || typeof dateValue !== "string") return null;
  const parsed = new Date(dateValue);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}

function formatElapsedValue(seconds) {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) {
    return "-";
  }
  const rounded = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(rounded / 60);
  const secs = rounded % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

async function loadScriptMeta(item) {
  if (!item.script_file) return null;
  try {
    const scriptUrl = `/api/outputs/${item.date}/${item.script_file.name}`;
    const resp = await fetch(scriptUrl);
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

function buildHashtags(tags) {
  if (!Array.isArray(tags) || !tags.length) return [];
  return tags.slice(0, 5).map((tag) => `#${String(tag).replace(/\s+/g, "")}`);
}

async function renderOutput(outputs) {
  outputList.innerHTML = "";
  if (!outputs.length) {
    outputList.innerHTML = "<p>Belum ada output.</p>";
    return;
  }

  for (const item of outputs) {
    const meta = await loadScriptMeta(item);
    const title = meta?.title || "Daily News Clip";
    const caption = meta?.description || "Ringkasan berita harian terbaru.";
    const hashtags = buildHashtags(meta?.tags || []);
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <div class="meta-strip">
        <div class="meta-line">${escapeHtml(currentProfile.name)} · ${parseDateLabel(item.date)}</div>
      </div>
      <div class="caption">
        <h3 class="video-title">📌 ${escapeHtml(title)}</h3>
        <p>${escapeHtml(caption)}</p>
        <div class="hashtags">${hashtags.map((tag) => `<span>${tag}</span>`).join(" ")}</div>
      </div>
      ${item.final_video ? `<div class="video-preview"><div class="video-filename-tag">📹 File: ${escapeHtml(item.final_video.name)}</div><video controls preload="metadata" src="/output/${item.date}/${item.final_video.name}" playsinline></video></div>` : ""}
      <div class="thumb-wrap">
        ${item.thumbnail ? `<img src="/output/${item.date}/${item.thumbnail.name}" alt="${escapeHtml(title)}" />` : ""}
      </div>
      <div class="links"></div>
    `;
    const links = card.querySelector(".links");
    ["script_file", "final_video", "thumbnail", "voiceover", "ig_caption_file"].forEach((key) => {
      const file = item[key];
      if (key === "ig_caption_file" && file) {
        const cLink = document.createElement("a");
        cLink.href = `/api/outputs/${item.date}/${file.name}`;
        cLink.target = "_blank";
        cLink.rel = "noopener";
        cLink.textContent = "Unduh caption IG";
        cLink.style.display = "block";
        links.appendChild(cLink);
        return;
      }
      if (!file) return;
      const link = document.createElement("a");
      const filename = file.name;
      link.href = `/api/outputs/${item.date}/${filename}`;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = `Unduh ${filename}`;
      link.style.display = "block";
      links.appendChild(link);
    });
    outputList.appendChild(card);
    const previewVideo = card.querySelector(".video-preview video");
    if (previewVideo) {
      fitVideoFormat(previewVideo);
    }
  }

  if (outputs[0]) {
    const first = outputs[0];
    const firstMeta = await loadScriptMeta(first);
    first.title = firstMeta?.title || "Daily News Clip";
    setLatestPreview(first);
  } else {
    setLatestPreview(null);
  }
}

async function loadOutputs() {
  const data = await fetchJson("/api/outputs/");
  renderOutput(data.outputs || []);
}

function setTaskText(text) {
  if (typeof text === "string") {
    taskResult.textContent = text;
    return;
  }
  taskResult.textContent = formatTask(text);
}

function formatTask(task) {
  if (!task || typeof task !== "object") return String(task || "");
  const lines = [];
  const phase = task.phase || "unknown";
  const progress = task.progress != null ? `${task.progress}%` : null;
  if (task.status) lines.push(`Status: ${task.status}${progress ? ` (${progress})` : ""}`);
  if (task.phase) lines.push(`Fase: ${phase}`);
  if (task.message) lines.push(`Proses: ${task.message}`);
  if (task.task_id) lines.push(`Task ID: ${task.task_id}`);
  if (task.run_date) lines.push(`Run date: ${task.run_date}`);
  if (task.elapsed || task.elapsed_seconds !== undefined) {
    const elapsedValue = task.elapsed || formatElapsedValue(task.elapsed_seconds);
    lines.push(`Durasi sesi: ${elapsedValue}`);
  }
  if (task.started_at && task.created_at) {
    const started = parseIsoDate(task.started_at);
    if (started) {
      lines.push(`Dimulai: ${started.toLocaleString("id-ID")}`);
    }
  }
  if (task.finished_at && (task.status === "finished" || task.status === "failed")) {
    const finished = parseIsoDate(task.finished_at);
    if (finished) {
      lines.push(`Selesai: ${finished.toLocaleString("id-ID")}`);
    }
  }
  if (task.result?.output_dir) lines.push(`Output: ${task.result.output_dir}`);
  if (task.error) lines.push(`Error: ${task.error}`);
  if (task.created_at) lines.push(`Dibuat: ${task.created_at}`);
  return lines.join("\n") || "Menerima update status...";
}

function startPolling(taskId) {
  if (pollTimer) clearInterval(pollTimer);
  let attempts = 0;
  const poll = async () => {
    try {
      const task = await fetchJson(`/api/task/${taskId}/`);
      setTaskText(formatTask(task));
      attempts += 1;
      if (task.status === "finished" || task.status === "failed") {
        clearInterval(pollTimer);
        pollTimer = null;
        await loadOutputs();
      }
    } catch (err) {
      setTaskText({ error: err.message });
      clearInterval(pollTimer);
      pollTimer = null;
    }
  };
  poll();
  pollTimer = setInterval(poll, 1000);
}

runForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = {
      skip_upload: skipUploadInput.checked,
      run_date: runDateInput.value.trim() || undefined,
    };
    const response = await fetchJson("/api/run/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setTaskText(response);
    startPolling(response.task_id);
  } catch (err) {
    setTaskText({ error: err.message });
  }
});

loadOutputs().catch((error) => setTaskText({ error: error.message }));
