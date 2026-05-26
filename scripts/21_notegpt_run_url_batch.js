(() => {
  if (!window.__notegptExporter) {
    console.warn("Load scripts/18_notegpt_export_current_transcript.js first.");
    return;
  }

  const DEFAULT_URLS = [
    "https://www.youtube.com/watch?v=JQB92KeQ5oo",
    "https://www.youtube.com/watch?v=OBz5o8EkjPk",
    "https://www.youtube.com/watch?v=5EtxutAb2tA",
    "https://www.youtube.com/watch?v=b4ySI0ZE7tk",
    "https://www.youtube.com/watch?v=PfTvcz8WGlg",
    "https://www.youtube.com/watch?v=fB3DNcX6fn0",
    "https://www.youtube.com/watch?v=83mFcg5-7NQ",
    "https://www.youtube.com/watch?v=2oS0E61EHHY",
    "https://www.youtube.com/watch?v=V8Lp7FXJ8i8",
    "https://www.youtube.com/watch?v=dRDPIoYIi5Q",
  ];

  const getVideoIdFromUrl = (url) => {
    try {
      return new URL(url).searchParams.get("v") || "";
    } catch {
      return "";
    }
  };

  const state = {
    urls: DEFAULT_URLS.slice(),
    index: 0,
    running: false,
    exported: [],
    failed: [],
    betweenVideosMs: 2500,
    afterExportMs: 2000,
    transcriptTimeoutMs: 45000,
    pollMs: 1200,
    timer: null,
  };

  const stop = () => {
    state.running = false;
    window.clearTimeout(state.timer);
    console.log("[NoteGPT batch] stopped.");
  };

  const waitForUrl = async (expectedUrl) => {
    const expectedVideoId = getVideoIdFromUrl(expectedUrl);
    const startedAt = Date.now();
    while (Date.now() - startedAt < 15000) {
      const currentVideoId = new URL(window.location.href).searchParams.get("v") || "";
      if (currentVideoId === expectedVideoId) return true;
      await new Promise((resolve) => window.setTimeout(resolve, 400));
    }
    return false;
  };

  const runOne = async (url) => {
    const videoId = getVideoIdFromUrl(url);
    console.log(`[NoteGPT batch] navigating to ${videoId}`);
    window.location.href = url;
    const loaded = await waitForUrl(url);
    if (!loaded) {
      throw new Error(`Navigation timeout for ${videoId}`);
    }

    await new Promise((resolve) => window.setTimeout(resolve, state.betweenVideosMs));

    const exportPromise = window.__notegptExporter.openTranscriptAndExport();
    const timeoutPromise = new Promise((_, reject) => {
      window.setTimeout(() => reject(new Error(`Transcript timeout for ${videoId}`)), state.transcriptTimeoutMs);
    });

    const payload = await Promise.race([exportPromise, timeoutPromise]);
    if (!payload?.video_id) {
      throw new Error(`No payload returned for ${videoId}`);
    }

    state.exported.push({
      video_id: payload.video_id,
      title: payload.title,
      text_length: payload.text_length,
      line_count: payload.line_count,
    });
    console.log(`[NoteGPT batch] exported ${payload.video_id}`);
    await new Promise((resolve) => window.setTimeout(resolve, state.afterExportMs));
  };

  const start = async (urls = DEFAULT_URLS) => {
    if (state.running) {
      console.warn("[NoteGPT batch] already running.");
      return;
    }

    state.running = true;
    state.urls = urls.slice();
    state.index = 0;
    state.exported = [];
    state.failed = [];

    console.log(`[NoteGPT batch] starting with ${state.urls.length} urls`);

    for (let index = 0; index < state.urls.length; index += 1) {
      if (!state.running) break;
      const url = state.urls[index];
      state.index = index;
      try {
        await runOne(url);
      } catch (error) {
        const videoId = getVideoIdFromUrl(url);
        console.warn(`[NoteGPT batch] failed ${videoId}`, error);
        state.failed.push({
          url,
          video_id: videoId,
          error: String(error?.message || error),
        });
      }
    }

    state.running = false;
    console.log("[NoteGPT batch] finished.", {
      exported: state.exported.length,
      failed: state.failed.length,
    });
    return {
      exported: state.exported,
      failed: state.failed,
    };
  };

  window.__notegptBatchRunner = {
    start,
    stop,
    state,
    DEFAULT_URLS,
  };

  console.log("NoteGPT batch runner ready.");
  console.log("Run: window.__notegptBatchRunner.start()");
  console.log("Stop: window.__notegptBatchRunner.stop()");
})();
