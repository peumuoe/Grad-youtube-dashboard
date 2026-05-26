// ==UserScript==
// @name         Grad NoteGPT Batch Runner
// @namespace    https://grad.local/
// @version      0.1.0
// @description  Persist across YouTube page navigation and export NoteGPT transcripts in sequence.
// @match        https://www.youtube.com/watch*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const STORAGE_KEY = "__grad_notegpt_batch_state_v1";
  const MAX_RETRIES_PER_VIDEO = 2;

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

  const normalize = (value) =>
    String(value || "")
      .replace(/\u00a0/g, " ")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();

  const isVisible = (element) => {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      rect.width > 0 &&
      rect.height > 0
    );
  };

  const getVideoIdFromUrl = (url) => {
    try {
      return new URL(url).searchParams.get("v") || "";
    } catch {
      return "";
    }
  };

  const getCurrentVideoId = () => getVideoIdFromUrl(window.location.href);

  const loadState = () => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return {
          running: false,
          urls: DEFAULT_URLS.slice(),
          index: 0,
          retries: {},
          exported: [],
          failed: [],
        };
      }
      const parsed = JSON.parse(raw);
      return {
        running: Boolean(parsed.running),
        urls: Array.isArray(parsed.urls) ? parsed.urls : DEFAULT_URLS.slice(),
        index: Number.isInteger(parsed.index) ? parsed.index : 0,
        retries: parsed.retries && typeof parsed.retries === "object" ? parsed.retries : {},
        exported: Array.isArray(parsed.exported) ? parsed.exported : [],
        failed: Array.isArray(parsed.failed) ? parsed.failed : [],
      };
    } catch {
      return {
        running: false,
        urls: DEFAULT_URLS.slice(),
        index: 0,
        retries: {},
        exported: [],
        failed: [],
      };
    }
  };

  const saveState = (state) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  };

  const collectCandidates = () => {
    return [...document.querySelectorAll("div, section, article, aside")]
      .filter(isVisible)
      .map((element) => {
        const text = normalize(element.innerText);
        const rect = element.getBoundingClientRect();
        return {
          element,
          text,
          len: text.length,
          lines: text.split("\n").filter(Boolean).length,
          cls: String(element.className || ""),
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          w: Math.round(rect.width),
          h: Math.round(rect.height),
        };
      })
      .filter((item) => item.len > 300)
      .sort((left, right) => {
        if (right.x !== left.x) return right.x - left.x;
        if (right.lines !== left.lines) return right.lines - left.lines;
        return right.len - left.len;
      });
  };

  const looksLikeTranscriptPanel = (item) => {
    if (!item) return false;
    if (item.x < 700) return false;
    if (item.w > 520) return false;
    if (item.lines < 8) return false;
    if (/Extracting video content/i.test(item.text)) return false;
    if (/관련 콘텐츠|최근에 업로드된 동영상|조회수 .*회|새 동영상/i.test(item.text)) return false;
    if (/ytd-watch-flexy|ytd-watch-metadata/i.test(item.cls)) return false;
    const lines = item.text.split("\n").map((line) => line.trim()).filter(Boolean);
    const timestampLineCount = lines.filter((line) => /^\d{2}:\d{2}$/.test(line)).length;
    return timestampLineCount >= 2;
  };

  const cleanTranscript = (rawText) => {
    const rawLines = String(rawText || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);

    return rawLines.filter((line) => {
      if (/^Save as Note$/i.test(line)) return false;
      if (/^Find word$/i.test(line)) return false;
      if (/^Read More$/i.test(line)) return false;
      if (/^NoteGPT$/i.test(line)) return false;
      if (/^Log In$/i.test(line)) return false;
      if (/^[<>]$/.test(line)) return false;
      return true;
    });
  };

  const collectTranscriptButtons = () => {
    return [...document.querySelectorAll("button, div, span, a")]
      .filter(isVisible)
      .map((element) => {
        const text = normalize(element.innerText);
        const rect = element.getBoundingClientRect();
        return {
          element,
          text,
          tag: element.tagName,
          cls: String(element.className || ""),
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          w: Math.round(rect.width),
          h: Math.round(rect.height),
        };
      })
      .filter((item) => item.x >= 700)
      .filter((item) => /transcript|script|자막|원문/i.test(item.text))
      .sort((left, right) => left.text.length - right.text.length);
  };

  const waitForTranscriptPanel = async (timeoutMs = 30000, pollMs = 700) => {
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      const candidates = collectCandidates();
      const candidateIdx = candidates.findIndex(looksLikeTranscriptPanel);
      if (candidateIdx >= 0) {
        return { candidates, candidateIdx };
      }
      await new Promise((resolve) => window.setTimeout(resolve, pollMs));
    }
    return { candidates: collectCandidates(), candidateIdx: -1 };
  };

  const exportCurrent = async () => {
    const { candidates, candidateIdx } = await waitForTranscriptPanel();
    if (candidateIdx < 0) {
      throw new Error("No NoteGPT transcript-like panel candidate found.");
    }

    const selected = candidates[candidateIdx];
    const cleanedLines = cleanTranscript(selected.text);
    const transcriptText = cleanedLines.join("\n");
    const videoId = getCurrentVideoId();
    const title =
      normalize(document.querySelector("h1.ytd-watch-metadata")?.innerText) ||
      normalize(document.title.replace(/\s*-\s*YouTube\s*$/i, ""));

    const payload = {
      extracted_at: new Date().toISOString(),
      candidate_idx: candidateIdx,
      candidate_class_name: selected.cls,
      text_length: transcriptText.length,
      line_count: cleanedLines.length,
      url: window.location.href,
      title,
      video_id: videoId,
      transcript_text: transcriptText,
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${videoId || `notegpt_${Date.now()}`}_transcript.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();

    return payload;
  };

  const openTranscriptAndExport = async () => {
    const buttons = collectTranscriptButtons();
    if (!buttons.length) {
      throw new Error("No transcript-like button found.");
    }
    buttons[0].element.click();
    await new Promise((resolve) => window.setTimeout(resolve, 2500));
    return exportCurrent();
  };

  const maybeRun = async () => {
    const state = loadState();
    if (!state.running) return;

    const targetUrl = state.urls[state.index];
    if (!targetUrl) {
      state.running = false;
      saveState(state);
      console.log("[Grad NoteGPT] batch finished.", state);
      return;
    }

    const targetVideoId = getVideoIdFromUrl(targetUrl);
    const currentVideoId = getCurrentVideoId();

    if (currentVideoId !== targetVideoId) {
      console.log(`[Grad NoteGPT] navigating to ${targetVideoId}`);
      window.location.href = targetUrl;
      return;
    }

    if (state.exported.some((item) => item.video_id === currentVideoId)) {
      delete state.retries[currentVideoId];
      state.index += 1;
      saveState(state);
      window.setTimeout(maybeRun, 1200);
      return;
    }

    console.log(`[Grad NoteGPT] exporting ${currentVideoId}`);
    try {
      const payload = await openTranscriptAndExport();
      state.exported.push({
        video_id: payload.video_id,
        title: payload.title,
        text_length: payload.text_length,
      });
      delete state.retries[currentVideoId];
      state.index += 1;
      saveState(state);
      window.setTimeout(maybeRun, 2200);
    } catch (error) {
      const nextRetry = Number(state.retries[currentVideoId] || 0) + 1;
      state.retries[currentVideoId] = nextRetry;
      saveState(state);

      if (nextRetry <= MAX_RETRIES_PER_VIDEO) {
        console.warn(`[Grad NoteGPT] export failed for ${currentVideoId}; retry ${nextRetry}/${MAX_RETRIES_PER_VIDEO}`, error);
        window.setTimeout(() => {
          window.location.reload();
        }, 1500);
        return;
      }

      state.failed.push({
        video_id: currentVideoId,
        url: targetUrl,
        retries: nextRetry - 1,
        error: String(error?.message || error),
      });
      delete state.retries[currentVideoId];
      state.index += 1;
      saveState(state);
      console.warn("[Grad NoteGPT] export failed permanently", error);
      window.setTimeout(maybeRun, 2200);
    }
  };

  window.__gradNoteGPTBatch = {
    start(urls = DEFAULT_URLS) {
      const state = loadState();
      state.urls = urls.slice();
      state.index = 0;
      state.retries = {};
      state.exported = [];
      state.failed = [];
      state.running = true;
      saveState(state);
      maybeRun();
    },
    stop() {
      const state = loadState();
      state.running = false;
      saveState(state);
      console.log("[Grad NoteGPT] stopped.");
    },
    state() {
      return loadState();
    },
    maybeRun,
    DEFAULT_URLS,
  };

  console.log("Grad NoteGPT Tampermonkey batch runner ready.");
  console.log("Start: window.__gradNoteGPTBatch.start()");
  console.log("Stop:  window.__gradNoteGPTBatch.stop()");
  console.log("State: window.__gradNoteGPTBatch.state()");

  const persistedState = loadState();
  if (persistedState.running) {
    console.log("[Grad NoteGPT] resuming persisted batch state...", persistedState);
    window.setTimeout(maybeRun, 1200);
  }
})();
