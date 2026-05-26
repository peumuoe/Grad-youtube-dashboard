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

  const buildCandidates = () => {
    return [...document.querySelectorAll("div, section, article, aside")]
      .filter(isVisible)
      .map((element) => {
        const text = normalize(element.innerText);
        return {
          element,
          text,
          len: text.length,
          lines: text.split("\n").filter(Boolean).length,
          className: String(element.className || ""),
          tagName: element.tagName,
        };
      })
      .filter((item) => item.len >= 300)
      .sort((left, right) => {
        if (right.lines !== left.lines) return right.lines - left.lines;
        return right.len - left.len;
      });
  };

  const scoreCandidate = (item) => {
    let score = 0;
    if (item.lines >= 8) score += 4;
    if (item.len >= 1200) score += 3;
    if (/transcript|script|summary|caption|subtitle/i.test(item.className)) score += 4;
    if (!/댓글|조회수|좋아요|공유|저장|구독|youtube/i.test(item.text)) score += 2;
    if ((item.text.match(/\n/g) || []).length >= 5) score += 2;
    if (/^\d{1,2}:\d{2}/m.test(item.text)) score += 1;
    return score;
  };

  const makeTable = (items) =>
    items.slice(0, 15).map((item, idx) => ({
      idx,
      score: scoreCandidate(item),
      len: item.len,
      lines: item.lines,
      tag: item.tagName,
      cls: item.className.slice(0, 80),
      preview: item.text.slice(0, 160),
    }));

  const listCandidates = () => {
    const candidates = buildCandidates();
    window.__extTranscriptCandidates = candidates;
    console.table(makeTable(candidates));
    return candidates;
  };

  const exportCandidate = async (idx = 0) => {
    const candidates = window.__extTranscriptCandidates || buildCandidates();
    const item = candidates[idx];
    if (!item) {
      console.warn("No candidate found at index:", idx);
      return null;
    }

    const payload = {
      extracted_at: new Date().toISOString(),
      candidate_idx: idx,
      tag_name: item.tagName,
      class_name: item.className,
      text_length: item.len,
      line_count: item.lines,
      transcript_text: item.text,
    };

    try {
      await navigator.clipboard.writeText(item.text);
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
      link.download = `browser_extension_transcript_${Date.now()}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      console.log("Downloaded candidate payload JSON.");
    } catch (error) {
      console.warn("Download failed:", error);
    }

    console.log("EXPORTED CANDIDATE:", payload);
    return payload;
  };

  window.__extTranscriptProbe = {
    listCandidates,
    exportCandidate,
  };

  console.log("Extension transcript probe ready.");
  console.log("1) Open the extension transcript panel.");
  console.log("2) Run window.__extTranscriptProbe.listCandidates()");
  console.log("3) Run window.__extTranscriptProbe.exportCandidate(idx)");
})();
