import { useState, type ReactElement } from "react";

import { InvestigatorPage } from "./pages/InvestigatorPage";
import { CaseWorkspacePage } from "./pages/CaseWorkspacePage";
import { RulesPage } from "./pages/RulesPage";

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
  { id: "settings", label: "设置与备份", sigil: "⚙" },
];

const PREPARATION = [
  {
    title: "规则资料",
    detail: "等待导入核心规则、调查员资料与已启用扩展。",
    state: "未索引",
  },
  {
    title: "当前模组",
    detail: "尚未创建战役。剧本内容将区分玩家可见信息与 KP 真相。",
    state: "未选择",
  },
  {
    title: "调查员",
    detail: "属性、技能、幸运、理智与背景故事将使用 COC7 原生结构。",
    state: "0 人",
  },
];

export function App(): ReactElement {
  const [workspace, setWorkspace] = useState<Workspace>("dashboard");
  const active = NAVIGATION.find((item) => item.id === workspace) ?? NAVIGATION[0];

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
          <div className="runtime">
            <span className="status-dot" aria-hidden="true" />
            本地服务待连接 · 8010
          </div>
        </header>

        {workspace === "dashboard" ? <Dashboard /> : null}
        {workspace === "investigators" ? <InvestigatorPage /> : null}
        {workspace === "rules" ? <RulesPage /> : null}
        {workspace === "table" ? <CaseWorkspacePage initialKind="sessions" /> : null}
        {workspace === "people" ? <CaseWorkspacePage initialKind="people" /> : null}
        {workspace === "locations" ? <CaseWorkspacePage initialKind="locations" /> : null}
        {workspace === "clues" ? <CaseWorkspacePage initialKind="clues" /> : null}
        {workspace !== "dashboard" &&
        workspace !== "table" &&
        workspace !== "investigators" &&
        workspace !== "people" &&
        workspace !== "locations" &&
        workspace !== "clues" &&
        workspace !== "rules" ? (
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

function Dashboard(): ReactElement {
  return (
    <div className="dashboard">
      <section className="opening-card">
        <div>
          <p className="eyebrow">KEEPER'S PRIVATE DESK</p>
          <h2>灯已点亮，档案柜仍是空的。</h2>
          <p>
            创建一场调查后，这里会汇总当前场景、公开线索、隐藏真相、理智变化和待确认的
            AI 提案。
          </p>
        </div>
        <div className="seal" aria-hidden="true">
          <span>7</span>
          <small>EDITION</small>
        </div>
      </section>

      <section className="preparation-grid" aria-label="准备状态">
        {PREPARATION.map((item) => (
          <article className="status-card" key={item.title}>
            <div className="card-heading">
              <h3>{item.title}</h3>
              <span>{item.state}</span>
            </div>
            <p>{item.detail}</p>
          </article>
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
