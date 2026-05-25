import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

import { chromium, type Browser, type BrowserContext, type Page } from "playwright";

type BrowserSessionStatus = "starting" | "active" | "failed" | "completed";

type BrowserSessionRecord = {
  id: string;
  context: BrowserContext;
  page: Page;
  provider: "playwright";
  status: BrowserSessionStatus;
  reasonBrowserNeeded: string;
  targetSite: string;
  allowedDomains: string[];
  intendedActions: string[];
  forbiddenActions: string[];
  approvalRequiredBeforeSubmit: boolean;
  currentUrl: string;
  title: string;
  lastScreenshotDataUrl?: string;
  lastScreenshotRef?: string;
  lastScreenshotAt?: string;
  lastPageText?: string;
  errorMessage?: string;
  startedAt: string;
};

type PublicBrowserSession = Omit<BrowserSessionRecord, "context" | "page">;

const DATA_DIR =
  process.env.YIELDAGENT_WEB_DATA_DIR ?? path.join(process.cwd(), ".yieldagent");
const SCREENSHOT_DIR = path.join(DATA_DIR, "browser-sessions");

const ALLOWED_DOMAINS = [
  "linkedin.com",
  "www.linkedin.com",
  "business.linkedin.com",
  "ads.linkedin.com",
  "facebook.com",
  "www.facebook.com",
  "business.facebook.com",
  "adsmanager.facebook.com",
  "google.com",
  "accounts.google.com",
  "ads.google.com"
];

const DEFAULT_BROWSER_URL = "https://www.linkedin.com/campaignmanager";

type BrowserRuntime = {
  browser?: Browser;
  sessions: Map<string, BrowserSessionRecord>;
};

const globalForBrowser = globalThis as typeof globalThis & {
  __yieldAgentBrowserRuntime?: BrowserRuntime;
};

const runtime = () => {
  globalForBrowser.__yieldAgentBrowserRuntime ??= {
    sessions: new Map<string, BrowserSessionRecord>()
  };
  return globalForBrowser.__yieldAgentBrowserRuntime;
};

export const defaultBrowserUrl = () => DEFAULT_BROWSER_URL;

export const getActiveBrowserSession = () => {
  const sessions = [...runtime().sessions.values()].filter(
    (session) => session.status === "active" || session.status === "failed"
  );
  return sessions.at(-1) ? toPublicSession(sessions.at(-1)!) : null;
};

export const openBrowserSession = async ({
  url = DEFAULT_BROWSER_URL,
  reasonBrowserNeeded = "The requested campaign data or workflow is not available through an official API."
}: {
  url?: string;
  reasonBrowserNeeded?: string;
}) => {
  assertAllowedUrl(url);

  const id = randomUUID();
  const startedAt = new Date().toISOString();
  const browser = await getBrowser();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });
  const page = await context.newPage();
  const record: BrowserSessionRecord = {
    id,
    context,
    page,
    provider: "playwright",
    status: "starting",
    reasonBrowserNeeded,
    targetSite: targetSiteForUrl(url),
    allowedDomains: ALLOWED_DOMAINS,
    intendedActions: ["navigate", "inspect page state", "take screenshots", "extract visible page text"],
    forbiddenActions: ["publish", "increase budget", "change billing", "submit spend-affecting forms"],
    approvalRequiredBeforeSubmit: true,
    currentUrl: url,
    title: "Starting browser session",
    startedAt
  };
  runtime().sessions.set(id, record);

  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20_000 });
    record.status = "active";
    await captureSession(record);
  } catch (error) {
    record.status = "failed";
    record.errorMessage = error instanceof Error ? error.message : "Browser session failed";
    await captureSession(record).catch(() => undefined);
  }

  return toPublicSession(record);
};

export const navigateBrowserSession = async (sessionId: string, url: string) => {
  assertAllowedUrl(url);
  const record = getSessionOrThrow(sessionId);
  record.status = "active";
  record.currentUrl = url;
  record.targetSite = targetSiteForUrl(url);

  try {
    await record.page.goto(url, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await captureSession(record);
  } catch (error) {
    record.status = "failed";
    record.errorMessage = error instanceof Error ? error.message : "Navigation failed";
    await captureSession(record).catch(() => undefined);
  }

  return toPublicSession(record);
};

export const refreshBrowserSession = async (sessionId: string) => {
  const record = getSessionOrThrow(sessionId);
  await captureSession(record);
  return toPublicSession(record);
};

export const closeBrowserSession = async (sessionId: string) => {
  const record = getSessionOrThrow(sessionId);
  record.status = "completed";
  runtime().sessions.delete(sessionId);
  await record.context.close();
  return toPublicSession(record);
};

const getBrowser = async () => {
  const current = runtime();
  if (current.browser?.isConnected()) {
    return current.browser;
  }

  current.browser = await chromium.launch({
    headless: true
  });
  return current.browser;
};

const captureSession = async (record: BrowserSessionRecord) => {
  const timestamp = new Date().toISOString();
  const bytes = await record.page.screenshot({ type: "png", fullPage: false });
  const folder = path.join(SCREENSHOT_DIR, record.id);
  const filename = `${Date.now()}.png`;
  const screenshotRef = path.join(folder, filename);
  await fs.mkdir(folder, { recursive: true });
  await fs.writeFile(screenshotRef, bytes);

  record.currentUrl = record.page.url();
  record.title = (await record.page.title()) || record.currentUrl;
  record.lastScreenshotDataUrl = `data:image/png;base64,${bytes.toString("base64")}`;
  record.lastScreenshotRef = screenshotRef;
  record.lastScreenshotAt = timestamp;
  record.lastPageText = await extractVisibleText(record.page);
};

const extractVisibleText = async (page: Page) => {
  try {
    const text = await page.locator("body").innerText({ timeout: 2_000 });
    return text.replace(/\s+/g, " ").trim().slice(0, 1400);
  } catch {
    return "";
  }
};

const getSessionOrThrow = (sessionId: string) => {
  const record = runtime().sessions.get(sessionId);
  if (!record) {
    throw new Error("Browser session not found");
  }
  return record;
};

const assertAllowedUrl = (url: string) => {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("Enter a valid URL.");
  }

  if (!["https:", "http:"].includes(parsed.protocol)) {
    throw new Error("Only HTTP and HTTPS URLs are allowed.");
  }

  const host = parsed.hostname.toLowerCase();
  const allowed = ALLOWED_DOMAINS.some((domain) => host === domain || host.endsWith(`.${domain}`));
  if (!allowed) {
    throw new Error(`Browser fallback is allowlisted to ad-platform domains. ${host} is not allowed.`);
  }
};

const targetSiteForUrl = (url: string) => {
  const host = new URL(url).hostname;
  if (host.includes("linkedin")) {
    return "linkedin_ads";
  }
  if (host.includes("facebook")) {
    return "meta_ads";
  }
  if (host.includes("google")) {
    return "google_ads";
  }
  return "ad_platform";
};

const toPublicSession = (record: BrowserSessionRecord): PublicBrowserSession => ({
  id: record.id,
  provider: record.provider,
  status: record.status,
  reasonBrowserNeeded: record.reasonBrowserNeeded,
  targetSite: record.targetSite,
  allowedDomains: record.allowedDomains,
  intendedActions: record.intendedActions,
  forbiddenActions: record.forbiddenActions,
  approvalRequiredBeforeSubmit: record.approvalRequiredBeforeSubmit,
  currentUrl: record.currentUrl,
  title: record.title,
  lastScreenshotDataUrl: record.lastScreenshotDataUrl,
  lastScreenshotRef: record.lastScreenshotRef,
  lastScreenshotAt: record.lastScreenshotAt,
  lastPageText: record.lastPageText,
  errorMessage: record.errorMessage,
  startedAt: record.startedAt
});
