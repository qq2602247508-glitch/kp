import { useEffect, useMemo, useState, type ReactElement } from "react";

import {
  getDeliveryReadiness,
  listAIProposals,
  listCampaigns,
  listCaseEntries,
  listInvestigators,
} from "./api/client";
import type { Campaign, DeliveryReadiness } from "./api/types";
import { InvestigatorPage } from "./pages/InvestigatorPage";
import { CombatChasePage } from "./pages/CombatChasePage";
import { CaseWorkspacePage } from "./pages/CaseWorkspacePage";
import { RulesPage } from "./pages/RulesPage";
import { SanityInjuryPage } from "./pages/SanityInjuryPage";
import { AIKPPage } from "./pages/AIKPPage";
import { SettingsDeliveryPage } from "./pages/SettingsDeliveryPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import {
  chooseAvailableCampaign,
  selectCampaign,
  subscribeToCampaignSelection,
} from "./state/campaignSelection";

type Workspace =
  | "dashboard"
  | "table"
  | "investigators"
  | "people"
  | "locations"
  | "clues"
  | "sanity"
  | "encounters"
  | "rules"
  | "assistant"
  | "proposals"
  | "audits"
  | "settings";

type NavigationItem = {
  id: Workspace;
  label: string;
  sigil: string;
};

const NAVIGATION: NavigationItem[] = [
  { id: "dashboard", label: "守秘人仪表板", sigil: "◎" },
  { id: "table", label: "跑团推进台", sigil: "⌁" },
  { id: "investigators", label: "调查员", sigil: "◉" },
  { id: "people", label: "人物与存在", sigil: "◇" },
  { id: "locations", label: "地点与场景", sigil: "⌖" },
  { id: "clues", label: "线索网络", sigil: "⌘" },
  { id: "sanity", label: "理智与疯狂", sigil: "◌" },
  { id: "encounters", label: "战斗与追逐", sigil: "↯" },
  { id: "rules", label: "COC7 规则库", sigil: "▤" },
  { id: "assistant", label: "AI KP 助手", sigil: "✦" },
  { id: "proposals", label: "提案中心", sigil: "△" },
  { id: "audits", label: "审计日志", sigil: "≋" },
  { id: "settings", label: "设置与备份", sigil: "⚙" },
];

type DashboardSummary = {
  sessions: number;
  scenes: number;
  clues: number;
  discoveredClues: number;
  investigators: number;
  hiddenTruths: number;
  pendingProposals: number;
};

const EMPTY_SUMMARY: DashboardSummary = {
  sessions: 0,
  scenes: 0,
  clues: 0,
  discoveredClues: 0,
  investigators: 0,
  hiddenTruths: 0,
  pendingProposals: 0,
};

export function App(): ReactElement {
  const [workspace, setWorkspace] = useState<Workspace>("dashboard");
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [readiness, setReadiness] = useState<DeliveryReadiness | null>(null);
  const [summary, setSummary] = useState<DashboardSummary>(EMPTY_SUMMARY);
  const [runtimeError, setRuntimeError] = useState("");
  const active = NAVIGATION.find((item) => item.id === workspace) ?? NAVIGATION[0];
  const campaign = useMemo(
    () => campaigns.find((item) => item.campaign_id === campaignId) ?? null,
    [campaignId, campaigns],
  );

  useEffect(() => {
    const controller = new AbortController();
    const loadShell = (): void => {
      Promise.all([
        listCampaigns(controller.signal),
        getDeliveryReadiness(controller.signal),
      ])
        .then(([nextCampaigns, nextReadiness]) => {
          setCampaigns(nextCampaigns);
          const selected = chooseAvailableCampaign(
            nextCampaigns.map((item) => item.campaign_id),
            campaignId,
          );
          setCampaignId(selected);
          selectCampaign(selected);
          setReadiness(nextReadiness);
          setRuntimeError("");
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) {
            setRuntimeError(
              error instanceof Error ? error.message : "本地服务连接失败",
            );
          }
        });
    };
    loadShell();
    const timer = window.setInterval(loadShell, 30_000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
    // Initial shell discovery is deliberately performed once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(
    () =>
      subscribeToCampaignSelection((nextCampaignId) => {
        setCampaignId((current) =>
          current === nextCampaignId ? current : nextCampaignId,
        );
        void listCampaigns()
          .then(setCampaigns)
          .catch(() => undefined);
      }),
    [],
  );

  useEffect(() => {
    if (!campaignId) {
      setSummary(EMPTY_SUMMARY);
      return;
    }
    const controller = new AbortController();
    Promise.all([
      listCaseEntries(campaignId, "sessions", controller.signal),
      listCaseEntries(campaignId, "scenes", controller.signal),
      listCaseEntries(campaignId, "clues", controller.signal),
      listCaseEntries(campaignId, "people", controller.signal),
      listInvestigators(campaignId, controller.signal),
      listAIProposals(campaignId, controller.signal),
    ])
      .then(([sessions, scenes, clues, people, investigators, proposals]) => {
        setSummary({
          sessions: sessions.length,
          scenes: scenes.length,
          clues: clues.length,
          discoveredClues: clues.filter((item) => item.discovered).length,
          investigators: investigators.length,
          hiddenTruths: [...sessions, ...scenes, ...clues, ...people].filter(
            (item) => item.keeper_truth.trim().length > 0,
          ).length,
          pendingProposals: proposals.filter(
            (item) => item.status === "pending" && !item.is_expired,
          ).length,
        });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setRuntimeError(
            error instanceof Error ? error.message : "案件摘要读取失败",
          );
        }
      });
    return () => controller.abort();
  }, [campaignId, workspace]);

  function changeCampaign(nextCampaignId: string): void {
    setCampaignId(nextCampaignId);
    selectCampaign(nextCampaignId);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            C7
          </span>
          <div>
            <strong>守秘人控制台</strong>
            <small>本地 AI KP 助手</small>
          </div>
        </div>

        <nav aria-label="主导航">
          {NAVIGATION.map((item) => (
            <button
              aria-current={workspace === item.id ? "page" : undefined}
              className={workspace === item.id ? "nav-item active" : "nav-item"}
              key={item.id}
              onClick={() => setWorkspace(item.id)}
              type="button"
            >
              <span aria-hidden="true">{item.sigil}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <p className="authority-note">
          <span>数据只保存在本机</span>
          <span>AI 的变更必须经 KP 确认</span>
        </p>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <span className="eyebrow">CALL OF CTHULHU · SEVENTH EDITION</span>
            <h1>{active.label}</h1>
          </div>
          <div className="topbar-controls">
            <label className="global-case-picker">
              当前案件
              <select
                aria-label="全局当前案件"
                value={campaignId}
                onChange={(event) => changeCampaign(event.target.value)}
              >
                <option value="">未选择</option>
                {campaigns.map((item) => (
                  <option key={item.campaign_id} value={item.campaign_id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
            <div
              className={
                readiness?.ready && !runtimeError
                  ? "runtime connected"
                  : "runtime disconnected"
              }
              title={runtimeError || "数据库、规则索引和本地模型状态"}
            >
              <span className="status-dot" aria-hidden="true" />
              {runtimeError
                ? "本地服务异常"
                : readiness?.ready
                  ? "本地服务已就绪 · 8010"
                  : "正在检查本地服务"}
            </div>
          </div>
        </header>

        {workspace === "dashboard" ? (
          <Dashboard
            campaign={campaign}
            campaigns={campaigns}
            onNavigate={setWorkspace}
            readiness={readiness}
            runtimeError={runtimeError}
            summary={summary}
          />
        ) : null}
        {workspace === "investigators" ? <InvestigatorPage /> : null}
        {workspace === "rules" ? <RulesPage /> : null}
        {workspace === "sanity" ? <SanityInjuryPage /> : null}
        {workspace === "encounters" ? <CombatChasePage /> : null}
        {workspace === "table" ? <CaseWorkspacePage initialKind="sessions" /> : null}
        {workspace === "people" ? <CaseWorkspacePage initialKind="people" /> : null}
        {workspace === "locations" ? <CaseWorkspacePage initialKind="locations" /> : null}
        {workspace === "clues" ? <CaseWorkspacePage initialKind="clues" /> : null}
        {workspace === "assistant" ? <AIKPPage initialView="assistant" /> : null}
        {workspace === "proposals" ? <AIKPPage initialView="proposals" /> : null}
        {workspace === "audits" ? <AuditLogPage /> : null}
        {workspace === "settings" ? <SettingsDeliveryPage /> : null}
        {workspace !== "dashboard" &&
        workspace !== "table" &&
        workspace !== "investigators" &&
        workspace !== "people" &&
        workspace !== "locations" &&
        workspace !== "clues" &&
        workspace !== "sanity" &&
        workspace !== "encounters" &&
        workspace !== "rules" &&
        workspace !== "assistant" &&
        workspace !== "proposals" &&
        workspace !== "audits" &&
        workspace !== "settings" ? (
          <section className="placeholder" aria-live="polite">
            <span className="large-sigil" aria-hidden="true">
              {active.sigil}
            </span>
            <p className="eyebrow">原生 COC7 工作区</p>
            <h2>{active.label}</h2>
            <p>
              领域模型和规则资料正在独立构建。此页面不会加载其他规则体系的数据或默认值。
            </p>
          </section>
        ) : null}
      </main>
    </div>
  );
}

function Dashboard({
  campaign,
  campaigns,
  onNavigate,
  readiness,
  runtimeError,
  summary,
}: {
  campaign: Campaign | null;
  campaigns: Campaign[];
  onNavigate: (workspace: Workspace) => void;
  readiness: DeliveryReadiness | null;
  runtimeError: string;
  summary: DashboardSummary;
}): ReactElement {
  const preparation = [
    {
      title: "规则资料",
      detail: readiness
        ? `${readiness.sources.ready_packs} 个资料包，${readiness.vector_index.chunk_count} 个可检索片段。`
        : "正在读取规则资料与向量索引状态。",
      state: readiness?.ready ? "已就绪" : runtimeError ? "连接失败" : "检查中",
      target: "rules" as Workspace,
    },
    {
      title: "当前案件",
      detail: campaign
        ? `${campaign.era} · ${summary.sessions} 个团次 · ${summary.scenes} 个场景`
        : campaigns.length
          ? "请从顶部选择一个案件。"
          : "尚未建立案件，可前往跑团推进台创建。",
      state: campaign?.title ?? "未选择",
      target: "table" as Workspace,
    },
    {
      title: "调查员",
      detail: campaign
        ? `${summary.investigators} 名调查员；状态与技能均保存在当前案件。`
        : "选择案件后显示调查员状态。",
      state: `${summary.investigators} 人`,
      target: "investigators" as Workspace,
    },
    {
      title: "线索进度",
      detail: `${summary.discoveredClues}/${summary.clues} 条线索已向调查员标记发现。`,
      state: `${summary.clues} 条`,
      target: "clues" as Workspace,
    },
    {
      title: "KP 私密资料",
      detail: "只统计含 KP 真相的记录，不会在玩家视图中展示内容。",
      state: `${summary.hiddenTruths} 条`,
      target: "clues" as Workspace,
    },
    {
      title: "AI 待确认",
      detail: "模型建议只有经 KP 确认后才会写入案件。",
      state: `${summary.pendingProposals} 项`,
      target: "proposals" as Workspace,
    },
  ];

  return (
    <div className="dashboard">
      <section className="opening-card">
        <div>
          <p className="eyebrow">KEEPER'S PRIVATE DESK</p>
          <h2>
            {campaign
              ? `${campaign.title}：守秘档案已展开。`
              : "灯已点亮，等待选择一场调查。"}
          </h2>
          <p>
            {campaign
              ? `这里实时汇总当前调查的团次、线索、隐藏真相和待确认 AI 提案。`
              : "创建或选择调查后，这里会显示真实案件状态，不再使用演示数字。"}
          </p>
          {runtimeError ? (
            <p className="form-error" role="alert">{runtimeError}</p>
          ) : null}
        </div>
        <div className="seal" aria-hidden="true">
          <span>7</span>
          <small>EDITION</small>
        </div>
      </section>

      <section className="preparation-grid" aria-label="准备状态">
        {preparation.map((item) => (
          <button
            aria-label={`dashboard-${item.target}`}
            className="status-card dashboard-link-card"
            key={item.title}
            onClick={() => onNavigate(item.target)}
            type="button"
          >
            <div className="card-heading">
              <h3>{item.title}</h3>
              <span>{item.state}</span>
            </div>
            <p>{item.detail}</p>
          </button>
        ))}
      </section>

      <section className="principles">
        <h3>守秘原则</h3>
        <div>
          <p>
            <strong>证据优先</strong>
            规则答案展示书名、章节与页码；检索不到就明确说明。
          </p>
          <p>
            <strong>秘密分层</strong>
            玩家文本、KP 真相和模型上下文拥有清晰边界。
          </p>
          <p>
            <strong>人工裁决</strong>
            AI 只整理、检索与提议，永远不替 KP 落锤。
          </p>
        </div>
      </section>
    </div>
  );
}
