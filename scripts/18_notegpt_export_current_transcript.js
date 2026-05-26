(() => {
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
      .filter((item) => /transcript|원문|script|자막/i.test(item.text))
      .sort((left, right) => {
        if (right.x !== left.x) return right.x - left.x;
        return left.text.length - right.text.length;
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
    if (timestampLineCount < 2) return false;
    return true;
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

  const getVideoMetadata = () => {
    const url = window.location.href;
    const title =
      normalize(document.querySelector("h1.ytd-watch-metadata")?.innerText) ||
      normalize(document.title.replace(/\s*-\s*YouTube\s*$/i, ""));
    const videoId =
      new URL(url).searchParams.get("v") ||
      (url.match(/[?&]v=([^&]+)/)?.[1] ?? "");

    return { url, title, video_id: videoId };
  };

  const waitForTranscriptPanel = async (timeoutMs = 25000, pollMs = 700) => {
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
      console.warn("No NoteGPT transcript-like panel candidate found.");
      console.table(
        candidates.slice(0, 20).map((item, idx) => ({
          idx,
          x: item.x,
          y: item.y,
          w: item.w,
          h: item.h,
          len: item.len,
          lines: item.lines,
          cls: item.cls.slice(0, 80),
          preview: item.text.slice(0, 120),
        })),
      );
      return null;
    }

    const selected = candidates[candidateIdx];
    const cleanedLines = cleanTranscript(selected.text);
    const transcriptText = cleanedLines.join("\n");
    const metadata = getVideoMetadata();

    const payload = {
      extracted_at: new Date().toISOString(),
      candidate_idx: candidateIdx,
      candidate_class_name: selected.cls,
      text_length: transcriptText.length,
      line_count: cleanedLines.length,
      ...metadata,
      transcript_text: transcriptText,
    };

    try {
      await navigator.clipboard.writeText(transcriptText);
      console.log("Transcript copied to clipboard.");
    } catch (error) {
      console.warn("Clipboard copy failed:", error);
    }

    try {
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      const safeId = metadata.video_id || `notegpt_${Date.now()}`;
      link.download = `${safeId}_transcript.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      console.log("Transcript JSON downloaded.");
    } catch (error) {
      console.warn("Download failed:", error);
    }

    console.log("EXPORTED TRANSCRIPT:", payload);
    return payload;
  };

  const openTranscriptAndExport = async () => {
    const buttons = collectTranscriptButtons();
    if (!buttons.length) {
      console.warn("No transcript-like button found on the right panel.");
      console.table(
        [...document.querySelectorAll("button, div, span, a")]
          .filter(isVisible)
          .map((element) => {
            const rect = element.getBoundingClientRect();
            return {
              text: normalize(element.innerText).slice(0, 80),
              tag: element.tagName,
              x: Math.round(rect.x),
              y: Math.round(rect.y),
              cls: String(element.className || "").slice(0, 80),
            };
          })
          .filter((item) => item.x >= 700)
          .slice(0, 30),
      );
      return null;
    }

    const button = buttons[0];
    console.log("CLICKING TRANSCRIPT BUTTON:", button.text, button);
    button.element.click();
    await new Promise((resolve) => window.setTimeout(resolve, 2500));
    return exportCurrent();
  };

  window.__notegptExporter = {
    exportCurrent,
    collectCandidates,
    collectTranscriptButtons,
    openTranscriptAndExport,
  };

  console.log("NoteGPT exporter ready.");
  console.log("Run: window.__notegptExporter.exportCurrent()");
  console.log("Or:  window.__notegptExporter.openTranscriptAndExport()");
})();
