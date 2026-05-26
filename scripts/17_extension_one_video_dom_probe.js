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

  const collectButtonCandidates = () => {
    const keywords = ["원문", "Transcript", "스크립트", "자막"];
    const nodes = [...document.querySelectorAll("button, div, span, a")]
      .filter(isVisible)
      .map((element) => {
        const text = normalize(element.innerText);
        return {
          element,
          text,
          tag: element.tagName,
          cls: String(element.className || ""),
          rect: element.getBoundingClientRect(),
        };
      })
      .filter((item) => {
        if (!item.text) return false;
        return keywords.some((keyword) => item.text.includes(keyword));
      })
      .sort((left, right) => left.text.length - right.text.length);

    return nodes;
  };

  const collectPanelCandidates = () => {
    return [...document.querySelectorAll("div, section, article, aside")]
      .filter(isVisible)
      .map((element) => {
        const text = normalize(element.innerText);
        return {
          element,
          text,
          tag: element.tagName,
          cls: String(element.className || ""),
          len: text.length,
          lines: text.split("\n").filter(Boolean).length,
          rect: element.getBoundingClientRect(),
        };
      })
      .filter((item) => item.len >= 200)
      .sort((left, right) => {
        if (right.lines !== left.lines) return right.lines - left.lines;
        return right.len - left.len;
      });
  };

  const buttonCandidates = collectButtonCandidates();
  const panelCandidates = collectPanelCandidates();

  window.__oneVideoExtensionProbe = {
    buttonCandidates,
    panelCandidates,
    clickButton(idx = 0) {
      const item = buttonCandidates[idx];
      if (!item) {
        console.warn("No button candidate at index:", idx);
        return null;
      }
      console.log("CLICK BUTTON:", idx, item.text, item.element);
      item.element.click();
      return item;
    },
    exportPanel(idx = 0) {
      const item = panelCandidates[idx];
      if (!item) {
        console.warn("No panel candidate at index:", idx);
        return null;
      }
      const payload = {
        extracted_at: new Date().toISOString(),
        candidate_idx: idx,
        tag_name: item.tag,
        class_name: item.cls,
        text_length: item.len,
        line_count: item.lines,
        transcript_text: item.text,
      };
      console.log("EXPORT PANEL:", payload);
      return payload;
    },
  };

  console.log("=== BUTTON CANDIDATES ===");
  console.table(
    buttonCandidates.slice(0, 20).map((item, idx) => ({
      idx,
      text: item.text.slice(0, 120),
      tag: item.tag,
      cls: item.cls.slice(0, 80),
      x: Math.round(item.rect.x),
      y: Math.round(item.rect.y),
    })),
  );

  console.log("=== PANEL CANDIDATES ===");
  console.table(
    panelCandidates.slice(0, 15).map((item, idx) => ({
      idx,
      len: item.len,
      lines: item.lines,
      tag: item.tag,
      cls: item.cls.slice(0, 80),
      preview: item.text.slice(0, 160),
    })),
  );

  console.log("Use window.__oneVideoExtensionProbe.clickButton(idx)");
  console.log("Then use window.__oneVideoExtensionProbe.exportPanel(idx)");
})();
