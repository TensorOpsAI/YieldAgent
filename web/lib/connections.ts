import crypto from "node:crypto";
import fs from "node:fs/promises";
import fsSync from "node:fs";
import path from "node:path";

export type ProviderKey = "linkedin" | "meta" | "google";

export type StoredAdAccount = {
  id: string;
  name: string;
  role?: string;
  status?: string;
  currency?: string;
  test?: boolean;
};

export type StoredConnection = {
  platform: ProviderKey;
  connectedAt: string;
  lastValidatedAt: string;
  expiresAt?: string;
  scopes: string[];
  encryptedCredential: string;
  accounts: StoredAdAccount[];
  selectedAccountId?: string;
};

export type ProviderFieldKey =
  | "clientId"
  | "clientSecret"
  | "developerToken"
  | "loginCustomerId";

export type ProviderConfig = Partial<Record<ProviderFieldKey, string>>;

export type ProviderField = {
  key: ProviderFieldKey;
  label: string;
  type: "text" | "password";
  required: boolean;
  placeholder?: string;
  helperText?: string;
};

export type ProviderSchema = {
  fields: ProviderField[];
  redirectUri: string;
  docsUrl: string;
  consoleUrl: string;
};

export const providerFieldSchema = (): Record<ProviderKey, ProviderSchema> => ({
  linkedin: {
    fields: [
      { key: "clientId", label: "Client ID", type: "text", required: true },
      { key: "clientSecret", label: "Client Secret", type: "password", required: true }
    ],
    redirectUri: linkedinRedirectUri(),
    docsUrl: "https://learn.microsoft.com/en-us/linkedin/marketing/quick-start",
    consoleUrl: "https://www.linkedin.com/developers/apps"
  },
  meta: {
    fields: [
      { key: "clientId", label: "App ID", type: "text", required: true },
      { key: "clientSecret", label: "App Secret", type: "password", required: true }
    ],
    redirectUri: `${appBaseUrl()}/api/oauth/meta/callback`,
    docsUrl: "https://developers.facebook.com/docs/marketing-api/get-started/authentication",
    consoleUrl: "https://developers.facebook.com/apps/"
  },
  google: {
    fields: [
      { key: "clientId", label: "OAuth Client ID", type: "text", required: true },
      { key: "clientSecret", label: "OAuth Client Secret", type: "password", required: true },
      {
        key: "developerToken",
        label: "Developer Token",
        type: "password",
        required: true,
        helperText: "22-character token from your Google Ads API Center."
      },
      {
        key: "loginCustomerId",
        label: "Manager (MCC) Customer ID",
        type: "text",
        required: false,
        placeholder: "10-digit ID without dashes",
        helperText: "Required only if you access accounts through a manager (MCC)."
      }
    ],
    redirectUri: `${appBaseUrl()}/api/oauth/google/callback`,
    docsUrl: "https://developers.google.com/google-ads/api/docs/get-started/introduction",
    consoleUrl: "https://console.cloud.google.com/apis/credentials"
  }
});

type ConnectionFile = {
  connections: Partial<Record<ProviderKey, StoredConnection>>;
  providerConfigs?: Partial<Record<ProviderKey, string>>;
};

type LinkedInTokenResponse = {
  access_token: string;
  expires_in?: number;
  refresh_token?: string;
  refresh_token_expires_in?: number;
  scope?: string;
};

type LinkedInAdAccountUser = {
  account?: string;
  role?: string;
};

const DATA_DIR =
  process.env.YIELDAGENT_WEB_DATA_DIR ?? path.join(process.cwd(), ".yieldagent");
const STORE_FILE = path.join(DATA_DIR, "connections.json");
const SECRET_FILE = path.join(DATA_DIR, "secret.key");

export const appBaseUrl = () =>
  process.env.NEXT_PUBLIC_APP_URL ??
  process.env.YIELDAGENT_APP_URL ??
  "http://localhost:3000";

export const linkedinRedirectUri = () =>
  process.env.LINKEDIN_REDIRECT_URI ?? `${appBaseUrl()}/api/oauth/linkedin/callback`;

export const linkedinApiVersion = () => process.env.LINKEDIN_API_VERSION ?? "202605";

export const linkedinScopes = () =>
  (process.env.LINKEDIN_OAUTH_SCOPES ?? "r_ads r_ads_reporting")
    .split(/[,\s]+/)
    .map((scope) => scope.trim())
    .filter(Boolean);

const envFallbacks = (): Record<ProviderKey, ProviderConfig> => ({
  linkedin: {
    clientId: process.env.LINKEDIN_CLIENT_ID,
    clientSecret: process.env.LINKEDIN_CLIENT_SECRET
  },
  meta: {
    clientId: process.env.META_APP_ID,
    clientSecret: process.env.META_APP_SECRET
  },
  google: {
    clientId: process.env.GOOGLE_ADS_CLIENT_ID,
    clientSecret: process.env.GOOGLE_ADS_CLIENT_SECRET,
    developerToken: process.env.GOOGLE_ADS_DEVELOPER_TOKEN,
    loginCustomerId: process.env.GOOGLE_ADS_LOGIN_CUSTOMER_ID
  }
});

const connectPaths: Partial<Record<ProviderKey, string>> = {
  linkedin: "/api/oauth/linkedin/start"
};

export const providerSetup = async () => {
  const file = await readConnectionFile();
  const stored = file.providerConfigs ?? {};
  const schema = providerFieldSchema();
  const fallbacks = envFallbacks();

  const buildStatus = (key: ProviderKey) => {
    const merged = mergeConfig(stored[key], fallbacks[key]);
    const definition = schema[key];
    const missing = definition.fields
      .filter((field) => field.required && !merged[field.key])
      .map((field) => field.label);
    return {
      configured: missing.length === 0,
      setupItems: missing,
      fields: definition.fields,
      redirectUri: definition.redirectUri,
      docsUrl: definition.docsUrl,
      consoleUrl: definition.consoleUrl,
      connectPath: connectPaths[key]
    };
  };

  return {
    linkedin: buildStatus("linkedin"),
    meta: buildStatus("meta"),
    google: buildStatus("google")
  };
};

const mergeConfig = (
  encrypted: string | undefined,
  envFallback: ProviderConfig
): ProviderConfig => {
  if (encrypted) {
    try {
      return decryptCredential<ProviderConfig>(encrypted);
    } catch {
      // fall through to env fallback if stored blob is unreadable
    }
  }
  return envFallback;
};

export const providerStatuses = async () => {
  const records = await readConnectionFile();
  const setup = await providerSetup();
  const linkedIn = records.connections.linkedin;
  const meta = records.connections.meta;
  const google = records.connections.google;

  return [
    providerStatus("linkedin", "LinkedIn Ads", linkedIn, setup.linkedin),
    providerStatus("meta", "Meta Ads", meta, setup.meta),
    providerStatus("google", "Google Ads", google, setup.google)
  ];
};

export const getProviderConfig = async (
  platform: ProviderKey
): Promise<ProviderConfig | null> => {
  const file = await readConnectionFile();
  const encrypted = file.providerConfigs?.[platform];
  if (!encrypted) {
    return null;
  }
  try {
    return decryptCredential<ProviderConfig>(encrypted);
  } catch {
    return null;
  }
};

export const saveProviderConfig = async (
  platform: ProviderKey,
  config: ProviderConfig
) => {
  const current = await readConnectionFile();
  current.providerConfigs = {
    ...(current.providerConfigs ?? {}),
    [platform]: encryptCredential(config)
  };
  await fs.mkdir(path.dirname(STORE_FILE), { recursive: true });
  await fs.writeFile(STORE_FILE, `${JSON.stringify(current, null, 2)}\n`);
};

export const deleteProviderConfig = async (platform: ProviderKey) => {
  const current = await readConnectionFile();
  if (!current.providerConfigs || !current.providerConfigs[platform]) {
    return;
  }
  delete current.providerConfigs[platform];
  await fs.writeFile(STORE_FILE, `${JSON.stringify(current, null, 2)}\n`);
};

export const readConnectionFile = async (): Promise<ConnectionFile> => {
  try {
    const raw = await fs.readFile(STORE_FILE, "utf8");
    return JSON.parse(raw) as ConnectionFile;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return { connections: {} };
    }
    throw error;
  }
};

export const saveConnection = async (connection: StoredConnection) => {
  const current = await readConnectionFile();
  current.connections[connection.platform] = connection;
  await fs.mkdir(path.dirname(STORE_FILE), { recursive: true });
  await fs.writeFile(STORE_FILE, `${JSON.stringify(current, null, 2)}\n`);
};

export const getStoredConnection = async (platform: ProviderKey) => {
  const current = await readConnectionFile();
  return current.connections[platform];
};

export const encryptCredential = (credential: unknown) => {
  const key = encryptionKey();
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const plaintext = Buffer.from(JSON.stringify(credential), "utf8");
  const encrypted = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const tag = cipher.getAuthTag();

  return [
    iv.toString("base64url"),
    tag.toString("base64url"),
    encrypted.toString("base64url")
  ].join(".");
};

export const decryptCredential = <T>(encryptedCredential: string): T => {
  const key = encryptionKey();
  const [ivValue, tagValue, encryptedValue] = encryptedCredential.split(".");
  if (!ivValue || !tagValue || !encryptedValue) {
    throw new Error("Stored credential is malformed");
  }

  const decipher = crypto.createDecipheriv(
    "aes-256-gcm",
    key,
    Buffer.from(ivValue, "base64url")
  );
  decipher.setAuthTag(Buffer.from(tagValue, "base64url"));
  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(encryptedValue, "base64url")),
    decipher.final()
  ]);

  return JSON.parse(decrypted.toString("utf8")) as T;
};

export const exchangeLinkedInCode = async (code: string) => {
  const stored = await getProviderConfig("linkedin");
  const clientId = stored?.clientId ?? process.env.LINKEDIN_CLIENT_ID;
  const clientSecret = stored?.clientSecret ?? process.env.LINKEDIN_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    throw new Error("LinkedIn OAuth is not configured");
  }

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: linkedinRedirectUri(),
    client_id: clientId,
    client_secret: clientSecret
  });
  const response = await fetch("https://www.linkedin.com/oauth/v2/accessToken", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body
  });

  if (!response.ok) {
    throw new Error(`LinkedIn token exchange failed with ${response.status}`);
  }

  return (await response.json()) as LinkedInTokenResponse;
};

export const listLinkedInAdAccounts = async (accessToken: string) => {
  const userResponse = await linkedInFetch(accessToken, "/adAccountUsers?q=authenticatedUser");
  const elements: LinkedInAdAccountUser[] = Array.isArray(userResponse.elements)
    ? userResponse.elements
    : [];

  return Promise.all(
    elements.map(async (entry) => {
      const accountUrn = String(entry.account ?? "");
      const id = accountUrn.split(":").at(-1) ?? accountUrn;
      const account: StoredAdAccount = {
        id,
        name: accountUrn,
        role: entry.role
      };

      try {
        const detail = await linkedInFetch(accessToken, `/adAccounts/${id}`);
        account.name = detail.name ?? accountUrn;
        account.status = detail.status;
        account.currency = detail.currency;
        account.test = detail.test;
      } catch {
        account.name = accountUrn;
      }

      return account;
    })
  );
};

const linkedInFetch = async (accessToken: string, pathName: string) => {
  const response = await fetch(`https://api.linkedin.com/rest${pathName}`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "LinkedIn-Version": linkedinApiVersion(),
      "X-Restli-Protocol-Version": "2.0.0"
    }
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`LinkedIn API call failed with ${response.status}: ${body.slice(0, 240)}`);
  }

  return response.json();
};

type ProviderSetupStatus = {
  configured: boolean;
  setupItems: string[];
  fields: ProviderField[];
  redirectUri: string;
  docsUrl: string;
  consoleUrl: string;
  connectPath?: string;
};

const providerStatus = (
  key: ProviderKey,
  platform: string,
  record: StoredConnection | undefined,
  setup: ProviderSetupStatus
) => {
  const expired = record?.expiresAt ? new Date(record.expiresAt).getTime() < Date.now() : false;
  const selected = record?.accounts.find((account) => account.id === record.selectedAccountId);
  const firstAccount = selected ?? record?.accounts[0];

  return {
    key,
    platform,
    status: record ? (expired ? "expired" : "connected") : setup.configured ? "pending" : "disabled",
    account: firstAccount?.name ?? (setup.configured ? "Ready to connect" : "Provider setup required"),
    scopes: record?.scopes ?? [],
    lastValidated: record?.lastValidatedAt ? relativeTime(record.lastValidatedAt) : "Never",
    configured: setup.configured,
    connected: Boolean(record && !expired),
    connectPath: setup.connectPath,
    setupItems: setup.setupItems,
    fields: setup.fields,
    redirectUri: setup.redirectUri,
    docsUrl: setup.docsUrl,
    consoleUrl: setup.consoleUrl,
    accounts: record?.accounts ?? []
  };
};

const encryptionKey = () => {
  const envSecret = process.env.YIELDAGENT_SECRET_KEY;
  if (envSecret && envSecret.length >= 32) {
    return crypto.createHash("sha256").update(envSecret).digest();
  }

  try {
    const existing = fsSync.readFileSync(SECRET_FILE, "utf8").trim();
    if (existing.length >= 32) {
      return crypto.createHash("sha256").update(existing).digest();
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      throw error;
    }
  }

  const fresh = crypto.randomBytes(32).toString("base64url");
  fsSync.mkdirSync(DATA_DIR, { recursive: true });
  fsSync.writeFileSync(SECRET_FILE, fresh, { mode: 0o600 });
  return crypto.createHash("sha256").update(fresh).digest();
};

const relativeTime = (isoValue: string) => {
  const delta = Date.now() - new Date(isoValue).getTime();
  if (Number.isNaN(delta)) {
    return "Unknown";
  }
  if (delta < 60_000) {
    return "Just now";
  }
  if (delta < 3_600_000) {
    return `${Math.round(delta / 60_000)} minutes ago`;
  }
  if (delta < 86_400_000) {
    return `${Math.round(delta / 3_600_000)} hours ago`;
  }
  return `${Math.round(delta / 86_400_000)} days ago`;
};
