import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const [port = "9225", baseUrl = "http://127.0.0.1:5127/", outputDir = "."] = process.argv.slice(2);
const devtoolsUrl = `http://127.0.0.1:${port}`;

mkdirSync(outputDir, { recursive: true });

const targetResponse = await fetch(
  `${devtoolsUrl}/json/new?${encodeURIComponent("about:blank")}`,
  { method: "PUT" },
);
if (!targetResponse.ok) {
  throw new Error(`Unable to create DevTools target: HTTP ${targetResponse.status}`);
}
const target = await targetResponse.json();
const socket = new WebSocket(target.webSocketDebuggerUrl);

await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let nextId = 1;
const pending = new Map();

socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) {
    return;
  }
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) {
    reject(new Error(`${message.error.message} (${message.error.code})`));
    return;
  }
  resolve(message.result ?? {});
});

function send(method, params = {}) {
  const id = nextId++;
  const response = new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
  });
  socket.send(JSON.stringify({ id, method, params }));
  return response;
}

async function evaluate(expression) {
  const response = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text || "Runtime evaluation failed");
  }
  return response.result?.value;
}

async function waitForReady() {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if ((await evaluate("document.readyState")) === "complete") {
      await new Promise((resolve) => setTimeout(resolve, 650));
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("Page did not reach document.readyState=complete");
}

async function setViewport(width, height) {
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width <= 500,
    screenWidth: width,
    screenHeight: height,
    positionX: 0,
    positionY: 0,
    screenOrientation: { type: "portraitPrimary", angle: 0 },
  });
  await send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: "no-preference" }],
  });
}

async function navigate(path) {
  const url = new URL(path, baseUrl).href;
  await send("Page.navigate", { url });
  await waitForReady();
  await evaluate("window.scrollTo(0, 0)");
  return url;
}

async function submit(selector) {
  const result = await evaluate(`(async () => {
    const form = document.querySelector(${JSON.stringify(selector)});
    if (!form) return { error: "missing form" };
    const response = await fetch(form.action, {
      method: (form.method || "POST").toUpperCase(),
      body: new FormData(form),
      credentials: "include",
    });
    return { status: response.status, url: response.url };
  })()`);
  if (!result || result.error || result.status >= 400) {
    throw new Error(`Form submission failed for ${selector}: ${JSON.stringify(result)}`);
  }
  return result;
}

async function focusPrimaryWithKeyboard() {
  await evaluate("document.activeElement?.blur()");
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await send("Input.dispatchKeyEvent", {
      type: "rawKeyDown",
      key: "Tab",
      code: "Tab",
      windowsVirtualKeyCode: 9,
      nativeVirtualKeyCode: 9,
    });
    await send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key: "Tab",
      code: "Tab",
      windowsVirtualKeyCode: 9,
      nativeVirtualKeyCode: 9,
    });
    if (await evaluate('document.activeElement?.matches("[data-primary-action]")')) {
      return true;
    }
  }
  return false;
}

async function layoutEvidence() {
  return evaluate(`(() => {
    const root = document.documentElement;
    const dockRect = document.querySelector(".mobile-dock")?.getBoundingClientRect();
    const primaryActions = [...document.querySelectorAll("[data-primary-action]")].map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        text: element.textContent.trim().replace(/\\s+/g, " "),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        top: Math.round(rect.top),
        bottom: Math.round(rect.bottom),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        horizontallyClipped: rect.left < 0 || rect.right > window.innerWidth,
        coveredByDock: Boolean(dockRect && rect.bottom > dockRect.top && rect.top < dockRect.bottom),
      };
    });
    const focusTarget = document.activeElement?.matches("[data-primary-action]")
      ? document.activeElement
      : null;
    const focusStyle = focusTarget ? getComputedStyle(focusTarget) : null;
    return {
      url: location.href,
      title: document.title,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      scrollY: Math.round(window.scrollY),
      clientWidth: root.clientWidth,
      scrollWidth: root.scrollWidth,
      horizontalOverflow: Math.max(0, root.scrollWidth - root.clientWidth),
      brokenImages: [...document.images].filter((image) => image.complete && image.naturalWidth === 0).length,
      pendingImages: [...document.images].filter((image) => !image.complete).length,
      primaryActions,
      focus: focusStyle ? {
        outlineStyle: focusStyle.outlineStyle,
        outlineWidth: focusStyle.outlineWidth,
        outlineOffset: focusStyle.outlineOffset,
      } : null,
      mobileDock: Boolean(document.querySelector(".mobile-dock")),
    };
  })()`);
}

const evidence = [];

function persistEvidence() {
  writeFileSync(
    join(outputDir, "runtime-layout-metrics.json"),
    `${JSON.stringify({ capturedAt: new Date().toISOString(), baseUrl, evidence }, null, 2)}\n`,
    "utf8",
  );
}

async function capture(name, width, height, path) {
  await setViewport(width, height);
  await navigate(path);
  const screenshot = await send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  writeFileSync(join(outputDir, name), Buffer.from(screenshot.data, "base64"));
  await focusPrimaryWithKeyboard();
  const layout = await layoutEvidence();
  evidence.push({ name, viewport: { width, height }, ...layout });
  persistEvidence();
  return layout;
}

await send("Page.enable");
await send("Runtime.enable");
await send("Network.enable");

await capture("home-desktop-1100x900.png", 1100, 900, "/");
await capture("home-mobile-390x844.png", 390, 844, "/");
const login = await submit("form[data-judge-entry]");
if (!login.url.endsWith("/profile")) {
  throw new Error(`Demo login did not resolve to /profile: ${login.url}`);
}

await capture("profile-mobile-390x844.png", 390, 844, "/profile");
await capture("match-ready-mobile-390x844.png", 390, 844, "/matches");
await submit("form.match-start-form");
await capture("match-searching-mobile-390x844.png", 390, 844, "/matches/searching");
const completed = await submit("form[data-match-complete]");
const resultPath = new URL(completed.url).pathname;
await capture("match-result-mobile-390x844.png", 390, 844, resultPath);
const conversation = await submit(".match-result-actions form:first-of-type");
const conversationPath = new URL(conversation.url).pathname;
await capture("chat-l0-mobile-390x844.png", 390, 844, conversationPath);
await submit("form.demo-progress-tool");
await capture("chat-progress-desktop-1100x900.png", 1100, 900, conversationPath);
await capture("events-mobile-390x844.png", 390, 844, "/events");
const eventPath = await evaluate(`document.querySelector(".event-row .button")?.getAttribute("href")`);
if (!eventPath) {
  throw new Error("No event detail link was available for screenshot evidence");
}
await capture("event-detail-desktop-1100x900.png", 1100, 900, eventPath);

persistEvidence();

socket.close();
console.log(JSON.stringify({ screenshots: evidence.length, outputDir }, null, 2));
