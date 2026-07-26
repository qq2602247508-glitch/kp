import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactElement,
} from "react";

import {
  createCampaign,
  createCaseEntry,
  deleteCaseEntry,
  listCampaigns,
  listCaseEntries,
  updateCaseEntry,
} from "../api/client";
import type {
  Campaign,
  CaseEntityKind,
  CaseEntry,
  CaseEntryDraft,
} from "../api/types";

const KINDS: Array<{ kind: CaseEntityKind; label: string; createLabel: string }> = [
  { kind: "sessions", label: "团次", createLabel: "新建团次" },
  { kind: "scenes", label: "场景", createLabel: "新建场景" },
  { kind: "people", label: "人物", createLabel: "新建人物" },
  { kind: "locations", label: "地点", createLabel: "新建地点" },
  { kind: "clues", label: "线索", createLabel: "新建线索" },
  { kind: "relationships", label: "线索关联", createLabel: "新建关联" },
  { kind: "handouts", label: "手册资料", createLabel: "新建资料" },
  { kind: "timeline-events", label: "时间线", createLabel: "新建事件" },
];

const EMPTY_DRAFT: CaseEntryDraft = {
  title: "",
  player_visible_text: "",
  keeper_truth: "",
  status: "active",
  time_label: null,
  role: null,
  session_id: null,
  location_id: null,
  scene_id: null,
  person_id: null,
  clue_id: null,
  source_clue_id: null,
  target_clue_id: null,
  relationship_type: null,
  discovered: false,
  revealed: false,
  sort_order: 0,
};

type Props = {
  initialKind: CaseEntityKind;
};

export function CaseWorkspacePage({ initialKind }: Props): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [newCaseTitle, setNewCaseTitle] = useState("未命名案件");
  const [kind, setKind] = useState<CaseEntityKind>(initialKind);
  const [entries, setEntries] = useState<CaseEntry[]>([]);
  const [draft, setDraft] = useState<CaseEntryDraft>(EMPTY_DRAFT);
  const [editing, setEditing] = useState<CaseEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setKind(initialKind);
    setEditing(null);
    setDraft(EMPTY_DRAFT);
  }, [initialKind]);

  useEffect(() => {
    const controller = new AbortController();
    listCampaigns(controller.signal)
      .then((result) => {
        setCampaigns(result);
        setCampaignId((current) => current || result[0]?.campaign_id || "");
      })
      .catch(() => setMessage("尚未连接本地案件库。"));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!campaignId) {
      setEntries([]);
      return;
    }
    const controller = new AbortController();
    listCaseEntries(campaignId, kind, controller.signal)
      .then(setEntries)
      .catch(() => setMessage("无法读取当前案件资料。"));
    return () => controller.abort();
  }, [campaignId, kind]);

  const selectedKind = KINDS.find((item) => item.kind === kind) ?? KINDS[4];
  const references = useMemo(
    () => ({
      sessions: kind === "sessions" ? entries : [],
      clues: kind === "clues" ? entries : [],
    }),
    [entries, kind],
  );

  async function addCase(): Promise<void> {
    if (!newCaseTitle.trim()) return;
    setBusy(true);
    try {
      const created = await createCampaign({
        title: newCaseTitle.trim(),
        ruleset: "coc7e",
        era: "1920s",
        enabled_source_pack_ids: [],
        house_rules: [],
      });
      setCampaigns((current) => [...current, created]);
      setCampaignId(created.campaign_id);
      setMessage("案件已建立。");
    } catch {
      setMessage("案件建立失败，请检查本地服务。");
    } finally {
      setBusy(false);
    }
  }

  function beginNew(): void {
    setEditing(null);
    setDraft({ ...EMPTY_DRAFT, status: kind === "sessions" ? "planned" : "active" });
  }

  function beginEdit(entry: CaseEntry): void {
    setEditing(entry);
    setDraft({
      title: entry.title,
      player_visible_text: entry.player_visible_text,
      keeper_truth: entry.keeper_truth,
      status: entry.status,
      time_label: entry.time_label,
      role: entry.role,
      session_id: entry.session_id,
      location_id: entry.location_id,
      scene_id: entry.scene_id,
      person_id: entry.person_id,
      clue_id: entry.clue_id,
      source_clue_id: entry.source_clue_id,
      target_clue_id: entry.target_clue_id,
      relationship_type: entry.relationship_type,
      discovered: entry.discovered,
      revealed: entry.revealed,
      sort_order: entry.sort_order,
    });
  }

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!campaignId || !draft.title.trim()) return;
    setBusy(true);
    try {
      const saved = editing
        ? await updateCaseEntry(campaignId, kind, editing.entity_id, {
            ...draft,
            title: draft.title.trim(),
            expected_version: editing.version,
          })
        : await createCaseEntry(campaignId, kind, {
            ...draft,
            title: draft.title.trim(),
          });
      setEntries((current) => {
        const others = current.filter((item) => item.entity_id !== saved.entity_id);
        return [...others, saved];
      });
      beginEdit(saved);
      setMessage(editing ? "修改已保存并记录审计。" : "资料已创建并记录审计。");
    } catch {
      setMessage("保存失败；资料可能已在另一处更新，请重新载入。");
    } finally {
      setBusy(false);
    }
  }

  async function remove(): Promise<void> {
    if (!campaignId || !editing) return;
    setBusy(true);
    try {
      await deleteCaseEntry(
        campaignId,
        kind,
        editing.entity_id,
        editing.version,
      );
      setEntries((current) =>
        current.filter((item) => item.entity_id !== editing.entity_id),
      );
      beginNew();
      setMessage("资料已删除，审计记录仍保留。");
    } catch {
      setMessage("删除失败；请重新载入最新版本。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="case-workspace">
      <section className="case-workspace-header">
        <div>
          <p className="eyebrow">KEEPER CASE FILE · CLUE FIRST</p>
          <h2>案件线索网络</h2>
          <p>以线索、人物、地点和时间为骨架；公开叙述与 KP 真相始终分栏保存。</p>
        </div>
        <div className="case-picker">
          <label>
            当前案件
            <select value={campaignId} onChange={(event) => setCampaignId(event.target.value)}>
              <option value="">请选择案件</option>
              {campaigns.map((campaign) => (
                <option key={campaign.campaign_id} value={campaign.campaign_id}>
                  {campaign.title}
                </option>
              ))}
            </select>
          </label>
          <div>
            <input
              aria-label="新案件名称"
              value={newCaseTitle}
              onChange={(event) => setNewCaseTitle(event.target.value)}
            />
            <button disabled={busy} onClick={addCase} type="button">
              建立案件
            </button>
          </div>
        </div>
      </section>

      <nav className="case-tabs" aria-label="案件资料类型">
        {KINDS.map((item) => (
          <button
            className={kind === item.kind ? "active" : ""}
            key={item.kind}
            onClick={() => {
              setKind(item.kind);
              beginNew();
            }}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="case-columns">
        <section className="case-list">
          <div className="case-section-title">
            <div>
              <span>{selectedKind.label}</span>
              <small>{entries.length} 条</small>
            </div>
            <button disabled={!campaignId} onClick={beginNew} type="button">
              {selectedKind.createLabel}
            </button>
          </div>
          {!campaignId ? <p className="case-empty">先选择或建立一个案件。</p> : null}
          {campaignId && entries.length === 0 ? (
            <p className="case-empty">此分栏尚无资料，可以从右侧开始记录。</p>
          ) : null}
          {entries.map((entry) => (
            <button
              className={editing?.entity_id === entry.entity_id ? "case-card selected" : "case-card"}
              key={entry.entity_id}
              onClick={() => beginEdit(entry)}
              type="button"
            >
              <span>{entry.title}</span>
              <small>{entry.status} · v{entry.version}</small>
              <p>{entry.player_visible_text || "尚无玩家可见摘要"}</p>
            </button>
          ))}
        </section>

        <form className="case-editor" onSubmit={save}>
          <div className="case-section-title">
            <div>
              <span>{editing ? `编辑 ${editing.title}` : selectedKind.createLabel}</span>
              <small>{editing ? `乐观锁版本 v${editing.version}` : "新记录"}</small>
            </div>
          </div>
          <label>
            名称
            <input
              required
              value={draft.title}
              onChange={(event) => setDraft({ ...draft, title: event.target.value })}
            />
          </label>
          <div className="visibility-grid">
            <label>
              玩家可见信息
              <textarea
                rows={7}
                value={draft.player_visible_text}
                onChange={(event) =>
                  setDraft({ ...draft, player_visible_text: event.target.value })
                }
              />
            </label>
            <label className="keeper-truth">
              KP 真相
              <textarea
                rows={7}
                value={draft.keeper_truth}
                onChange={(event) =>
                  setDraft({ ...draft, keeper_truth: event.target.value })
                }
              />
            </label>
          </div>
          <div className="case-meta-grid">
            <label>
              状态
              <input
                value={draft.status}
                onChange={(event) => setDraft({ ...draft, status: event.target.value })}
              />
            </label>
            {kind === "people" ? (
              <label>
                身份 / 作用
                <input
                  value={draft.role ?? ""}
                  onChange={(event) => setDraft({ ...draft, role: event.target.value })}
                />
              </label>
            ) : null}
            {kind === "sessions" || kind === "timeline-events" ? (
              <label>
                时间标记
                <input
                  value={draft.time_label ?? ""}
                  onChange={(event) =>
                    setDraft({ ...draft, time_label: event.target.value })
                  }
                />
              </label>
            ) : null}
            {kind === "relationships" ? (
              <>
                <label>
                  起点线索 ID
                  <input
                    list="known-clues"
                    value={draft.source_clue_id ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, source_clue_id: event.target.value })
                    }
                  />
                </label>
                <label>
                  终点线索 ID
                  <input
                    list="known-clues"
                    value={draft.target_clue_id ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, target_clue_id: event.target.value })
                    }
                  />
                </label>
                <label>
                  关联性质
                  <input
                    value={draft.relationship_type ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, relationship_type: event.target.value })
                    }
                  />
                </label>
              </>
            ) : null}
            {kind === "clues" || kind === "handouts" ? (
              <label className="case-check">
                <input
                  checked={kind === "clues" ? draft.discovered : draft.revealed}
                  onChange={(event) =>
                    setDraft(
                      kind === "clues"
                        ? { ...draft, discovered: event.target.checked }
                        : { ...draft, revealed: event.target.checked },
                    )
                  }
                  type="checkbox"
                />
                {kind === "clues" ? "已被调查员发现" : "已向玩家公开"}
              </label>
            ) : null}
          </div>
          <datalist id="known-clues">
            {references.clues.map((entry) => (
              <option key={entry.entity_id} value={entry.entity_id}>{entry.title}</option>
            ))}
          </datalist>
          <div className="case-actions">
            <button disabled={busy || !campaignId} type="submit">保存</button>
            {editing ? (
              <button className="danger" disabled={busy} onClick={remove} type="button">
                删除
              </button>
            ) : null}
            <span role="status">{message}</span>
          </div>
        </form>
      </div>
    </div>
  );
}
