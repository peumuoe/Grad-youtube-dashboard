(() => {
  if (!window.__notegptExporter) {
    console.warn("Load scripts/18_notegpt_export_current_transcript.js first.");
    return;
  }

  const getVideoId = () => {
    try {
      return new URL(window.location.href).searchParams.get("v") || "";
    } catch {
      return "";
    }
  };

  const state = {
    timer: null,
    lastVideoId: getVideoId(),
    processed: new Set(),
    running: false,
    delayMs: 3500,
    isExporting: false,
  };

  const scheduleExport = (reason = "manual") => {
    if (!state.running) return;
    window.clearTimeout(state.timer);
    state.timer = window.setTimeout(async () => {
      const videoId = getVideoId();
      if (!videoId || state.processed.has(videoId) || state.isExporting) {
        return;
      }

      state.isExporting = true;
      console.log(`[NoteGPT watcher] exporting video=${videoId} reason=${reason}`);
      try {
        const payload = await window.__notegptExporter.openTranscriptAndExport();
        if (payload?.video_id) {
          state.processed.add(payload.video_id);
          console.log(`[NoteGPT watcher] done video=${payload.video_id}`);
        } else {
          console.warn(`[NoteGPT watcher] export returned no payload for video=${videoId}`);
        }
      } catch (error) {
        console.warn(`[NoteGPT watcher] export failed for video=${videoId}`, error);
      } finally {
        state.isExporting = false;
      }
    }, state.delayMs);
  };

  const onUrlMaybeChanged = (reason = "poll") => {
    const currentVideoId = getVideoId();
    if (!currentVideoId) return;
    if (currentVideoId !== state.lastVideoId) {
      console.log(`[NoteGPT watcher] detected video change ${state.lastVideoId} -> ${currentVideoId}`);
      state.lastVideoId = currentVideoId;
      scheduleExport(reason);
      return;
    }

    if (!state.processed.has(currentVideoId)) {
      scheduleExport(reason);
    }
  };

  const poller = window.setInterval(() => onUrlMaybeChanged("poll"), 1500);

  const start = () => {
    state.running = true;
    onUrlMaybeChanged("start");
  };

  const stop = () => {
    state.running = false;
    window.clearTimeout(state.timer);
  };

  window.addEventListener("yt-navigate-finish", () => onUrlMaybeChanged("yt-navigate-finish"));
  window.addEventListener("popstate", () => onUrlMaybeChanged("popstate"));

  window.__notegptWatcher = {
    start,
    stop,
    state,
    scheduleExport,
    onUrlMaybeChanged,
    poller,
  };

  console.log("NoteGPT video watcher ready.");
  console.log("Run: window.__notegptWatcher.start()");
  console.log("Stop: window.__notegptWatcher.stop()");
})();
