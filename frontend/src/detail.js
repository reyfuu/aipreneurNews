import "./style.css";
import {
  buildHashtags,
  detailUrl,
  escapeHtml,
  fetchJson,
  formatBytes,
  formatDateLabel,
  formatTimeLabel,
  loadScriptMeta,
  loadTextFile,
  outputUrl,
  tagVideoOrientation,
} from "./api.js";

const detailRoot = document.getElementById("detailRoot");
const detailBadge = document.getElementById("detailBadge");

const FILE_LABELS = [
  ["final_video", "Video final"],
  ["thumbnail", "Thumbnail"],
  ["script_file", "Script JSON"],
  ["ig_caption_file", "Caption Instagram"],
  ["voiceover", "Voiceover"],
];

function showMessage(html) {
  detailRoot.innerHTML = `<section class="panel"><p class="empty-state">${html}</p></section>`;
}

function requestedDate() {
  return new URLSearchParams(window.location.search).get("date");
}

function renderTextBlock(title, body) {
  if (!body || !String(body).trim()) return "";
  return `
    <div class="detail-block">
      <h3>${escapeHtml(title)}</h3>
      <p class="detail-text">${escapeHtml(body)}</p>
    </div>
  `;
}

function renderFileRows(item) {
  const rows = FILE_LABELS.filter(([key]) => item[key]).map(([key, label]) => {
    const file = item[key];
    const empty = file.size === 0;
    return `
      <li class="file-row">
        <div class="file-meta">
          <span class="file-label">${escapeHtml(label)}</span>
          <span class="file-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
        </div>
        <span class="file-size">${escapeHtml(formatBytes(file.size))}</span>
        ${
          empty
            ? `<span class="chip chip-warn">kosong</span>`
            : `<a class="btn-ghost" href="${escapeHtml(outputUrl(item, file))}" target="_blank" rel="noopener">Buka</a>`
        }
      </li>
    `;
  });
  if (!rows.length) return `<p class="empty-state">Tidak ada file.</p>`;
  return `<ul class="file-list">${rows.join("")}</ul>`;
}

function renderNav(outputs, index) {
  const newer = outputs[index - 1];
  const older = outputs[index + 1];
  if (!newer && !older) return "";
  return `
    <nav class="detail-nav">
      ${
        newer
          ? `<a class="btn-ghost" href="${escapeHtml(detailUrl(newer.date))}">← ${escapeHtml(formatDateLabel(newer.date))}</a>`
          : `<span class="btn-ghost is-disabled">← Tidak ada yang lebih baru</span>`
      }
      ${
        older
          ? `<a class="btn-ghost" href="${escapeHtml(detailUrl(older.date))}">${escapeHtml(formatDateLabel(older.date))} →</a>`
          : `<span class="btn-ghost is-disabled">Tidak ada yang lebih lama →</span>`
      }
    </nav>
  `;
}

function render(item, meta, igCaption, outputs, index) {
  const title = meta?.title || "Daily News Clip";
  const dateLabel = formatDateLabel(item.date);
  const timeLabel = formatTimeLabel(item.final_video);
  const hashtags = buildHashtags(meta?.tags, 8);
  const sourceUrl = meta?.source_url;

  document.title = `${title} · AIPreneur News`;
  if (detailBadge) detailBadge.textContent = dateLabel;

  detailRoot.innerHTML = `
    <section class="panel detail-head">
      <span class="output-stamp">
        ${escapeHtml(dateLabel)}${timeLabel ? ` · dirender ${escapeHtml(timeLabel)} WIB` : ""}
      </span>
      <h1 class="detail-title">${escapeHtml(title)}</h1>
      ${meta?.hook ? `<p class="detail-hook">${escapeHtml(meta.hook)}</p>` : ""}
      <div class="output-tags">
        ${hashtags.map((tag) => `<span class="chip">${escapeHtml(tag)}</span>`).join("")}
      </div>
      ${
        sourceUrl
          ? `<a class="source-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">Sumber berita ↗</a>`
          : ""
      }
    </section>

    <div class="detail-columns">
      <section class="panel">
        <div class="panel-head"><h2>Video</h2></div>
        ${
          item.final_video
            ? `<div class="player">
                 <video controls preload="metadata" playsinline
                        src="${escapeHtml(outputUrl(item, item.final_video))}"></video>
               </div>
               <p class="panel-hint player-caption">${escapeHtml(item.final_video.name)} · ${escapeHtml(
                 formatBytes(item.final_video.size),
               )}</p>`
            : `<p class="empty-state">Video belum tersedia untuk tanggal ini.</p>`
        }
      </section>

      <aside class="stack">
        <section class="panel">
          <div class="panel-head"><h2>Thumbnail</h2></div>
          ${
            item.thumbnail
              ? `<div class="thumb-frame"><img src="${escapeHtml(outputUrl(item, item.thumbnail))}" alt="Thumbnail ${escapeHtml(title)}" /></div>`
              : `<p class="empty-state">Belum ada thumbnail.</p>`
          }
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Berkas</h2></div>
          ${renderFileRows(item)}
        </section>
      </aside>
    </div>

    <section class="panel">
      <div class="panel-head"><h2>Naskah &amp; Caption</h2></div>
      ${renderTextBlock("Deskripsi", meta?.description_text || meta?.description)}
      ${renderTextBlock("Naskah voiceover", meta?.script_voiceover)}
      ${renderTextBlock("Caption Instagram", igCaption || meta?.ig_caption)}
      ${
        !meta
          ? `<p class="empty-state">script.json tidak bisa dibaca, jadi metadata naskah tidak tersedia.</p>`
          : ""
      }
    </section>

    ${renderNav(outputs, index)}
  `;

  tagVideoOrientation(detailRoot.querySelector("video"));
}

async function init() {
  const date = requestedDate();
  if (!date) {
    showMessage(`Tanggal output tidak disebutkan. <a href="/">Kembali ke dashboard</a>.`);
    return;
  }

  let outputs = [];
  try {
    const data = await fetchJson("/api/outputs/");
    outputs = data.outputs || [];
  } catch (error) {
    showMessage(`Gagal memuat data: ${escapeHtml(error.message)}`);
    return;
  }

  const index = outputs.findIndex((entry) => entry.date === date);
  if (index === -1) {
    showMessage(
      `Output untuk <strong>${escapeHtml(date)}</strong> tidak ditemukan. <a href="/">Kembali ke dashboard</a>.`,
    );
    return;
  }

  const item = outputs[index];
  const [meta, igCaption] = await Promise.all([
    loadScriptMeta(item),
    loadTextFile(item, item.ig_caption_file),
  ]);
  render(item, meta, igCaption, outputs, index);
}

init().catch((error) => showMessage(`Terjadi kesalahan: ${escapeHtml(error.message)}`));
