"use client";

import {
  Activity,
  AlertTriangle,
  Bot,
  BriefcaseBusiness,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  ClipboardCheck,
  ClipboardCopy,
  ExternalLink,
  FileText,
  Gauge,
  History,
  KeyRound,
  LayoutDashboard,
  LockKeyhole,
  MessageSquareText,
  PlugZap,
  Plus,
  Radar,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Target,
  TerminalSquare,
  Trash2,
  UserRoundCheck,
  X
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Screen =
  | "dashboard"
  | "agent"
  | "connections"
  | "profiles"
  | "briefs"
  | "tools"
  | "audit";

type RiskLevel =
  | "read_only"
  | "draft_only"
  | "low_mutation"
  | "spend_or_publish"
  | "destructive"
  | "credential_sensitive";

type ConnectionStatus = "connected" | "pending" | "expired" | "disabled" | "error";

type Notice = {
  id: number;
  message: string;
  tone: "success" | "info" | "warning";
};

type ProviderFieldKey = "clientId" | "clientSecret" | "developerToken" | "loginCustomerId";

type ProviderField = {
  key: ProviderFieldKey;
  label: string;
  type: "text" | "password";
  required: boolean;
  placeholder?: string;
  helperText?: string;
};

type Connection = {
  key: "linkedin" | "meta" | "google";
  platform: string;
  status: ConnectionStatus;
  account: string;
  scopes: string[];
  lastValidated: string;
  configured: boolean;
  connected: boolean;
  connectPath?: string;
  setupItems: string[];
  fields: ProviderField[];
  redirectUri: string;
  docsUrl: string;
  consoleUrl: string;
  accounts?: Array<{
    id: string;
    name: string;
    role?: string;
    status?: string;
    currency?: string;
    test?: boolean;
  }>;
  error?: string;
};

type TargetProfile = {
  id: number;
  name: string;
  type: string;
  status: string;
  geography: string;
  segments: string[];
  usedBy: number;
  source: string;
};

type CampaignBrief = {
  id: number;
  name: string;
  objective: string;
  platforms: string[];
  budget: string;
  status: string;
  profile: string;
};

type ChatMessage = {
  id: number;
  actor: "user" | "agent";
  text: string;
  time: string;
};

type BrowserSessionView = {
  id: string;
  provider: "playwright";
  status: "starting" | "active" | "failed" | "completed";
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

type AuditEvent = {
  id: number;
  actor: string;
  event: string;
  risk: RiskLevel;
  tool: string;
  time: string;
};

type ApprovalStatus = "pending" | "approved" | "rejected";

type PlanSummary = {
  name: string;
  platform: string;
  budget: string;
  profile: string;
} | null;

type PanelState =
  | { kind: "search" }
  | { kind: "settings" }
  | { kind: "role" }
  | { kind: "connection"; connection: Connection }
  | null;

const navItems: Array<{ id: Screen; label: string; icon: LucideIcon }> = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "agent", label: "Agent Console", icon: MessageSquareText },
  { id: "connections", label: "Connections", icon: PlugZap },
  { id: "profiles", label: "Target Profiles", icon: Target },
  { id: "briefs", label: "Campaign Briefs", icon: FileText },
  { id: "tools", label: "Tools", icon: TerminalSquare },
  { id: "audit", label: "Audit Log", icon: History }
];

const nowTime = () =>
  new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date());

const riskLabels: Record<RiskLevel, string> = {
  read_only: "Read only",
  draft_only: "Draft only",
  low_mutation: "Low mutation",
  spend_or_publish: "Spend or publish",
  destructive: "Destructive",
  credential_sensitive: "Credential sensitive"
};

const initialProfiles: TargetProfile[] = [];

const initialBriefs: CampaignBrief[] = [];

const initialConnections: Connection[] = [];

const tools = [
  {
    name: "workspace.search_target_profiles",
    provider: "mcp-workspace-data",
    platform: "Workspace",
    risk: "read_only" as RiskLevel,
    permissions: ["campaigns.read"],
    approval: false,
    dryRun: false
  },
  {
    name: "workspace.create_campaign_brief",
    provider: "mcp-workspace-data",
    platform: "Workspace",
    risk: "draft_only" as RiskLevel,
    permissions: ["campaigns.create_draft"],
    approval: false,
    dryRun: true
  },
  {
    name: "linkedin.estimate_audience",
    provider: "mcp-linkedin-ads",
    platform: "LinkedIn Ads",
    risk: "read_only" as RiskLevel,
    permissions: ["campaigns.plan"],
    approval: false,
    dryRun: false
  },
  {
    name: "meta.create_campaign_draft",
    provider: "mcp-meta-ads",
    platform: "Meta Ads",
    risk: "spend_or_publish" as RiskLevel,
    permissions: ["campaigns.publish"],
    approval: true,
    dryRun: true
  },
  {
    name: "browser.run_playwright_flow",
    provider: "mcp-browser-control",
    platform: "Allowlisted sites",
    risk: "credential_sensitive" as RiskLevel,
    permissions: ["browser.use"],
    approval: true,
    dryRun: false
  }
];

const initialAudit: AuditEvent[] = [];

const toolTimeline = [
  {
    label: "intake_user_request",
    detail: "Classified as campaign planning",
    risk: "draft_only" as RiskLevel
  },
  {
    label: "load_workspace_context",
    detail: "3 profiles, 4 connections, 5 tools loaded",
    risk: "read_only" as RiskLevel
  },
  {
    label: "select_tools",
    detail: "Official MCP tools selected before browser fallback",
    risk: "read_only" as RiskLevel
  },
  {
    label: "approval_gate",
    detail: "Spend requires explicit approval",
    risk: "spend_or_publish" as RiskLevel
  }
];

export default function WorkspaceInterface() {
  const [activeScreen, setActiveScreen] = useState<Screen>("dashboard");
  const [profiles, setProfiles] = useState(initialProfiles);
  const [briefs, setBriefs] = useState(initialBriefs);
  const [connections, setConnections] = useState<Connection[]>(initialConnections);
  const [auditEvents, setAuditEvents] = useState(initialAudit);
  const [approvalStatus, setApprovalStatus] = useState<ApprovalStatus>("pending");
  const [activePanel, setActivePanel] = useState<PanelState>(null);
  const [connectionChecks, setConnectionChecks] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<Notice | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [latestPlan, setLatestPlan] = useState<PlanSummary>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [messageDraft, setMessageDraft] = useState("");
  const [browserSession, setBrowserSession] = useState<BrowserSessionView | null>(null);
  const [browserTargetUrl, setBrowserTargetUrl] = useState("https://www.linkedin.com/campaignmanager");
  const [browserLoading, setBrowserLoading] = useState(false);
  const [profileDraft, setProfileDraft] = useState({
    name: "",
    geography: "",
    segments: ""
  });
  const [briefDraft, setBriefDraft] = useState({
    name: "",
    objective: "Lead generation",
    budget: "",
    platform: "LinkedIn Ads"
  });

  const showNotice = (message: string, tone: Notice["tone"] = "info") => {
    setNotice({ id: Date.now(), message, tone });
  };

  const refreshConnections = useCallback(async () => {
    try {
      const response = await fetch("/api/connections", { cache: "no-store" });
      if (!response.ok) {
        throw new Error("Connection status API failed");
      }
      const payload = (await response.json()) as { providers: Connection[] };
      setConnections(payload.providers);
    } catch {
      showNotice("Could not load live connection status from the local API.", "warning");
    }
  }, []);

  const refreshBrowserStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/browser/session", { cache: "no-store" });
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as { session: BrowserSessionView | null };
      setBrowserSession(payload.session);
      if (payload.session?.currentUrl) {
        setBrowserTargetUrl(payload.session.currentUrl);
      }
    } catch {
      // Browser status is optional; the panel can start a new session.
    }
  }, []);

  useEffect(() => {
    window.setTimeout(() => {
      void refreshConnections();
      void refreshBrowserStatus();
    }, 0);

    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "linkedin") {
      window.setTimeout(() => {
        setActiveScreen("connections");
        showNotice("LinkedIn Ads connected. Accessible ad accounts are listed below.", "success");
        window.history.replaceState({}, "", window.location.pathname);
      }, 0);
    }
    if (params.get("connection_error")) {
      window.setTimeout(() => {
        setActiveScreen("connections");
        showNotice(`Connection failed: ${params.get("connection_error")}`, "warning");
        window.history.replaceState({}, "", window.location.pathname);
      }, 0);
    }
  }, [refreshBrowserStatus, refreshConnections]);

  const approvalCopy = useMemo(() => {
    if (approvalStatus === "approved") {
      return {
        title: "Approved for queued dry run",
        note: "The approved payload is locked and ready for an idempotent tool execution.",
        icon: CheckCircle2
      };
    }

    if (approvalStatus === "rejected") {
      return {
        title: "Rejected and held",
        note: "The plan remains available for revision. No external mutation was executed.",
        icon: X
      };
    }

    return {
      title: "Approval required",
      note: "This creates budgeted campaign objects, so the agent prepared a request instead of executing.",
      icon: AlertTriangle
    };
  }, [approvalStatus]);

  const searchResults = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const items: Array<{
      id: string;
      label: string;
      detail: string;
      screen: Screen;
      icon: LucideIcon;
    }> = [
      ...navItems.map((item) => ({
        id: `screen-${item.id}`,
        label: item.label,
        detail: "Workspace section",
        screen: item.id,
        icon: item.icon
      })),
      ...profiles.map((profile) => ({
        id: `profile-${profile.id}`,
        label: profile.name,
        detail: `${profile.type} - ${profile.geography}`,
        screen: "profiles" as Screen,
        icon: Target
      })),
      ...briefs.map((brief) => ({
        id: `brief-${brief.id}`,
        label: brief.name,
        detail: `${brief.objective} - ${brief.budget}`,
        screen: "briefs" as Screen,
        icon: FileText
      })),
      ...connections.map((connection) => ({
        id: `connection-${connection.platform}`,
        label: connection.platform,
        detail: `${connection.status} - ${connection.account}`,
        screen: "connections" as Screen,
        icon: PlugZap
      })),
      ...tools.map((tool) => ({
        id: `tool-${tool.name}`,
        label: tool.name,
        detail: `${tool.provider} - ${riskLabels[tool.risk]}`,
        screen: "tools" as Screen,
        icon: TerminalSquare
      }))
    ];

    if (!query) {
      return items.slice(0, 8);
    }

    return items
      .filter((item) => `${item.label} ${item.detail}`.toLowerCase().includes(query))
      .slice(0, 8);
  }, [briefs, connections, profiles, searchQuery]);


  const addAudit = (event: string, risk: RiskLevel, tool: string, actor = "user") => {
    setAuditEvents((current) => [
      {
        id: current.length + 1,
        actor,
        event,
        risk,
        tool,
        time: nowTime()
      },
      ...current
    ]);
  };

  const handleStartBrowser = (reasonBrowserNeeded?: string, url = browserTargetUrl) => {
    void (async () => {
      setBrowserLoading(true);
      try {
        const response = await fetch("/api/browser/session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url,
            reasonBrowserNeeded:
              reasonBrowserNeeded ??
              "The user asked for browser fallback because the requested workflow may not be available through an official API."
          })
        });
        const payload = (await response.json()) as {
          ok?: boolean;
          session?: BrowserSessionView;
          error?: string;
        };

        if (!response.ok || !payload.ok || !payload.session) {
          throw new Error(payload.error ?? "Browser session failed");
        }

        setBrowserSession(payload.session);
        setBrowserTargetUrl(payload.session.currentUrl);
        setActiveScreen("agent");
        setChatMessages((current) => [
          ...current,
          {
            id: current.length + 1,
            actor: "agent",
            text: "I opened a governed browser session in read-only mode. I can inspect visible UI state and screenshots, but form submissions, publishing, spend, billing, and targeting expansion still require approval.",
            time: nowTime()
          }
        ]);
        addAudit("Opened governed browser fallback session", "credential_sensitive", "browser.open_session", "agent");
        showNotice("Browser fallback opened inside the agent console.", "success");
      } catch (error) {
        showNotice(error instanceof Error ? error.message : "Could not open browser fallback.", "warning");
      } finally {
        setBrowserLoading(false);
      }
    })();
  };

  const handleNavigateBrowser = () => {
    if (!browserSession) {
      handleStartBrowser("The user requested a browser fallback session.", browserTargetUrl);
      return;
    }

    void (async () => {
      setBrowserLoading(true);
      try {
        const response = await fetch("/api/browser/session/navigate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sessionId: browserSession.id, url: browserTargetUrl })
        });
        const payload = (await response.json()) as {
          ok?: boolean;
          session?: BrowserSessionView;
          error?: string;
        };

        if (!response.ok || !payload.ok || !payload.session) {
          throw new Error(payload.error ?? "Browser navigation failed");
        }

        setBrowserSession(payload.session);
        setBrowserTargetUrl(payload.session.currentUrl);
        addAudit("Navigated governed browser fallback session", "credential_sensitive", "browser.navigate", "agent");
      } catch (error) {
        showNotice(error instanceof Error ? error.message : "Could not navigate browser.", "warning");
      } finally {
        setBrowserLoading(false);
      }
    })();
  };

  const handleRefreshBrowser = () => {
    if (!browserSession) {
      return;
    }

    void (async () => {
      setBrowserLoading(true);
      try {
        const response = await fetch("/api/browser/session", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sessionId: browserSession.id })
        });
        const payload = (await response.json()) as {
          ok?: boolean;
          session?: BrowserSessionView;
          error?: string;
        };

        if (!response.ok || !payload.ok || !payload.session) {
          throw new Error(payload.error ?? "Browser refresh failed");
        }

        setBrowserSession(payload.session);
        addAudit("Captured browser screenshot and visible page text", "read_only", "browser.take_screenshot", "agent");
      } catch (error) {
        showNotice(error instanceof Error ? error.message : "Could not refresh browser screenshot.", "warning");
      } finally {
        setBrowserLoading(false);
      }
    })();
  };

  const handleCloseBrowser = () => {
    if (!browserSession) {
      return;
    }

    void (async () => {
      const closingId = browserSession.id;
      setBrowserSession(null);
      try {
        await fetch(`/api/browser/session?sessionId=${encodeURIComponent(closingId)}`, {
          method: "DELETE"
        });
        addAudit("Closed governed browser fallback session", "read_only", "browser.close_session", "agent");
        showNotice("Browser fallback closed.", "info");
      } catch {
        showNotice("Browser session was removed from the UI, but the server close call failed.", "warning");
      }
    })();
  };

  const handleSendMessage = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = messageDraft.trim();

    if (!trimmed) {
      return;
    }

    const nextId = chatMessages.length + 1;
    setChatMessages((current) => [
      ...current,
      { id: nextId, actor: "user", text: trimmed, time: nowTime() },
      {
        id: nextId + 1,
        actor: "agent",
        text: "I can inspect workspace context and prepare safe draft work now. Any spend, publish, budget, targeting expansion, or browser form submission will be routed into an approval request.",
        time: nowTime()
      }
    ]);
    setMessageDraft("");
    addAudit("Captured agent-console message and generated governed response", "draft_only", "agent_runs.messages");
    showNotice("Agent response added to the console.", "success");
    if (/(browser|campaign manager|ui-only|rejection|not available via api|doesn't expose|does not expose|inspect.*ui)/i.test(trimmed)) {
      handleStartBrowser(
        "The user asked for browser/UI inspection because the requested information may not be exposed by an official API.",
        browserTargetUrl
      );
    }
  };

  const handleCreateProfile = (event: FormEvent) => {
    event.preventDefault();
    if (!profileDraft.name.trim()) {
      return;
    }

    setProfiles((current) => [
      {
        id: current.length + 1,
        name: profileDraft.name.trim(),
        type: "Audience rule",
        status: "draft",
        geography: profileDraft.geography.trim() || "Unscoped",
        segments: profileDraft.segments
          .split(",")
          .map((segment) => segment.trim())
          .filter(Boolean),
        usedBy: 0,
        source: "manual"
      },
      ...current
    ]);
    setProfileDraft({ name: "", geography: "", segments: "" });
    addAudit("Created target profile draft", "draft_only", "workspace.save_target_profile");
    showNotice("Target profile draft saved.", "success");
  };

  const handleCreateBrief = (event: FormEvent) => {
    event.preventDefault();
    if (!briefDraft.name.trim()) {
      return;
    }

    setBriefs((current) => [
      {
        id: current.length + 1,
        name: briefDraft.name.trim(),
        objective: briefDraft.objective,
        platforms: [briefDraft.platform],
        budget: briefDraft.budget.trim() || "Budget pending",
        status: "draft",
        profile: profiles[0]?.name ?? "Profile pending"
      },
      ...current
    ]);
    setBriefDraft({
      name: "",
      objective: "Lead generation",
      budget: "",
      platform: "LinkedIn Ads"
    });
    addAudit("Created campaign brief draft", "draft_only", "workspace.create_campaign_brief");
    showNotice("Campaign brief draft saved.", "success");
  };

  const handleGeneratePlan = (brief: CampaignBrief) => {
    setLatestPlan({
      name: brief.name,
      platform: brief.platforms.join(", "),
      budget: brief.budget,
      profile: brief.profile
    });
    setApprovalStatus("pending");
    setActiveScreen("agent");
    setChatMessages((current) => [
      ...current,
      {
        id: current.length + 1,
        actor: "user",
        text: `Generate a governed campaign plan from "${brief.name}".`,
        time: nowTime()
      },
      {
        id: current.length + 2,
        actor: "agent",
        text: `I generated a ${brief.platforms.join(", ")} plan for ${brief.profile}. It is ready for review, and execution is held at the approval gate because the budget is ${brief.budget}.`,
        time: nowTime()
      }
    ]);
    addAudit(`Generated campaign plan draft from brief "${brief.name}"`, "draft_only", "campaign_operator.plan_actions", "agent");
    showNotice("Plan generated and opened in the agent console.", "success");
  };

  const handleTestConnection = (connection: Connection) => {
    void (async () => {
      try {
        const response = await fetch(`/api/connections/${connection.key}/test`, {
          method: "POST"
        });
        const payload = (await response.json()) as {
          ok?: boolean;
          providers?: Connection[];
          error?: string;
        };

        if (!response.ok || !payload.ok) {
          throw new Error(payload.error ?? "Connection test failed");
        }

        if (payload.providers) {
          setConnections(payload.providers);
        }
        setConnectionChecks((current) => ({
          ...current,
          [connection.platform]: "Just now"
        }));
        addAudit(`Validated ${connection.platform} connection with redacted credentials`, "read_only", "connections.test");
        showNotice(`${connection.platform} connection check completed.`, "success");
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown connection error";
        addAudit(`Connection test failed for ${connection.platform}`, "read_only", "connections.test");
        showNotice(message, "warning");
      }
    })();
  };

  const handleOpenCredential = (connection: Connection) => {
    setActivePanel({ kind: "connection", connection });
    addAudit(`Opened redacted credential reference for ${connection.platform}`, "credential_sensitive", "connections.inspect_redacted");
  };

  const handleCredentialsSaved = useCallback(
    (providers: Connection[], saved: Connection) => {
      setConnections(providers);
      const refreshed = providers.find((provider) => provider.key === saved.key);
      if (refreshed) {
        setActivePanel({ kind: "connection", connection: refreshed });
      }
      addAudit(
        `Saved OAuth client credentials for ${saved.platform}`,
        "credential_sensitive",
        "connections.save_credentials"
      );
      showNotice(`${saved.platform} credentials saved. Encrypted to the local secret store.`, "success");
    },
    []
  );

  const handleClearCredentials = useCallback((connection: Connection) => {
    void (async () => {
      try {
        const response = await fetch(`/api/connections/${connection.key}/setup`, {
          method: "DELETE"
        });
        const payload = (await response.json()) as {
          ok?: boolean;
          providers?: Connection[];
          error?: string;
        };
        if (!response.ok || !payload.ok || !payload.providers) {
          throw new Error(payload.error ?? "Failed to clear credentials");
        }
        setConnections(payload.providers);
        const refreshed = payload.providers.find((provider) => provider.key === connection.key);
        if (refreshed) {
          setActivePanel({ kind: "connection", connection: refreshed });
        }
        addAudit(
          `Cleared OAuth client credentials for ${connection.platform}`,
          "credential_sensitive",
          "connections.clear_credentials"
        );
        showNotice(`${connection.platform} credentials cleared.`, "info");
      } catch (error) {
        showNotice(
          error instanceof Error ? error.message : "Failed to clear credentials",
          "warning"
        );
      }
    })();
  }, []);

  const setApproval = (status: ApprovalStatus) => {
    setApprovalStatus(status);
    addAudit(
      status === "approved" ? "Approved campaign-plan execution request" : "Rejected campaign-plan execution request",
      "spend_or_publish",
      "mcp-approval.decide",
      "user"
    );
    showNotice(
      status === "approved" ? "Approval recorded. Execution payload is now locked." : "Rejection recorded. No external action was run.",
      status === "approved" ? "success" : "warning"
    );
  };

  return (
    <main className="workspace-shell">
      <aside className="sidebar" aria-label="Workspace navigation">
        <div className="brand-lockup">
          <div className="brand-mark">
            <Sparkles aria-hidden="true" size={22} />
          </div>
          <div>
            <p className="eyebrow">YieldAgent</p>
            <h1>Campaign Ops</h1>
          </div>
        </div>

        <nav className="nav-list">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = item.id === activeScreen;

            return (
              <button
                key={item.id}
                type="button"
                className={active ? "nav-item active" : "nav-item"}
                onClick={() => setActiveScreen(item.id)}
              >
                <Icon aria-hidden="true" size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="safety-panel">
          <ShieldCheck aria-hidden="true" size={20} />
          <div>
            <strong>Approval gates active</strong>
            <span>Spend, publish, broad targeting, and browser submits are held.</span>
          </div>
        </div>
      </aside>

      <section className="content-area">
        <header className="topbar">
          <div>
            <p className="eyebrow">Workspace</p>
            <h2>TensorOps Growth Lab</h2>
          </div>

          <div className="topbar-actions">
            <button
              className="icon-button"
              type="button"
              title="Search workspace"
              aria-label="Search workspace"
              onClick={() => {
                setSearchQuery("");
                setActivePanel({ kind: "search" });
              }}
            >
              <Search aria-hidden="true" size={18} />
            </button>
            <button
              className="icon-button"
              type="button"
              title="Workspace settings"
              aria-label="Workspace settings"
              onClick={() => setActivePanel({ kind: "settings" })}
            >
              <Settings2 aria-hidden="true" size={18} />
            </button>
            <button className="user-pill" type="button" onClick={() => setActivePanel({ kind: "role" })}>
              <UserRoundCheck aria-hidden="true" size={16} />
              <span>Owner</span>
            </button>
          </div>
        </header>

        {notice && <NoticeBanner notice={notice} onClose={() => setNotice(null)} />}

        {activeScreen === "dashboard" && (
          <DashboardScreen
            approvalStatus={approvalStatus}
            auditEvents={auditEvents}
            briefs={briefs}
            connections={connections}
            latestPlan={latestPlan}
            profiles={profiles}
            setActiveScreen={setActiveScreen}
          />
        )}

        {activeScreen === "agent" && (
          <AgentScreen
            approvalCopy={approvalCopy}
            approvalStatus={approvalStatus}
            browserLoading={browserLoading}
            browserSession={browserSession}
            browserTargetUrl={browserTargetUrl}
            chatMessages={chatMessages}
            latestPlan={latestPlan}
            messageDraft={messageDraft}
            setBrowserTargetUrl={setBrowserTargetUrl}
            setMessageDraft={setMessageDraft}
            handleSendMessage={handleSendMessage}
            onCloseBrowser={handleCloseBrowser}
            onNavigateBrowser={handleNavigateBrowser}
            onRefreshBrowser={handleRefreshBrowser}
            onStartBrowser={() => handleStartBrowser()}
            setApproval={setApproval}
          />
        )}

        {activeScreen === "connections" && (
          <ConnectionsScreen
            connectionChecks={connectionChecks}
            connections={connections}
            onTestConnection={handleTestConnection}
            onViewCredential={handleOpenCredential}
          />
        )}

        {activeScreen === "profiles" && (
          <ProfilesScreen
            profileDraft={profileDraft}
            profiles={profiles}
            setProfileDraft={setProfileDraft}
            handleCreateProfile={handleCreateProfile}
          />
        )}

        {activeScreen === "briefs" && (
          <BriefsScreen
            briefDraft={briefDraft}
            briefs={briefs}
            setBriefDraft={setBriefDraft}
            handleCreateBrief={handleCreateBrief}
            handleGeneratePlan={handleGeneratePlan}
          />
        )}

        {activeScreen === "tools" && <ToolsScreen />}

        {activeScreen === "audit" && <AuditScreen auditEvents={auditEvents} />}
      </section>

      {activePanel && (
        <WorkspacePanel
          panel={activePanel}
          searchQuery={searchQuery}
          searchResults={searchResults}
          setSearchQuery={setSearchQuery}
          onClose={() => setActivePanel(null)}
          onNavigate={(screen) => {
            setActiveScreen(screen);
            setActivePanel(null);
            showNotice(`Opened ${navItems.find((item) => item.id === screen)?.label ?? "workspace section"}.`, "info");
          }}
          onTestConnection={handleTestConnection}
          onCredentialsSaved={handleCredentialsSaved}
          onClearCredentials={handleClearCredentials}
        />
      )}
    </main>
  );
}

function DashboardScreen({
  approvalStatus,
  auditEvents,
  briefs,
  connections,
  latestPlan,
  profiles,
  setActiveScreen
}: {
  approvalStatus: ApprovalStatus;
  auditEvents: AuditEvent[];
  briefs: CampaignBrief[];
  connections: Connection[];
  latestPlan: PlanSummary;
  profiles: TargetProfile[];
  setActiveScreen: (screen: Screen) => void;
}) {
  const connectedCount = connections.filter((connection) => connection.connected).length;
  const pendingApprovals = latestPlan && approvalStatus === "pending" ? 1 : 0;
  const planObjects = latestPlan
    ? [
        `Platform: ${latestPlan.platform}`,
        `Budget: ${latestPlan.budget}`,
        `Audience profile: ${latestPlan.profile}`,
        "Execution: held until explicit approval"
      ]
    : [];

  return (
    <div className="screen-stack">
      <section className="summary-grid" aria-label="Workspace summary">
        <MetricTile icon={CircleDollarSign} label="Tracked spend" value="0" helper="Connect an ads account to sync spend" tone="green" />
        <MetricTile icon={Activity} label="Active campaigns" value="0" helper="No campaign data synced yet" tone="blue" />
        <MetricTile icon={ClipboardCheck} label="Pending approvals" value={String(pendingApprovals)} helper="Risk gate enforced" tone="amber" />
        <MetricTile icon={Radar} label="Connections" value={String(connectedCount)} helper={`${connections.length} providers available`} tone="rose" />
      </section>

      <section className="dashboard-grid">
        <div className="panel wide-panel">
          <PanelHeader
            eyebrow="Agent Command Center"
            title={latestPlan ? latestPlan.name : "No campaign plan yet"}
            actionLabel="Open agent"
            onAction={() => setActiveScreen("agent")}
          />
          {latestPlan ? (
            <div className="plan-preview">
              <div className="plan-score">
                <Gauge aria-hidden="true" size={36} />
                <strong>Medium risk</strong>
                <span>Approval required before spend or publish.</span>
              </div>
              <div className="plan-detail-list">
                {planObjects.map((item) => (
                  <div className="plan-line" key={item}>
                    <CheckCircle2 aria-hidden="true" size={18} />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState
              icon={Bot}
              title="Connect LinkedIn Ads, then ask the agent to inspect real workspace data."
              actionLabel="Set up connections"
              onAction={() => setActiveScreen("connections")}
            />
          )}
        </div>

        <div className="panel">
          <PanelHeader eyebrow="Connections" title="Platform readiness" />
          <div className="status-list">
            {connections.slice(0, 4).map((connection) => (
              <div className="status-row" key={connection.platform}>
                <div>
                  <strong>{connection.platform}</strong>
                  <span>{connection.account}</span>
                </div>
                <StatusPill status={connection.status} />
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <PanelHeader eyebrow="Library" title="Target profiles" actionLabel="Add profile" onAction={() => setActiveScreen("profiles")} />
          {profiles.length > 0 ? (
            <div className="compact-list">
              {profiles.slice(0, 3).map((profile) => (
                <div className="compact-row" key={profile.id}>
                  <Target aria-hidden="true" size={18} />
                  <div>
                    <strong>{profile.name}</strong>
                    <span>{profile.segments.slice(0, 2).join(", ")}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={Target} title="No target profiles saved yet." actionLabel="Create profile" onAction={() => setActiveScreen("profiles")} />
          )}
        </div>

        <div className="panel">
          <PanelHeader eyebrow="Campaigns" title="Brief pipeline" actionLabel="New brief" onAction={() => setActiveScreen("briefs")} />
          {briefs.length > 0 ? (
            <div className="compact-list">
              {briefs.slice(0, 3).map((brief) => (
                <div className="compact-row" key={brief.id}>
                  <BriefcaseBusiness aria-hidden="true" size={18} />
                  <div>
                    <strong>{brief.name}</strong>
                    <span>{brief.status} - {brief.budget}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={BriefcaseBusiness} title="No campaign briefs yet." actionLabel="Create brief" onAction={() => setActiveScreen("briefs")} />
          )}
        </div>

        <div className="panel wide-panel">
          <PanelHeader eyebrow="Audit" title="Recent action trail" actionLabel="View log" onAction={() => setActiveScreen("audit")} />
          {auditEvents.length > 0 ? (
            <AuditRows auditEvents={auditEvents.slice(0, 4)} />
          ) : (
            <EmptyState icon={History} title="No audit events recorded yet." />
          )}
        </div>
      </section>
    </div>
  );
}

function AgentScreen({
  approvalCopy,
  approvalStatus,
  browserLoading,
  browserSession,
  browserTargetUrl,
  chatMessages,
  latestPlan,
  messageDraft,
  setBrowserTargetUrl,
  setMessageDraft,
  handleSendMessage,
  onCloseBrowser,
  onNavigateBrowser,
  onRefreshBrowser,
  onStartBrowser,
  setApproval
}: {
  approvalCopy: { title: string; note: string; icon: LucideIcon };
  approvalStatus: ApprovalStatus;
  browserLoading: boolean;
  browserSession: BrowserSessionView | null;
  browserTargetUrl: string;
  chatMessages: ChatMessage[];
  latestPlan: PlanSummary;
  messageDraft: string;
  setBrowserTargetUrl: (value: string) => void;
  setMessageDraft: (value: string) => void;
  handleSendMessage: (event: FormEvent) => void;
  onCloseBrowser: () => void;
  onNavigateBrowser: () => void;
  onRefreshBrowser: () => void;
  onStartBrowser: () => void;
  setApproval: (status: ApprovalStatus) => void;
}) {
  const ApprovalIcon = approvalCopy.icon;

  return (
    <div className="agent-layout">
      <section className="chat-panel">
        <PanelHeader eyebrow="Workspace Operator" title="Agent Console" />
        <div className="message-stream" aria-live="polite">
          {chatMessages.length > 0 ? (
            chatMessages.map((message) => (
              <article className={`message ${message.actor}`} key={message.id}>
                <div className="avatar">{message.actor === "agent" ? <Bot aria-hidden="true" size={18} /> : <UserRoundCheck aria-hidden="true" size={18} />}</div>
                <div>
                  <div className="message-meta">
                    <strong>{message.actor === "agent" ? "Campaign Codex" : "You"}</strong>
                    <span>{message.time}</span>
                  </div>
                  <p>{message.text}</p>
                </div>
              </article>
            ))
          ) : (
            <EmptyState
              icon={MessageSquareText}
              title="No agent run yet."
              description="Connect an ads account or create a brief, then ask the operator to inspect, plan, or explain real workspace data."
            />
          )}
        </div>
        <form className="composer" onSubmit={handleSendMessage}>
          <input
            aria-label="Message Campaign Codex"
            placeholder="Ask for a plan, report, profile, or safe workspace action"
            value={messageDraft}
            onChange={(event) => setMessageDraft(event.target.value)}
          />
          <button className="primary-icon-button" type="submit" title="Send message" aria-label="Send message">
            <Send aria-hidden="true" size={18} />
          </button>
        </form>
      </section>

      <aside className="agent-side">
        <BrowserFallbackPanel
          browserLoading={browserLoading}
          browserSession={browserSession}
          browserTargetUrl={browserTargetUrl}
          setBrowserTargetUrl={setBrowserTargetUrl}
          onCloseBrowser={onCloseBrowser}
          onNavigateBrowser={onNavigateBrowser}
          onRefreshBrowser={onRefreshBrowser}
          onStartBrowser={onStartBrowser}
        />

        <div className="panel">
          <PanelHeader eyebrow="Execution Trace" title="Tool-call timeline" />
          {chatMessages.length > 0 || latestPlan ? (
            <div className="timeline">
              {toolTimeline.map((item) => (
                <div className="timeline-item" key={item.label}>
                  <span className="timeline-dot" />
                  <div>
                    <strong>{item.label}</strong>
                    <p>{item.detail}</p>
                    <RiskPill risk={item.risk} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={TerminalSquare} title="Tool calls will appear here after the first agent run." />
          )}
        </div>

        <div className="panel">
          <PanelHeader eyebrow="Approval" title={approvalCopy.title} />
          {latestPlan ? (
            <>
              <div className={`approval-card ${approvalStatus}`}>
                <ApprovalIcon aria-hidden="true" size={24} />
                <p>{approvalCopy.note}</p>
              </div>
              <div className="approval-details">
                <div>
                  <span>Budget impact</span>
                  <strong>{latestPlan.budget}</strong>
                </div>
                <div>
                  <span>Objects affected</span>
                  <strong>{latestPlan.platform} plan for {latestPlan.profile}</strong>
                </div>
                <div>
                  <span>Execution mode</span>
                  <strong>Approved payload + idempotency key</strong>
                </div>
              </div>
              <div className="approval-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setApproval("rejected")}
                  disabled={approvalStatus === "rejected"}
                >
                  <X aria-hidden="true" size={16} />
                  Reject
                </button>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => setApproval("approved")}
                  disabled={approvalStatus === "approved"}
                >
                  <Check aria-hidden="true" size={16} />
                  Approve
                </button>
              </div>
            </>
          ) : (
            <EmptyState icon={ClipboardCheck} title="No risky action is waiting for approval." />
          )}
        </div>
      </aside>
    </div>
  );
}

function BrowserFallbackPanel({
  browserLoading,
  browserSession,
  browserTargetUrl,
  setBrowserTargetUrl,
  onCloseBrowser,
  onNavigateBrowser,
  onRefreshBrowser,
  onStartBrowser
}: {
  browserLoading: boolean;
  browserSession: BrowserSessionView | null;
  browserTargetUrl: string;
  setBrowserTargetUrl: (value: string) => void;
  onCloseBrowser: () => void;
  onNavigateBrowser: () => void;
  onRefreshBrowser: () => void;
  onStartBrowser: () => void;
}) {
  return (
    <div className="panel browser-panel">
      <PanelHeader eyebrow="Browser Fallback" title={browserSession ? "Live governed session" : "Ready when APIs stop short"} />

      <div className="browser-policy">
        <ShieldCheck aria-hidden="true" size={18} />
        <div>
          <strong>Read-only until approval</strong>
          <span>Navigation, screenshots, and page-state extraction are allowed. Submit, publish, spend, billing, and broad targeting are forbidden.</span>
        </div>
      </div>

      <div className="browser-url-row">
        <input
          aria-label="Browser fallback URL"
          value={browserTargetUrl}
          onChange={(event) => setBrowserTargetUrl(event.target.value)}
          placeholder="https://www.linkedin.com/campaignmanager"
        />
        <button
          className="primary-icon-button"
          type="button"
          title={browserSession ? "Navigate browser" : "Start browser"}
          aria-label={browserSession ? "Navigate browser" : "Start browser"}
          onClick={browserSession ? onNavigateBrowser : onStartBrowser}
          disabled={browserLoading}
        >
          <ExternalLink aria-hidden="true" size={18} />
        </button>
      </div>

      {browserSession ? (
        <>
          <div className={`browser-status ${browserSession.status}`}>
            <div>
              <strong>{browserSession.title}</strong>
              <span>{browserSession.currentUrl}</span>
            </div>
            <StatusPill status={browserSession.status === "failed" ? "error" : "connected"} />
          </div>

          <div className="browser-frame" aria-live="polite">
            {browserSession.lastScreenshotDataUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={browserSession.lastScreenshotDataUrl} alt="Current browser session screenshot" />
            ) : (
              <EmptyState icon={RefreshCw} title={browserLoading ? "Opening browser..." : "No screenshot captured yet."} />
            )}
          </div>

          <div className="browser-actions">
            <button className="secondary-button" type="button" onClick={onRefreshBrowser} disabled={browserLoading}>
              <RefreshCw aria-hidden="true" size={16} />
              Refresh
            </button>
            <button className="secondary-button" type="button" onClick={onCloseBrowser}>
              <X aria-hidden="true" size={16} />
              Close
            </button>
          </div>

          <div className="browser-policy-details">
            <InfoBlock title="Reason browser is needed" value={browserSession.reasonBrowserNeeded} />
            <InfoBlock title="Allowed domains" value={browserSession.allowedDomains.slice(0, 8).join(", ")} />
            <InfoBlock title="Last capture" value={browserSession.lastScreenshotAt ?? "Pending"} />
          </div>
        </>
      ) : (
        <EmptyState
          icon={ExternalLink}
          title="No browser session is active."
          description="Start one when an ad-platform feature is unavailable via API. The session appears here as audited screenshots."
          actionLabel={browserLoading ? "Opening..." : "Start browser"}
          onAction={onStartBrowser}
        />
      )}
    </div>
  );
}

function ConnectionsScreen({
  connectionChecks,
  connections,
  onTestConnection,
  onViewCredential
}: {
  connectionChecks: Record<string, string>;
  connections: Connection[];
  onTestConnection: (connection: Connection) => void;
  onViewCredential: (connection: Connection) => void;
}) {
  return (
    <div className="screen-stack">
      <ScreenTitle
        eyebrow="Workspace Admin"
        title="Connections"
        description="OAuth credentials stay in the secret store; agents only receive scoped connection references."
      />
      <div className="connection-grid">
        {connections.map((connection) => (
          <article className="connection-card" key={connection.platform}>
            <div className="connection-heading">
              <div>
                <h3>{connection.platform}</h3>
                <p>{connection.account}</p>
              </div>
              <StatusPill status={connection.status} />
            </div>
            {connection.scopes.length > 0 ? (
              <div className="scope-list">
                {connection.scopes.map((scope) => (
                  <span key={scope}>{scope}</span>
                ))}
              </div>
            ) : (
              <div className="setup-list">
                {connection.setupItems.map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            )}
            {connection.accounts && connection.accounts.length > 0 && (
              <div className="account-list">
                {connection.accounts.map((account) => (
                  <div className="account-row" key={account.id}>
                    <div>
                      <strong>{account.name}</strong>
                      <span>{account.id}{account.role ? ` - ${account.role}` : ""}</span>
                    </div>
                    {account.status && <span className="soft-pill">{account.status}</span>}
                  </div>
                ))}
              </div>
            )}
            <div className="connection-footer">
              <span>Validated {connectionChecks[connection.platform] ?? connection.lastValidated}</span>
              <div className="button-row">
                {connection.connected ? (
                  <>
                    <button
                      className="icon-button"
                      type="button"
                      title="Test connection"
                      aria-label={`Test ${connection.platform}`}
                      onClick={() => onTestConnection(connection)}
                    >
                      <RefreshCw aria-hidden="true" size={17} />
                    </button>
                    <button
                      className="icon-button"
                      type="button"
                      title="View credential reference"
                      aria-label={`View ${connection.platform} credential reference`}
                      onClick={() => onViewCredential(connection)}
                    >
                      <KeyRound aria-hidden="true" size={17} />
                    </button>
                  </>
                ) : connection.configured ? (
                  <>
                    <button
                      className="icon-button"
                      type="button"
                      title="Edit credentials"
                      aria-label={`Edit ${connection.platform} credentials`}
                      onClick={() => onViewCredential(connection)}
                    >
                      <Settings2 aria-hidden="true" size={17} />
                    </button>
                    {connection.connectPath && (
                      <a className="primary-link-button" href={connection.connectPath}>
                        <ExternalLink aria-hidden="true" size={16} />
                        Connect
                      </a>
                    )}
                  </>
                ) : (
                  <button className="secondary-button" type="button" onClick={() => onViewCredential(connection)}>
                    <Settings2 aria-hidden="true" size={16} />
                    Setup
                  </button>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function ProfilesScreen({
  profileDraft,
  profiles,
  setProfileDraft,
  handleCreateProfile
}: {
  profileDraft: { name: string; geography: string; segments: string };
  profiles: TargetProfile[];
  setProfileDraft: (draft: { name: string; geography: string; segments: string }) => void;
  handleCreateProfile: (event: FormEvent) => void;
}) {
  return (
    <div className="screen-stack">
      <ScreenTitle
        eyebrow="Audience Library"
        title="Target Profiles"
        description="Generic target profiles are saved first, then translated into platform-specific IDs by tools."
      />
      <div className="split-layout">
        <form className="panel form-panel" onSubmit={handleCreateProfile}>
          <PanelHeader eyebrow="Draft" title="Create target profile" />
          <label>
            <span>Name</span>
            <input
              value={profileDraft.name}
              onChange={(event) => setProfileDraft({ ...profileDraft, name: event.target.value })}
              placeholder="Healthcare CFOs in Benelux"
            />
          </label>
          <label>
            <span>Geography</span>
            <input
              value={profileDraft.geography}
              onChange={(event) => setProfileDraft({ ...profileDraft, geography: event.target.value })}
              placeholder="Belgium, Netherlands, Luxembourg"
            />
          </label>
          <label>
            <span>Segments</span>
            <textarea
              value={profileDraft.segments}
              onChange={(event) => setProfileDraft({ ...profileDraft, segments: event.target.value })}
              placeholder="CFO, Finance Director, Healthcare, 501-5000 employees"
            />
          </label>
          <button className="primary-button" type="submit">
            <Plus aria-hidden="true" size={16} />
            Save draft
          </button>
        </form>

        <section className="table-panel">
          {profiles.length > 0 ? (
            <>
              <div className="table-header">
                <span>Name</span>
                <span>Scope</span>
                <span>Usage</span>
                <span>Status</span>
              </div>
              {profiles.map((profile) => (
                <article className="table-row" key={profile.id}>
                  <div>
                    <strong>{profile.name}</strong>
                    <span>{profile.type} - {profile.source}</span>
                  </div>
                  <div>
                    <strong>{profile.geography}</strong>
                    <span>{profile.segments.join(", ") || "Segments pending"}</span>
                  </div>
                  <span>{profile.usedBy} campaigns</span>
                  <span className="soft-pill">{profile.status}</span>
                </article>
              ))}
            </>
          ) : (
            <EmptyState icon={Target} title="No target profiles yet." description="Save your first profile to use it in campaign briefs and targeting translations." />
          )}
        </section>
      </div>
    </div>
  );
}

function BriefsScreen({
  briefDraft,
  briefs,
  setBriefDraft,
  handleCreateBrief,
  handleGeneratePlan
}: {
  briefDraft: { name: string; objective: string; budget: string; platform: string };
  briefs: CampaignBrief[];
  setBriefDraft: (draft: { name: string; objective: string; budget: string; platform: string }) => void;
  handleCreateBrief: (event: FormEvent) => void;
  handleGeneratePlan: (brief: CampaignBrief) => void;
}) {
  return (
    <div className="screen-stack">
      <ScreenTitle
        eyebrow="Planning"
        title="Campaign Briefs"
        description="Briefs capture intent, constraints, budget, brand rules, target profiles, and approval policy."
      />
      <div className="split-layout">
        <form className="panel form-panel" onSubmit={handleCreateBrief}>
          <PanelHeader eyebrow="Draft" title="Create campaign brief" />
          <label>
            <span>Name</span>
            <input
              value={briefDraft.name}
              onChange={(event) => setBriefDraft({ ...briefDraft, name: event.target.value })}
              placeholder="Q4 pipeline acceleration"
            />
          </label>
          <label>
            <span>Objective</span>
            <select
              value={briefDraft.objective}
              onChange={(event) => setBriefDraft({ ...briefDraft, objective: event.target.value })}
            >
              <option>Lead generation</option>
              <option>Traffic</option>
              <option>Awareness</option>
              <option>Sales</option>
            </select>
          </label>
          <label>
            <span>Platform</span>
            <select
              value={briefDraft.platform}
              onChange={(event) => setBriefDraft({ ...briefDraft, platform: event.target.value })}
            >
              <option>LinkedIn Ads</option>
              <option>Meta Ads</option>
              <option>Google Ads</option>
            </select>
          </label>
          <label>
            <span>Budget</span>
            <input
              value={briefDraft.budget}
              onChange={(event) => setBriefDraft({ ...briefDraft, budget: event.target.value })}
              placeholder="EUR 2,000 total"
            />
          </label>
          <button className="primary-button" type="submit">
            <Plus aria-hidden="true" size={16} />
            Save brief
          </button>
        </form>

        {briefs.length > 0 ? (
          <section className="brief-board">
            {briefs.map((brief) => (
              <article className="brief-card" key={brief.id}>
                <div className="brief-card-top">
                  <div>
                    <h3>{brief.name}</h3>
                    <p>{brief.objective}</p>
                  </div>
                  <span className="soft-pill">{brief.status}</span>
                </div>
                <div className="brief-meta">
                  <span>{brief.platforms.join(", ")}</span>
                  <span>{brief.budget}</span>
                  <span>{brief.profile}</span>
                </div>
                <button className="ghost-button" type="button" onClick={() => handleGeneratePlan(brief)}>
                  Generate plan
                  <ChevronRight aria-hidden="true" size={16} />
                </button>
              </article>
            ))}
          </section>
        ) : (
          <section className="panel">
            <EmptyState icon={FileText} title="No briefs yet." description="Create a brief here, then generate a governed plan from it." />
          </section>
        )}
      </div>
    </div>
  );
}

function ToolsScreen() {
  return (
    <div className="screen-stack">
      <ScreenTitle
        eyebrow="Governance"
        title="Tool Registry"
        description="Tools declare credentials, permissions, risk, mutation behavior, dry-run support, and approval requirements."
      />
      <section className="table-panel tools-table">
        <div className="table-header tool-table-header">
          <span>Tool</span>
          <span>Provider</span>
          <span>Risk</span>
          <span>Controls</span>
        </div>
        {tools.map((tool) => (
          <article className="table-row tool-row" key={tool.name}>
            <div>
              <strong>{tool.name}</strong>
              <span>{tool.platform}</span>
            </div>
            <div>
              <strong>{tool.provider}</strong>
              <span>{tool.permissions.join(", ")}</span>
            </div>
            <RiskPill risk={tool.risk} />
            <div className="control-pill-row">
              <span className={tool.approval ? "control-pill warn" : "control-pill"}>{tool.approval ? "Approval" : "Auto-safe"}</span>
              <span className={tool.dryRun ? "control-pill" : "control-pill muted"}>{tool.dryRun ? "Dry run" : "No dry run"}</span>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function AuditScreen({ auditEvents }: { auditEvents: AuditEvent[] }) {
  return (
    <div className="screen-stack">
      <ScreenTitle
        eyebrow="Evidence"
        title="Audit Log"
        description="Every user message, plan, permission check, tool call, approval decision, and external mutation is recorded."
      />
      <section className="panel">
        {auditEvents.length > 0 ? (
          <AuditRows auditEvents={auditEvents} />
        ) : (
          <EmptyState icon={History} title="No audit events yet." description="Real connection checks, saved drafts, plan generation, and approvals will appear here." />
        )}
      </section>
    </div>
  );
}

function NoticeBanner({ notice, onClose }: { notice: Notice; onClose: () => void }) {
  return (
    <div className={`notice-banner ${notice.tone}`} role="status">
      <span>{notice.message}</span>
      <button className="icon-button compact" type="button" onClick={onClose} aria-label="Dismiss notice">
        <X aria-hidden="true" size={15} />
      </button>
    </div>
  );
}

function WorkspacePanel({
  panel,
  searchQuery,
  searchResults,
  setSearchQuery,
  onClose,
  onNavigate,
  onTestConnection,
  onCredentialsSaved,
  onClearCredentials
}: {
  panel: Exclude<PanelState, null>;
  searchQuery: string;
  searchResults: Array<{
    id: string;
    label: string;
    detail: string;
    screen: Screen;
    icon: LucideIcon;
  }>;
  setSearchQuery: (query: string) => void;
  onClose: () => void;
  onNavigate: (screen: Screen) => void;
  onTestConnection: (connection: Connection) => void;
  onCredentialsSaved: (providers: Connection[], saved: Connection) => void;
  onClearCredentials: (connection: Connection) => void;
}) {
  return (
    <div className="panel-scrim" role="presentation" onMouseDown={onClose}>
      <aside className="drawer" aria-label="Workspace panel" onMouseDown={(event) => event.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <span className="eyebrow">
              {panel.kind === "search" && "Search"}
              {panel.kind === "settings" && "Settings"}
              {panel.kind === "role" && "Access"}
              {panel.kind === "connection" && "Connection"}
            </span>
            <h3>
              {panel.kind === "search" && "Find workspace data"}
              {panel.kind === "settings" && "Workspace settings"}
              {panel.kind === "role" && "Current role"}
              {panel.kind === "connection" && panel.connection.platform}
            </h3>
          </div>
          <button className="icon-button compact" type="button" onClick={onClose} aria-label="Close panel">
            <X aria-hidden="true" size={16} />
          </button>
        </div>

        {panel.kind === "search" && (
          <div className="drawer-body">
            <input
              autoFocus
              aria-label="Search workspace"
              placeholder="Search connections, profiles, briefs, tools"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <div className="search-results">
              {searchResults.map((result) => {
                const Icon = result.icon;

                return (
                  <button className="search-result" type="button" key={result.id} onClick={() => onNavigate(result.screen)}>
                    <Icon aria-hidden="true" size={18} />
                    <span>
                      <strong>{result.label}</strong>
                      <small>{result.detail}</small>
                    </span>
                  </button>
                );
              })}
              {searchResults.length === 0 && <EmptyState icon={Search} title="No matches found." />}
            </div>
          </div>
        )}

        {panel.kind === "settings" && (
          <div className="drawer-body">
            <InfoBlock title="Workspace slug" value="tensorops-growth-lab" />
            <InfoBlock title="Approval policy" value="Spend, publish, destructive, targeting expansion, and browser submits require approval." />
            <InfoBlock title="Secret policy" value="OAuth tokens are accepted only through server-side routes and saved as encrypted local credentials." />
          </div>
        )}

        {panel.kind === "role" && (
          <div className="drawer-body">
            <InfoBlock title="Role" value="Owner" />
            <InfoBlock title="Allowed now" value="Manage connections, create drafts, approve requests, view audit log." />
            <InfoBlock title="Still gated" value="No autonomous spend, publish, billing, deletion, or browser form submission." />
          </div>
        )}

        {panel.kind === "connection" && (
          <div className="drawer-body">
            <InfoBlock title="Status" value={panel.connection.status} />
            <InfoBlock title="Account" value={panel.connection.account} />
            <InfoBlock
              title="Credential reference"
              value={panel.connection.connected ? `${panel.connection.key}:encrypted-local-token` : "No credential stored"}
            />

            {panel.connection.connected ? (
              <div className="drawer-actions">
                <button className="primary-button" type="button" onClick={() => onTestConnection(panel.connection)}>
                  <RefreshCw aria-hidden="true" size={16} />
                  Test connection
                </button>
                <button className="secondary-button" type="button" onClick={() => onClearCredentials(panel.connection)}>
                  <Trash2 aria-hidden="true" size={16} />
                  Clear credentials
                </button>
              </div>
            ) : panel.connection.configured ? (
              <>
                <div className="drawer-actions">
                  {panel.connection.connectPath ? (
                    <a className="primary-link-button full" href={panel.connection.connectPath}>
                      <ExternalLink aria-hidden="true" size={16} />
                      Start OAuth
                    </a>
                  ) : (
                    <InfoBlock
                      title="OAuth flow"
                      value="Credentials saved. The OAuth start route for this provider is not yet implemented."
                    />
                  )}
                  <button className="secondary-button" type="button" onClick={() => onClearCredentials(panel.connection)}>
                    <Trash2 aria-hidden="true" size={16} />
                    Clear credentials
                  </button>
                </div>
                <CredentialsForm
                  connection={panel.connection}
                  onSaved={onCredentialsSaved}
                  editing
                />
              </>
            ) : (
              <CredentialsForm connection={panel.connection} onSaved={onCredentialsSaved} />
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

function CredentialsForm({
  connection,
  onSaved,
  editing = false
}: {
  connection: Connection;
  onSaved: (providers: Connection[], saved: Connection) => void;
  editing?: boolean;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const filledFieldCount = connection.fields.filter(
    (field) => (values[field.key] ?? "").trim().length > 0
  ).length;
  const missingRequired = connection.fields
    .filter((field) => field.required && !(values[field.key] ?? "").trim())
    .map((field) => field.label);
  const canSubmit = editing
    ? filledFieldCount > 0 && !submitting
    : missingRequired.length === 0 && !submitting;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, string> = {};
      for (const field of connection.fields) {
        const trimmed = (values[field.key] ?? "").trim();
        if (trimmed) {
          payload[field.key] = trimmed;
        }
      }
      const response = await fetch(`/api/connections/${connection.key}/setup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const body = (await response.json()) as {
        ok?: boolean;
        providers?: Connection[];
        error?: string;
      };
      if (!response.ok || !body.ok || !body.providers) {
        throw new Error(body.error ?? "Failed to save credentials");
      }
      setValues({});
      onSaved(body.providers, connection);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to save credentials");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCopyRedirect = async () => {
    try {
      await navigator.clipboard.writeText(connection.redirectUri);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be unavailable (insecure context); user can still copy manually.
    }
  };

  return (
    <div className="credentials-setup">
      {!editing && (
        <div className="redirect-uri-block">
          <span className="eyebrow">Redirect URI</span>
          <div className="redirect-uri-row">
            <code>{connection.redirectUri}</code>
            <button
              type="button"
              className="icon-button compact"
              onClick={handleCopyRedirect}
              title="Copy redirect URI"
              aria-label="Copy redirect URI"
            >
              <ClipboardCopy aria-hidden="true" size={14} />
            </button>
          </div>
          <p className="redirect-uri-hint">
            {copied ? "Copied to clipboard." : `Register this URL in your ${connection.platform} app before connecting.`}
          </p>
          <a
            className="redirect-uri-docs"
            href={connection.docsUrl}
            target="_blank"
            rel="noreferrer"
          >
            {connection.platform} setup docs
            <ExternalLink aria-hidden="true" size={13} />
          </a>
        </div>
      )}

      <form className="credentials-form" onSubmit={handleSubmit}>
        {editing && (
          <p className="credentials-form-hint">
            Update saved credentials. Leave a field blank to keep its current value.
          </p>
        )}
        {connection.fields.map((field) => (
          <label key={field.key}>
            <span>
              {field.label}
              {!field.required && <em className="optional-tag"> · optional</em>}
            </span>
            <input
              type={field.type === "password" ? "password" : "text"}
              value={values[field.key] ?? ""}
              onChange={(event) =>
                setValues((current) => ({ ...current, [field.key]: event.target.value }))
              }
              placeholder={
                editing
                  ? "Leave blank to keep saved value"
                  : field.placeholder ?? `Paste your ${field.label}`
              }
              autoComplete={field.type === "password" ? "new-password" : "off"}
              spellCheck={false}
            />
            {field.helperText && <small className="field-help">{field.helperText}</small>}
          </label>
        ))}
        {error && <p className="credentials-form-error">{error}</p>}
        <button className="primary-button" type="submit" disabled={!canSubmit}>
          <KeyRound aria-hidden="true" size={16} />
          {submitting ? (editing ? "Updating..." : "Saving...") : editing ? "Update credentials" : "Save credentials"}
        </button>
      </form>
    </div>
  );
}

function InfoBlock({ title, value }: { title: string; value: string }) {
  return (
    <div className="info-block">
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="empty-state">
      <Icon aria-hidden="true" size={22} />
      <strong>{title}</strong>
      {description && <span>{description}</span>}
      {actionLabel && onAction && (
        <button className="ghost-button" type="button" onClick={onAction}>
          {actionLabel}
          <ChevronRight aria-hidden="true" size={16} />
        </button>
      )}
    </div>
  );
}

function MetricTile({
  icon: Icon,
  label,
  value,
  helper,
  tone
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  helper: string;
  tone: "green" | "blue" | "amber" | "rose";
}) {
  return (
    <article className={`metric-tile ${tone}`}>
      <Icon aria-hidden="true" size={22} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{helper}</small>
      </div>
    </article>
  );
}

function PanelHeader({
  eyebrow,
  title,
  actionLabel,
  onAction
}: {
  eyebrow: string;
  title: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="panel-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h3>{title}</h3>
      </div>
      {actionLabel && onAction && (
        <button className="ghost-button" type="button" onClick={onAction}>
          {actionLabel}
          <ChevronRight aria-hidden="true" size={16} />
        </button>
      )}
    </div>
  );
}

function ScreenTitle({
  eyebrow,
  title,
  description
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header className="screen-title">
      <span className="eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      <p>{description}</p>
    </header>
  );
}

function StatusPill({ status }: { status: ConnectionStatus }) {
  return <span className={`status-pill ${status}`}>{status}</span>;
}

function RiskPill({ risk }: { risk: RiskLevel }) {
  return <span className={`risk-pill ${risk}`}>{riskLabels[risk]}</span>;
}

function AuditRows({ auditEvents }: { auditEvents: AuditEvent[] }) {
  return (
    <div className="audit-list">
      {auditEvents.map((event) => (
        <article className="audit-row" key={event.id}>
          <div className="audit-icon">
            {event.actor === "agent" && <Bot aria-hidden="true" size={17} />}
            {event.actor === "user" && <UserRoundCheck aria-hidden="true" size={17} />}
            {event.actor === "system" && <LockKeyhole aria-hidden="true" size={17} />}
          </div>
          <div>
            <strong>{event.event}</strong>
            <span>{event.time} - {event.actor} - {event.tool}</span>
          </div>
          <RiskPill risk={event.risk} />
        </article>
      ))}
    </div>
  );
}
