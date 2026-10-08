// UI logic. Python methods are available as window.pywebview.api.<name>() and return Promises.

const $ = (id) => document.getElementById(id);
let folder = null;
let pollTimer = null;

function formatSize(bytes) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return (i === 0 ? bytes : bytes.toFixed(1)) + " " + units[i];
}

function showError(message) {
  $("error").textContent = message || "";
  $("error").hidden = !message;
}

// Lock the controls while a run is in progress.
function setRunning(running) {
  $("pick").disabled = running;
  $("start").disabled = running || !folder;
  $("cancel").hidden = !running;
  $("cancel").disabled = false;
  document.querySelectorAll("input[name=level]").forEach((r) => (r.disabled = running));
  $("webp").disabled = running;
  $("gif").disabled = running;
}

// Elapsed time on the current file, so long GIFs/videos visibly keep working.
let fileStarted = 0;
let lastFile = null;

function render(p) {
  const finished = p.status !== "running";
  const done = finished ? p.index : Math.max(p.index - 1, 0); // files fully handled
  $("bar-fill").style.width = (p.total ? (done / p.total) * 100 : 100) + "%";
  $("count").textContent = `File ${p.index} of ${p.total}`;
  $("current").textContent = p.current;

  if (p.current !== lastFile) {
    lastFile = p.current;
    fileStarted = Date.now();
  }
  const secs = Math.floor((Date.now() - fileStarted) / 1000);
  let state = "";
  if (!finished && p.cancel_requested) state = p.gif ? "Stopping…" : "Stopping after this file…";
  else if (!finished && secs >= 3) state = `Working… ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
  $("state").textContent = state;
}

function showSummary(p) {
  const titles = { done: "Done", cancelled: "Cancelled", error: "Something went wrong" };
  $("summary-title").textContent = titles[p.status] || "Done";
  $("s-processed").textContent = p.processed;
  $("s-skipped").textContent = p.skipped;
  $("s-failed").textContent = p.failed;
  const saved = p.original_bytes ? Math.round((1 - p.new_bytes / p.original_bytes) * 100) : 0;
  $("s-size").textContent =
    `${formatSize(p.original_bytes)} → ${formatSize(p.new_bytes)} (${saved}% saved)`;
  $("s-webp").textContent = p.webp
    ? `Convert images to WebP: on (${p.webp_converted} image${p.webp_converted === 1 ? "" : "s"} converted)`
    : "Convert images to WebP: off";
  $("s-gif").textContent = p.gif
    ? `Transform videos to GIF: on (${p.gif_converted} video${p.gif_converted === 1 ? "" : "s"} converted)`
    : "Transform videos to GIF: off";
  $("s-gif-warn").hidden = !p.gif_large;
  $("s-gif-warn").textContent = p.gif_large === 1
    ? "1 GIF is larger than the original video or over 50 MB (see log.txt)."
    : `${p.gif_large} GIFs are larger than the original video or over 50 MB (see log.txt).`;
  $("open").hidden = !p.output_dir;
  $("summary").hidden = false;
  if (p.status === "error") showError(p.message);
}

async function poll() {
  const p = await window.pywebview.api.get_progress();
  render(p);
  if (p.status !== "running") {
    clearInterval(pollTimer);
    pollTimer = null;
    setRunning(false);
    closeModal(false); // a cancel popup is pointless once the run has ended
    showSummary(p);
  }
}

$("pick").addEventListener("click", async () => {
  const path = await window.pywebview.api.pick_folder();
  if (path) {
    folder = path;
    $("folder").textContent = path;
    $("folder").classList.remove("muted");
    $("start").disabled = false;
  }
});

$("start").addEventListener("click", async () => {
  const level = document.querySelector("input[name=level]:checked").value;
  showError("");
  const toWebp = $("webp").checked;
  const toGif = $("gif").checked;
  const result = await window.pywebview.api.start(folder, level, toWebp, toGif);
  if (!result.ok) {
    showError(result.error);
    return;
  }
  $("summary").hidden = true;
  $("progress").hidden = false;
  setRunning(true);
  pollTimer = setInterval(poll, 300);
});

// Simple popup. Resolves true if the user clicks the "yes" button, false otherwise.
let modalResolve = null;

function askUser(title, text, yesLabel, noLabel) {
  if (modalResolve) return Promise.resolve(false); // a popup is already open
  $("modal-title").textContent = title;
  $("modal-text").textContent = text;
  $("modal-yes").textContent = yesLabel;
  $("modal-no").textContent = noLabel;
  $("modal").hidden = false;
  $("modal-no").focus();
  return new Promise((resolve) => (modalResolve = resolve));
}

function closeModal(answer) {
  $("modal").hidden = true;
  if (modalResolve) modalResolve(answer);
  modalResolve = null;
}

$("modal-yes").addEventListener("click", () => closeModal(true));
$("modal-no").addEventListener("click", () => closeModal(false));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && modalResolve) closeModal(false);
});

async function confirmCancel(title, text) {
  const yes = await askUser(title, text, "Yes, cancel", "Keep going");
  // Only cancel if the run is still going (it may have finished while the popup was open).
  if (yes && !$("cancel").hidden) {
    $("cancel").disabled = true;
    window.pywebview.api.cancel();
  }
}

$("cancel").addEventListener("click", () =>
  confirmCancel(
    "Cancel optimization?",
    "The file being processed now will finish, then the run stops. " +
      ($("gif").checked ? "A GIF that is still being made is stopped right away and not saved. " : "") +
      "Files already done stay in the output folder."
  )
);

// Called from Python when the user tries to close the window during a run.
function showCloseBlocked() {
  confirmCancel(
    "Optimization in progress",
    "The app can't be closed while files are being optimized. " +
      "Cancel first (the current file will finish), then close the window."
  );
}

$("open").addEventListener("click", () => window.pywebview.api.open_output());

// The Python API is only usable after pywebview has injected it.
window.addEventListener("pywebviewready", () => {
  $("pick").disabled = false;
});
