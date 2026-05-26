from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.common.exceptions import NoSuchWindowException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


LOGGER = logging.getLogger("notegpt_selenium_one_video")
RETRYABLE_ERROR_SNIPPETS = (
    "Payload video mismatch detected.",
    "Video mismatch detected.",
)
NON_RETRYABLE_ERROR_SNIPPETS = (
    "NoteGPT reported no subtitles for this video.",
    "NoteGPT requires login before transcription.",
)

FIND_TRANSCRIPT_BUTTON_JS = r"""
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

const transcriptPattern = /\b(generate\s+transcript|transcript)\b|자막|원문/i;
const rejectPattern = /\b(save as note|find word|read more|log in|generate summary|ask|share|save)\b/i;
const interactiveSelector = 'button, [role="button"], div, span';

const noteRoots = [...document.querySelectorAll(
  '.ng-yt-extension-container, [class*="ystn"], [class*="notegpt"], [id*="notegpt"]'
)]
  .filter(isVisible)
  .map((element) => {
    const text = normalize(element.innerText);
    const rect = element.getBoundingClientRect();
    return {
      element,
      text,
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      w: Math.round(rect.width),
      h: Math.round(rect.height),
    };
  })
  .filter((item) => item.x >= 650)
  .filter((item) => item.w >= 220 && item.w <= 520)
  .filter((item) => /notegpt|transcript|summary|save as note/i.test(item.text))
  .sort((left, right) => {
    if (right.x !== left.x) return right.x - left.x;
    return right.h - left.h;
  });

const collectCandidates = (rootElement) =>
  [...rootElement.querySelectorAll(interactiveSelector)]
    .filter(isVisible)
    .map((element) => {
      const text = normalize(element.innerText || element.getAttribute("aria-label"));
      const rect = element.getBoundingClientRect();
      let score = 0;
      if (/^generate transcript$/i.test(text)) score += 100;
      if (/^transcript$/i.test(text)) score += 80;
      if (/generate transcript/i.test(text)) score += 60;
      if (/transcript|자막|원문/i.test(text)) score += 40;
      if (element.tagName === "BUTTON") score += 10;
      if (rect.width >= 80 && rect.width <= 240) score += 5;
      return {
        element,
        text,
        score,
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      };
    })
    .filter((item) => item.x >= 650)
    .filter((item) => transcriptPattern.test(item.text))
    .filter((item) => !rejectPattern.test(item.text))
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score;
      return left.text.length - right.text.length;
    });

for (const root of noteRoots) {
  const candidates = collectCandidates(root.element);
  if (candidates.length) {
    return candidates[0].element;
  }
}

const fallbackCandidates = [...document.querySelectorAll(interactiveSelector)]
  .filter(isVisible)
  .map((element) => {
    const text = normalize(element.innerText || element.getAttribute("aria-label"));
    const rect = element.getBoundingClientRect();
    let score = 0;
    if (/^generate transcript$/i.test(text)) score += 100;
    if (/^transcript$/i.test(text)) score += 80;
    if (/generate transcript/i.test(text)) score += 60;
    if (/transcript|자막|원문/i.test(text)) score += 40;
    if (element.tagName === "BUTTON") score += 10;
    return {
      element,
      text,
      score,
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      w: Math.round(rect.width),
      h: Math.round(rect.height),
    };
  })
  .filter((item) => item.x >= 650)
  .filter((item) => item.w >= 60 && item.w <= 260)
  .filter((item) => transcriptPattern.test(item.text))
  .filter((item) => !rejectPattern.test(item.text))
  .sort((left, right) => {
    if (right.score !== left.score) return right.score - left.score;
    return left.text.length - right.text.length;
  });

return null;
"""

FIND_LOADING_PANEL_JS = r"""
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

const candidates = [...document.querySelectorAll("div, section, article, aside")]
  .filter(isVisible)
  .map((element) => {
    const text = normalize(element.innerText);
    const rect = element.getBoundingClientRect();
    return {
      element,
      text,
      x: Math.round(rect.x),
      w: Math.round(rect.width),
      h: Math.round(rect.height),
    };
  })
  .filter((item) => item.x >= 650)
  .filter((item) => /Extracting video content/i.test(item.text))
  .sort((left, right) => right.h - left.h);

return candidates.length ? candidates[0].element : null;
"""

FIND_TERMINAL_FAILURE_JS = r"""
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

const candidates = [...document.querySelectorAll("div, section, article, aside")]
  .filter(isVisible)
  .map((element) => {
    const text = normalize(element.innerText);
    const rect = element.getBoundingClientRect();
    return {
      text,
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      w: Math.round(rect.width),
      h: Math.round(rect.height),
      cls: String(element.className || ""),
    };
  })
  .filter((item) => item.x >= 650)
  .sort((left, right) => {
    if (right.x !== left.x) return right.x - left.x;
    return right.h - left.h;
  });

for (const item of candidates) {
  if (/no subtitles/i.test(item.text)) {
    return { reason: "no_subtitles", message: "NoteGPT reported no subtitles for this video.", text: item.text.slice(0, 240), cls: item.cls };
  }
  if (/please log in to transcribe|log in to transcribe/i.test(item.text)) {
    return { reason: "login_required", message: "NoteGPT requires login before transcription.", text: item.text.slice(0, 240), cls: item.cls };
  }
  if (/mounted failed|try again/i.test(item.text)) {
    return { reason: "mounted_failed", message: "NoteGPT panel failed to mount.", text: item.text.slice(0, 240), cls: item.cls };
  }
}

return null;
"""

EXTRACT_TRANSCRIPT_JS = r"""
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

const candidates = [...document.querySelectorAll("div, section, article, aside")]
  .filter(isVisible)
  .map((element) => {
    const text = normalize(element.innerText);
    const rect = element.getBoundingClientRect();
    return {
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
  .filter((item) => item.len > 160)
  .sort((left, right) => {
    if (right.x !== left.x) return right.x - left.x;
    if (right.lines !== left.lines) return right.lines - left.lines;
    return right.len - left.len;
  });

const looksLikeTranscriptPanel = (item) => {
  if (!item) return false;
  if (item.x < 650) return false;
  if (item.w > 520) return false;
  if (/Extracting video content/i.test(item.text)) return false;
  if (/관련 콘텐츠|최근에 업로드된 동영상|조회수 .*회|새 동영상/i.test(item.text)) return false;
  if (/ytd-watch-flexy|ytd-watch-metadata/i.test(item.cls)) return false;
  const lines = item.text.split("\n").map((line) => line.trim()).filter(Boolean);
  const timestampLineCount = lines.filter((line) => /^\d{2}:\d{2}$/.test(line)).length;
  const hasOpeningTimestamp = lines.length >= 1 && /^\d{2}:\d{2}$/.test(lines[0]);
  const compactTranscriptClass = /ystn-transcript|ystn-panel-container|ystn-main-container|ystn-no-mini-view|ng-yt-extension-container/i.test(item.cls);
  const compactTranscriptShape =
    compactTranscriptClass &&
    item.w >= 280 &&
    item.w <= 430 &&
    item.lines >= 3 &&
    timestampLineCount >= 1 &&
    item.len >= 180;

  if (compactTranscriptShape) return true;
  if (item.lines < 4) return false;
  if (timestampLineCount >= 2) return true;
  return hasOpeningTimestamp && item.lines >= 3 && item.len >= 180;
};

const candidateIdx = candidates.findIndex(looksLikeTranscriptPanel);
if (candidateIdx < 0) return null;

const selected = candidates[candidateIdx];
const cleanedLines = String(selected.text || "")
  .split("\n")
  .map((line) => line.trim())
  .filter(Boolean)
  .filter((line) => {
    if (/^Save as Note$/i.test(line)) return false;
    if (/^Find word$/i.test(line)) return false;
    if (/^Read More$/i.test(line)) return false;
    if (/^NoteGPT$/i.test(line)) return false;
    if (/^Log In$/i.test(line)) return false;
    if (/^[<>]$/.test(line)) return false;
    return true;
  });

const transcriptText = cleanedLines.join("\n");
const videoId = new URL(window.location.href).searchParams.get("v") || "";
const titleNode = document.querySelector("h1.ytd-watch-metadata");
const title = normalize(titleNode ? titleNode.innerText : document.title.replace(/\s*-\s*YouTube\s*$/i, ""));

return {
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
"""

DEBUG_CANDIDATES_JS = r"""
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

return [...document.querySelectorAll("div, section, article, aside")]
  .filter(isVisible)
  .map((element) => {
    const text = normalize(element.innerText);
    const rect = element.getBoundingClientRect();
    return {
      cls: String(element.className || ""),
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      w: Math.round(rect.width),
      h: Math.round(rect.height),
      len: text.length,
      lines: text.split("\n").filter(Boolean).length,
      timestamp_lines: text.split("\n").map((line) => line.trim()).filter(Boolean).filter((line) => /^\d{2}:\d{2}$/.test(line)).length,
      has_extracting: /Extracting video content/i.test(text),
      preview: text.slice(0, 180),
    };
  })
  .filter((item) => item.len > 120)
  .filter((item) => item.x >= 650)
  .sort((left, right) => {
    if (right.x !== left.x) return right.x - left.x;
    if (right.lines !== left.lines) return right.lines - left.lines;
    return right.len - left.len;
  })
  .slice(0, 15);
"""

PAUSE_VIDEO_JS = r"""
const video = document.querySelector("video");
if (video) {
  try {
    video.pause();
  } catch (error) {}
}
return !!video;
"""

DISABLE_AUTOPLAY_JS = r"""
const selectors = [
  'button[aria-label*="Autoplay"]',
  'button[aria-label*="자동재생"]',
  'ytd-compact-autoplay-renderer tp-yt-paper-toggle-button',
  'tp-yt-paper-toggle-button',
];
for (const selector of selectors) {
  const node = document.querySelector(selector);
  if (!node) continue;
  const pressed = node.getAttribute("aria-pressed");
  if (pressed === "true") {
    node.click();
    return "clicked";
  }
  const checked = node.hasAttribute("checked") || node.getAttribute("aria-checked") === "true";
  if (checked) {
    node.click();
    return "clicked";
  }
  return "already-off";
}
return "not-found";
"""

COLLECTION_TAB_MARKER = "__grad_notegpt_collection_tab__"
MARK_COLLECTION_TAB_JS = r"""
try {
  window.name = arguments[0];
  window.sessionStorage.setItem(arguments[0], "1");
  return "ok";
} catch (error) {
  try {
    window.name = arguments[0];
    return "ok-name-only";
  } catch (nestedError) {
    return "error";
  }
}
"""

GET_COLLECTION_TAB_MARKER_JS = r"""
try {
  const key = String(arguments[0] || "");
  return {
    windowName: String(window.name || ""),
    storageValue: String(window.sessionStorage.getItem(key) || ""),
  };
} catch (error) {
  try {
    const key = String(arguments[0] || "");
    return {
      windowName: String(window.name || ""),
      storageValue: "",
    };
  } catch (nestedError) {
    return {
      windowName: "",
      storageValue: "",
    };
  }
}
"""

DESCRIBE_ACTIVE_ELEMENT_JS = r"""
const describe = (element) => {
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  return {
    tag: String(element.tagName || "").toLowerCase(),
    id: String(element.id || ""),
    cls: String(element.className || ""),
    name: String(element.getAttribute?.("name") || ""),
    role: String(element.getAttribute?.("role") || ""),
    ariaLabel: String(element.getAttribute?.("aria-label") || ""),
    text: String((element.innerText || element.textContent || "")).replace(/\s+/g, " ").trim().slice(0, 140),
    href: String(element.getAttribute?.("href") || ""),
    x: Math.round(rect.x),
    y: Math.round(rect.y),
    w: Math.round(rect.width),
    h: Math.round(rect.height),
  };
};
return {
  active: describe(document.activeElement),
  locationHref: String(window.location.href || ""),
};
"""

DESCRIBE_BUTTON_JS = r"""
const element = arguments[0];
if (!element) return null;
const rect = element.getBoundingClientRect();
return {
  tag: String(element.tagName || "").toLowerCase(),
  id: String(element.id || ""),
  cls: String(element.className || ""),
  role: String(element.getAttribute?.("role") || ""),
  ariaLabel: String(element.getAttribute?.("aria-label") || ""),
  text: String((element.innerText || element.textContent || "")).replace(/\s+/g, " ").trim().slice(0, 180),
  x: Math.round(rect.x),
  y: Math.round(rect.y),
  w: Math.round(rect.width),
  h: Math.round(rect.height),
};
"""

SHOW_COLLECTION_OVERLAY_JS = r"""
const label = arguments[0] || "Collecting";
const details = arguments[1] || "";
const id = "__grad_notegpt_collect_overlay";
let root = document.getElementById(id);
if (!root) {
  root = document.createElement("div");
  root.id = id;
  root.style.position = "fixed";
  root.style.top = "16px";
  root.style.left = "16px";
  root.style.zIndex = "2147483647";
  root.style.background = "rgba(15, 23, 42, 0.92)";
  root.style.color = "#f8fafc";
  root.style.padding = "10px 14px";
  root.style.borderRadius = "12px";
  root.style.boxShadow = "0 8px 24px rgba(0,0,0,0.25)";
  root.style.fontFamily = "Arial, sans-serif";
  root.style.fontSize = "14px";
  root.style.lineHeight = "1.4";
  root.style.maxWidth = "440px";
  root.style.pointerEvents = "none";
  document.documentElement.appendChild(root);
}
root.innerHTML = `<div style="font-weight:700;">${label}</div><div style="margin-top:4px;">${details}</div>`;
try { window.focus(); } catch (error) {}
return true;
"""

GUARD_COLLECTION_SURFACE_JS = r"""
const styleId = "__grad_notegpt_click_guard_style";
if (!document.getElementById(styleId)) {
  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = `
    #secondary a,
    #secondary [role="link"],
    #secondary ytd-compact-video-renderer,
    #secondary ytd-rich-item-renderer,
    #related a,
    .ytp-ce-element,
    .ytp-endscreen-content,
    .ytp-pause-overlay {
      pointer-events: none !important;
    }

    .ng-yt-extension-container,
    .ng-yt-extension-container *,
    [class*="ystn"],
    [class*="ystn"] *,
    [class*="notegpt"],
    [class*="notegpt"] *,
    [id*="notegpt"],
    [id*="notegpt"] * {
      pointer-events: auto !important;
    }
  `;
  document.documentElement.appendChild(style);
}

if (!window.__gradNotegptClickGuardInstalled) {
  const allowSelector = ".ng-yt-extension-container, [class*='ystn'], [class*='notegpt'], [id*='notegpt']";
  document.addEventListener(
    "click",
    (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest(allowSelector)) return;
      const anchor = target.closest("a");
      if (!anchor) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    },
    true
  );
  window.__gradNotegptClickGuardInstalled = true;
}

return true;
"""


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Try a real Selenium click on NoteGPT's transcript button for one YouTube video."
    )
    parser.add_argument("--url", required=True, help="YouTube watch URL to test.")
    parser.add_argument(
        "--debugger-address",
        default="127.0.0.1:9222",
        help="Chrome remote debugging address. Default: 127.0.0.1:9222",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw/notegpt_exports",
        help="Directory to write *_transcript.json outputs.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Maximum wait time for transcript generation. Default: 30",
    )
    return parser.parse_args()


def resolve_chromedriver_path() -> Path | None:
    candidates: list[Path] = []
    env_value = os.environ.get("CHROMEDRIVER_PATH", "").strip()
    if env_value:
        candidates.append(Path(env_value))

    user_profile = os.environ.get("USERPROFILE", "").strip()
    if user_profile:
        cache_root = Path(user_profile) / ".cache" / "selenium" / "chromedriver" / "win64"
        if cache_root.exists():
            version_dirs = sorted(
                [path for path in cache_root.iterdir() if path.is_dir()],
                key=lambda path: path.name,
                reverse=True,
            )
            for version_dir in version_dirs:
                candidates.append(version_dir / "chromedriver.exe")

    candidates.append(Path.cwd() / "tools" / "chromedriver.exe")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def connect_driver(debugger_address: str) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.debugger_address = debugger_address
    chromedriver_path = resolve_chromedriver_path()
    try:
        if chromedriver_path is not None:
            LOGGER.info("Using chromedriver at %s", chromedriver_path)
            service = ChromeService(executable_path=str(chromedriver_path))
            driver = webdriver.Chrome(service=service, options=options)
        else:
            LOGGER.warning("No local chromedriver.exe found. Falling back to Selenium Manager.")
            driver = webdriver.Chrome(options=options)
    except WebDriverException as exc:
        raise RuntimeError(
            "Could not attach to Chrome. Close all Chrome windows, run scripts\\23_launch_chrome_debug.ps1, "
            "then try again."
        ) from exc
    driver.set_page_load_timeout(60)
    driver.set_script_timeout(60)
    setattr(driver, "_grad_collection_handle", "")
    ensure_collection_tab(driver)
    return driver


def wait_for_page_ready(driver: webdriver.Chrome, timeout_seconds: int) -> None:
    WebDriverWait(driver, timeout_seconds).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    WebDriverWait(driver, timeout_seconds).until(
        EC.presence_of_element_located((By.TAG_NAME, "ytd-watch-flexy"))
    )


def wait_for_watch_ready_after_navigation(
    driver: webdriver.Chrome,
    timeout_seconds: int,
    expected_video_id: str,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_log_at = 0.0

    while time.monotonic() < deadline:
        try:
            current_url = str(driver.current_url or "")
        except Exception:
            current_url = ""

        try:
            ready_state = str(driver.execute_script("return document.readyState") or "")
        except Exception:
            ready_state = ""

        try:
            has_watch = bool(driver.execute_script("return !!document.querySelector('ytd-watch-flexy')"))
        except Exception:
            has_watch = False

        if expected_video_id:
            try:
                assert_expected_video_id(driver, expected_video_id)
            except RuntimeError:
                raise
            except Exception:
                pass

        if ready_state == "complete" and has_watch:
            return

        now = time.monotonic()
        if now - last_log_at >= 10:
            LOGGER.info(
                "Still waiting for watch page... current_url=%s ready_state=%s has_watch=%s",
                current_url,
                ready_state,
                has_watch,
            )
            last_log_at = now
        time.sleep(0.5)

    try:
        driver.execute_script("window.stop();")
    except Exception:
        pass
    raise RuntimeError(
        f"Timed out waiting for YouTube watch page to become ready. current_url={getattr(driver, 'current_url', '')}"
    )


def stabilize_watch_page(driver: webdriver.Chrome) -> None:
    try:
        driver.execute_script(PAUSE_VIDEO_JS)
    except Exception:
        pass


def show_collection_overlay(driver: webdriver.Chrome, label: str, details: str) -> None:
    try:
        driver.execute_script(SHOW_COLLECTION_OVERLAY_JS, label, details)
    except Exception:
        pass
    try:
        driver.execute_script(GUARD_COLLECTION_SURFACE_JS)
    except Exception:
        pass
    try:
        driver.execute_script(DISABLE_AUTOPLAY_JS)
    except Exception:
        pass


def mark_current_tab_as_collection(driver: webdriver.Chrome) -> None:
    try:
        driver.execute_script(MARK_COLLECTION_TAB_JS, COLLECTION_TAB_MARKER)
    except Exception:
        pass


def _is_closed_window_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "target window already closed" in text or "web view not found" in text or "no such window" in text


def get_live_window_handles(driver: webdriver.Chrome) -> list[str]:
    try:
        return list(driver.window_handles)
    except (NoSuchWindowException, WebDriverException) as exc:
        if _is_closed_window_error(exc):
            return []
        raise


def ensure_live_window_context(driver: webdriver.Chrome) -> list[str]:
    handles = get_live_window_handles(driver)
    if not handles:
        return []

    try:
        current_handle = str(driver.current_window_handle or "")
    except (NoSuchWindowException, WebDriverException):
        current_handle = ""

    if current_handle in handles:
        return handles

    for handle in handles:
        try:
            driver.switch_to.window(handle)
            return get_live_window_handles(driver)
        except (NoSuchWindowException, WebDriverException) as exc:
            if _is_closed_window_error(exc):
                continue
            raise
    return get_live_window_handles(driver)


def find_existing_collection_tab_handles(driver: webdriver.Chrome) -> list[str]:
    handles = ensure_live_window_context(driver)
    named_matches: list[tuple[str, str]] = []
    storage_only_matches: list[tuple[str, str]] = []
    for handle in handles:
        try:
            driver.switch_to.window(handle)
            current_url = str(driver.current_url or "")
            marker_info = driver.execute_script(GET_COLLECTION_TAB_MARKER_JS, COLLECTION_TAB_MARKER) or {}
            window_name = str(getattr(marker_info, "get", lambda *_: "")("windowName") or "")
            storage_value = str(getattr(marker_info, "get", lambda *_: "")("storageValue") or "")
            if window_name != COLLECTION_TAB_MARKER and storage_value != COLLECTION_TAB_MARKER and (
                current_url.startswith("data:")
                or current_url.startswith("http://data")
                or current_url.startswith("https://data")
            ):
                try:
                    driver.close()
                except Exception:
                    pass
                continue
            if window_name == COLLECTION_TAB_MARKER:
                named_matches.append((handle, current_url))
            elif storage_value == COLLECTION_TAB_MARKER:
                storage_only_matches.append((handle, current_url))
        except Exception:
            continue

    if named_matches:
        keeper_handle, keeper_url = named_matches[0]
        for handle, current_url in storage_only_matches:
            try:
                driver.switch_to.window(handle)
                driver.execute_script(
                    "try { window.sessionStorage.removeItem(arguments[0]); } catch (e) {}",
                    COLLECTION_TAB_MARKER,
                )
                if current_url == keeper_url:
                    driver.close()
            except Exception:
                continue
        return [handle for handle, _ in named_matches]

    if len(storage_only_matches) == 1:
        handle, _ = storage_only_matches[0]
        try:
            driver.switch_to.window(handle)
            mark_current_tab_as_collection(driver)
        except Exception:
            pass
        return [handle]

    if len(storage_only_matches) > 1:
        keeper_handle, keeper_url = storage_only_matches[0]
        try:
            driver.switch_to.window(keeper_handle)
            mark_current_tab_as_collection(driver)
        except Exception:
            pass
        for handle, current_url in storage_only_matches[1:]:
            try:
                driver.switch_to.window(handle)
                driver.execute_script(
                    "try { window.sessionStorage.removeItem(arguments[0]); } catch (e) {}",
                    COLLECTION_TAB_MARKER,
                )
                if current_url == keeper_url:
                    driver.close()
            except Exception:
                continue
        return [keeper_handle]

    return []


def ensure_collection_tab(driver: webdriver.Chrome) -> None:
    handles = ensure_live_window_context(driver)
    known_handle = str(getattr(driver, "_grad_collection_handle", "") or "")
    if known_handle and known_handle in handles:
        try:
            driver.switch_to.window(known_handle)
        except (NoSuchWindowException, WebDriverException):
            setattr(driver, "_grad_collection_handle", "")
        else:
            return

    existing_handles = find_existing_collection_tab_handles(driver)
    if existing_handles:
        keeper = existing_handles[0]
        for duplicate in existing_handles[1:]:
            try:
                driver.switch_to.window(duplicate)
                driver.close()
            except Exception:
                pass
        driver.switch_to.window(keeper)
        setattr(driver, "_grad_collection_handle", keeper)
        return

    handles = ensure_live_window_context(driver)
    if not handles:
        raise RuntimeError(
            "Chrome is attached, but there are no live tabs to recover. Reopen the debug Chrome window and try again."
        )

    driver.switch_to.new_window("tab")
    driver.get("about:blank")
    handle = driver.current_window_handle
    setattr(driver, "_grad_collection_handle", handle)


def open_video_page(
    driver: webdriver.Chrome,
    url: str,
    timeout_seconds: int,
    expected_video_id: str,
    navigation_attempts: int = 3,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, navigation_attempts + 1):
        LOGGER.info("Navigating to %s (attempt %s/%s)", url, attempt, navigation_attempts)
        try:
            LOGGER.info("Ensuring the dedicated collection tab is active before navigation...")
            ensure_collection_tab(driver)
            LOGGER.info("Collection tab ready. handle=%s open_tabs=%s", driver.current_window_handle, len(driver.window_handles))
        except Exception:
            pass
        try:
            LOGGER.info("Navigating with driver.get(...) in the collection tab...")
            driver.get(url)
            LOGGER.info("driver.get(...) navigation dispatched.")
        except Exception:
            LOGGER.info("driver.get(...) failed. Falling back to JS location.replace navigation...")
            driver.get("about:blank")
            driver.execute_script("window.location.replace(arguments[0]);", url)
            LOGGER.info("JS navigation dispatched.")
        wait_for_watch_ready_after_navigation(driver, timeout_seconds, expected_video_id)
        mark_current_tab_as_collection(driver)
        stabilize_watch_page(driver)
        try:
            assert_expected_video_id(driver, expected_video_id)
            return
        except RuntimeError as exc:
            last_error = exc
            LOGGER.warning("Loaded the wrong video after navigation attempt %s: %s", attempt, exc)
    if last_error is not None:
        raise last_error


def get_video_id_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get("v", [""])[0].strip()
    except Exception:
        return ""


def get_current_video_id(driver: webdriver.Chrome) -> str:
    return get_video_id_from_url(str(driver.current_url))


def assert_expected_video_id(driver: webdriver.Chrome, expected_video_id: str) -> None:
    current_video_id = get_current_video_id(driver)
    if expected_video_id and current_video_id != expected_video_id:
        raise RuntimeError(
            f"Video mismatch detected. expected_video_id={expected_video_id} current_video_id={current_video_id} "
            f"current_url={driver.current_url}"
        )


def assert_same_video_or_raise(driver: webdriver.Chrome, expected_video_id: str) -> None:
    if expected_video_id:
        assert_expected_video_id(driver, expected_video_id)


def wait_for_transcript_button(
    driver: webdriver.Chrome, timeout_seconds: int
) -> Any:
    return WebDriverWait(driver, timeout_seconds).until(
        lambda d: d.execute_script(FIND_TRANSCRIPT_BUTTON_JS)
    )


def wait_for_state_change(
    driver: webdriver.Chrome,
    timeout_seconds: int,
    expected_video_id: str = "",
) -> bool:
    try:
        WebDriverWait(driver, timeout_seconds).until(
            lambda d: (
                assert_same_video_or_raise(d, expected_video_id) or True
            )
            and (
                d.execute_script(FIND_LOADING_PANEL_JS) is not None
                or d.execute_script(EXTRACT_TRANSCRIPT_JS) is not None
            )
        )
        return True
    except TimeoutException:
        return False


def log_click_context(driver: webdriver.Chrome, button: Any, label: str) -> None:
    try:
        button_info = driver.execute_script(DESCRIBE_BUTTON_JS, button)
    except Exception as exc:
        button_info = {"error": f"button_describe_failed: {exc}"}
    try:
        active_info = driver.execute_script(DESCRIBE_ACTIVE_ELEMENT_JS)
    except Exception as exc:
        active_info = {"error": f"active_describe_failed: {exc}"}
    LOGGER.info("%s button=%s active=%s", label, button_info, active_info)


def click_transcript_button(
    driver: webdriver.Chrome,
    timeout_seconds: int,
    expected_video_id: str = "",
) -> None:
    LOGGER.info("Waiting for NoteGPT transcript button...")
    button = wait_for_transcript_button(driver, timeout_seconds)
    if button is None:
        raise RuntimeError("Could not find a NoteGPT transcript button.")

    LOGGER.info("Clicking transcript button with Selenium user gesture...")
    click_attempt_errors: list[str] = []
    click_attempts = [
        ("webdriver-click", "Clicking transcript button with WebDriver click..."),
        ("js-click", "Transcript generation did not start. Retrying once with JS click..."),
    ]

    for attempt_name, attempt_log in click_attempts:
        LOGGER.info(attempt_log)
        try:
            fresh_button = wait_for_transcript_button(driver, 10)
            log_click_context(driver, fresh_button, f"Before {attempt_name}")
            if attempt_name == "webdriver-click":
                fresh_button.click()
            else:
                driver.execute_script("arguments[0].click();", fresh_button)
            assert_same_video_or_raise(driver, expected_video_id)
            log_click_context(driver, fresh_button, f"After {attempt_name}")
        except WebDriverException as exc:
            click_attempt_errors.append(f"{attempt_name}: {exc}")
            continue

        if wait_for_state_change(driver, 4, expected_video_id):
            return

    debug_candidates = driver.execute_script(DEBUG_CANDIDATES_JS)
    raise RuntimeError(
        "Clicked transcript button repeatedly, but NoteGPT never entered loading/transcript state. "
        f"Click errors={click_attempt_errors} candidates={debug_candidates}"
    )


def wait_for_loading_or_transcript(
    driver: webdriver.Chrome,
    timeout_seconds: int,
    expected_video_id: str = "",
) -> None:
    LOGGER.info("Waiting for NoteGPT to enter loading or transcript state...")

    def condition(d: webdriver.Chrome) -> bool:
        assert_same_video_or_raise(d, expected_video_id)
        terminal_failure = d.execute_script(FIND_TERMINAL_FAILURE_JS)
        if terminal_failure is not None:
            raise RuntimeError(str(terminal_failure.get("message") or "NoteGPT reported a terminal failure."))
        loading_panel = d.execute_script(FIND_LOADING_PANEL_JS)
        if loading_panel is not None:
            return True
        transcript_payload = d.execute_script(EXTRACT_TRANSCRIPT_JS)
        return transcript_payload is not None

    try:
        WebDriverWait(driver, timeout_seconds).until(condition)
    except TimeoutException as exc:
        debug_candidates = driver.execute_script(DEBUG_CANDIDATES_JS)
        LOGGER.warning("NoteGPT never entered loading/transcript state. Top candidates: %s", debug_candidates)
        raise RuntimeError("Timed out waiting for NoteGPT to start transcript generation.") from exc


def wait_for_transcript_payload(
    driver: webdriver.Chrome,
    timeout_seconds: int,
    expected_video_id: str = "",
) -> dict[str, Any]:
    LOGGER.info("Waiting for transcript panel...")
    def condition(d: webdriver.Chrome) -> Any:
        assert_same_video_or_raise(d, expected_video_id)
        terminal_failure = d.execute_script(FIND_TERMINAL_FAILURE_JS)
        if terminal_failure is not None:
            raise RuntimeError(str(terminal_failure.get("message") or "NoteGPT reported a terminal failure."))
        return d.execute_script(EXTRACT_TRANSCRIPT_JS)

    try:
        payload = WebDriverWait(driver, timeout_seconds).until(condition)
    except TimeoutException as exc:
        debug_candidates = driver.execute_script(DEBUG_CANDIDATES_JS)
        LOGGER.warning("Transcript panel timeout. Top candidates: %s", debug_candidates)
        raise RuntimeError("Timed out waiting for a transcript-like panel.") from exc

    if not payload:
        raise RuntimeError("Transcript extraction returned no payload.")
    return payload


def save_payload(payload: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    video_id = str(payload.get("video_id") or "unknown")
    output_path = output_dir / f"{video_id}_transcript.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def is_retryable_error(exc: Exception) -> bool:
    message = str(exc)
    if any(snippet in message for snippet in NON_RETRYABLE_ERROR_SNIPPETS):
        return False
    return any(snippet in message for snippet in RETRYABLE_ERROR_SNIPPETS)


def main() -> int:
    configure_logging()
    args = parse_args()

    output_dir = Path(args.output_dir)
    LOGGER.info("Attaching to Chrome at %s", args.debugger_address)
    driver = connect_driver(args.debugger_address)
    expected_video_id = get_video_id_from_url(args.url)

    try:
        open_video_page(driver, args.url, args.timeout_seconds, expected_video_id)
        LOGGER.info("Giving NoteGPT a moment to finish mounting...")
        wait_for_transcript_button(driver, 8)
        click_transcript_button(driver, args.timeout_seconds, expected_video_id)
        wait_for_loading_or_transcript(driver, 20, expected_video_id)
        payload = wait_for_transcript_payload(driver, args.timeout_seconds, expected_video_id)
        payload_video_id = str(payload.get("video_id") or "").strip()
        if expected_video_id and payload_video_id != expected_video_id:
            raise RuntimeError(
                f"Payload video mismatch detected. expected_video_id={expected_video_id} "
                f"payload_video_id={payload_video_id} current_url={driver.current_url}"
            )
        output_path = save_payload(payload, output_dir)
        LOGGER.info(
            "Saved transcript for video=%s title=%s to %s",
            payload.get("video_id"),
            payload.get("title"),
            output_path,
        )
        return 0
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
