import "./style.css";
import {
  buildHashtags,
  detailUrl,
  escapeHtml,
  fetchJson,
  formatDateLabel,
  formatTimeLabel,
  loadScriptMeta,
  outputUrl,
} from "./api.js";

const DASHBOARD_LIMIT = 3;

const taskResult = document.getElementById("taskResult");
const outputList = document.getElementById("outputList");
const outputCount = document.getElementById("outputCount");
const runForm = document.getElementById("run-form");
const skipYoutubeInput = document.getElementById("skipYoutube");
const skipInstagramInput = document.getElementById("skipInstagram");
const runDateInput = document.getElementById("runDate");

let pollTimer = null;

function parseIsoDate(value) {
  if (!value || typeof value !== "string") return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatElapsedValue(seconds) {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) return "-";
  const rounded = Math.max(0, Math.floor(seconds));
  const mins = String(Math.floor(rounded / 60)).padStart(2, "0");
  const secs = String(rounded % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}

function buildCard(item, meta, isLatest) {
  const title = meta?.title || "Daily News Clip";
  const summary = meta?.description_text || meta?.description || "";
  const hashtags = buildHashtags(meta?.tags, 3);
  const timeLabel = formatTimeLabel(item.final_video);
  const dateLabel = formatDateLabel(item.date);
  const stamp = timeLabel ? `${dateLabel} · ${timeLabel} WIB` : dateLabel;

  const card = document.createElement("a");
  card.className = "output-card";
  card.href = detailUrl(item.date);
  card.setAttribute("aria-label", `Lihat detail output ${dateLabel}: ${title}`);

  const thumbSrc = item.thumbnail ? outputUrl(item, item.thumbnail) : "";
  card.innerHTML = `
    <div class="output-thumb">
      ${
        thumbSrc
          ? `<img src="${escapeHtml(thumbSrc)}" alt="Thumbnail ${escapeHtml(title)}" loading="lazy" />`
          : `<div class="output-thumb-fallback">Tanpa thumbnail</div>`
      }
      ${isLatest ? `<span class="badge badge-live">Terbaru</span>` : ""}
      ${item.final_video ? `<span class="output-play" aria-hidden="true">▶</span>` : ""}
    </div>
    <div class="output-body">
      <span class="output-stamp">${escapeHtml(stamp)}</span>
      <h3 class="output-title">${escapeHtml(title)}</h3>
      ${summary ? `<p class="output-summary">${escapeHtml(summary)}</p>` : ""}
      <div class="output-tags">
        ${hashtags.map((tag) => `<span class="chip">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <span class="output-cta">Lihat detail →</span>
    </div>
  `;
  return card;
}

async function renderOutputs(outputs) {
  outputList.innerHTML = "";
  if (!outputs.length) {
    outputList.innerHTML = `<p class="empty-state">Belum ada output. Jalankan pipeline untuk membuat video pertama.</p>`;
    if (outputCount) outputCount.textContent = "0 output";
    return;
  }

  const visible = outputs.slice(0, DASHBOARD_LIMIT);
  if (outputCount) {
    outputCount.textContent =
      outputs.length > visible.length
        ? `${visible.length} dari ${outputs.length} output`
        : `${outputs.length} output`;
  }

  const metas = await Promise.all(visible.map((item) => loadScriptMeta(item)));
  const fragment = document.createDocumentFragment();
  visible.forEach((item, index) => {
    fragment.appendChild(buildCard(item, metas[index], index === 0));
  });
  outputList.appendChild(fragment);
}

async function loadOutputs() {
  const data = await fetchJson("/api/outputs/");
  await renderOutputs(data.outputs || []);
}

function formatTask(task) {
  if (!task || typeof task !== "object") return String(task || "");
  const lines = [];
  const progress = task.progress != null ? ` (${task.progress}%)` : "";
  if (task.status) lines.push(`Status: ${task.status}${progress}`);
  if (task.phase) lines.push(`Fase: ${task.phase}`);
  if (task.message) lines.push(`Proses: ${task.message}`);
  if (task.task_id) lines.push(`Task ID: ${task.task_id}`);
  if (task.run_date) lines.push(`Run date: ${task.run_date}`);
  if (task.elapsed || task.elapsed_seconds !== undefined) {
    lines.push(`Durasi sesi: ${task.elapsed || formatElapsedValue(task.elapsed_seconds)}`);
  }
  const started = parseIsoDate(task.started_at);
  if (started) lines.push(`Dimulai: ${started.toLocaleString("id-ID")}`);
  if (task.status === "finished" || task.status === "failed") {
    const finished = parseIsoDate(task.finished_at);
    if (finished) lines.push(`Selesai: ${finished.toLocaleString("id-ID")}`);
  }
  if (task.result?.output_dir) lines.push(`Output: ${task.result.output_dir}`);
  if (task.error) lines.push(`Error: ${task.error}`);
  return lines.join("\n") || "Menerima update status…";
}

function setTaskText(value) {
  taskResult.textContent = typeof value === "string" ? value : formatTask(value);
}

function startPolling(taskId) {
  if (pollTimer) clearInterval(pollTimer);
  const poll = async () => {
    try {
      const task = await fetchJson(`/api/task/${taskId}/`);
      setTaskText(task);
      if (task.status === "finished" || task.status === "failed") {
        clearInterval(pollTimer);
        pollTimer = null;
        await loadOutputs();
      }
    } catch (error) {
      setTaskText({ error: error.message });
      clearInterval(pollTimer);
      pollTimer = null;
    }
  };
  poll();
  pollTimer = setInterval(poll, 1000);
}

runForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = runForm.querySelector("button[type=submit]");
  if (submitButton) submitButton.disabled = true;
  try {
    const response = await fetchJson("/api/run/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        skip_youtube: skipYoutubeInput.checked,
        skip_instagram: skipInstagramInput.checked,
        run_date: runDateInput.value.trim() || undefined,
      }),
    });
    setTaskText(response);
    startPolling(response.task_id);
  } catch (error) {
    setTaskText({ error: error.message });
  } finally {
    if (submitButton) submitButton.disabled = false;
  }
});

loadOutputs().catch((error) => setTaskText({ error: error.message }));
