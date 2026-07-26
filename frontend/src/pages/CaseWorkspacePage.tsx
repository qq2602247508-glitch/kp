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
  getPlayerCaseEntry,
  listCampaigns,
  listCaseEntries,
  updateCaseEntry,
} from "../api/client";
import type {
  Campaign,
  CaseEntityKind,
  CaseEntry,
  CaseEntryDraft,
  PlayerCaseEntry,
} from "../api/types";
import {
  chooseAvailableCampaign,
  selectCampaign,
  subscribeToCampaignSelection,
} from "../state/campaignSelection";

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

type CaseEntryCache = Record<CaseEntityKind, CaseEntry[]>;

function emptyCache(): CaseEntryCache {
  return {
    sessions: [],
    scenes: [],
    people: [],
    locations: [],
    clues: [],
    relationships: [],
    handouts: [],
    "timeline-events": [],
  };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function payloadForKind(
  kind: CaseEntityKind,
  draft: CaseEntryDraft,
): CaseEntryDraft {
  const common = {
    title: draft.title.trim(),
    player_visible_text: draft.player_visible_text,
    keeper_truth: draft.keeper_truth,
    status: draft.status,
  };
  switch (kind) {
    case "sessions":
      return { ...common, time_label: draft.time_label };
    case "people":
      return { ...common, role: draft.role };
    case "locations":
      return common;
    case "scenes":
      return {
        ...common,
        session_id: draft.session_id,
        location_id: draft.location_id,
      };
    case "clues":
      return {
        ...common,
        scene_id: draft.scene_id,
        person_id: draft.person_id,
        location_id: draft.location_id,
        discovered: draft.discovered,
      };
    case "relationships":
      return {
        ...common,
        source_clue_id: draft.source_clue_id,
        target_clue_id: draft.target_clue_id,
        relationship_type: draft.relationship_type,
      };
    case "handouts":
      return { ...common, clue_id: draft.clue_id, revealed: draft.revealed };
    case "timeline-events":
      return {
        ...common,
        session_id: draft.session_id,
        scene_id: draft.scene_id,
        time_label: draft.time_label,
        sort_order: draft.sort_order,
      };
  }
}

export function CaseWorkspacePage({ initialKind }: Props): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [newCaseTitle, setNewCaseTitle] = useState("未命名案件");
  const [kind, setKind] = useState<CaseEntityKind>(initialKind);
  const [entryCache, setEntryCache] = useState<CaseEntryCache>(emptyCache);
  const [draft, setDraft] = useState<CaseEntryDraft>(EMPTY_DRAFT);
  const [editing, setEditing] = useState<CaseEntry | null>(null);
  const [playerPreview, setPlayerPreview] = useState<PlayerCaseEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [activeSceneId, setActiveSceneId] = useState("");
  const [sceneHint, setSceneHint] = useState("");

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
        const selected = chooseAvailableCampaign(
          result.map((campaign) => campaign.campaign_id),
          "",
        );
        setCampaignId(selected);
        selectCampaign(selected);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(errorMessage(error, "尚未连接本地案件库。"));
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(
    () =>
      subscribeToCampaignSelection((nextCampaignId) => {
        setCampaignId((current) =>
          current === nextCampaignId ? current : nextCampaignId,
        );
        setEditing(null);
        setPlayerPreview(null);
      }),
    [],
  );

  useEffect(() => {
    if (!campaignId) {
      setEntryCache(emptyCache());
      return;
    }
    setEntryCache(emptyCache());
    const controller = new AbortController();
    Promise.all(
      KINDS.map(async ({ kind: requestedKind }) => [
        requestedKind,
        await listCaseEntries(campaignId, requestedKind, controller.signal),
      ] as const),
    )
      .then((results) => {
        setEntryCache(
          Object.fromEntries(results) as CaseEntryCache,
        );
        setMessage("");
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(errorMessage(error, "无法读取当前案件资料。"));
        }
      });
    return () => controller.abort();
  }, [campaignId]);

  const sceneEntries = useMemo(
    () => [...entryCache.scenes].sort((a, b) => a.sort_order - b.sort_order),
    [entryCache.scenes],
  );
  const activeScene = sceneEntries.find((scene) => scene.entity_id === activeSceneId)
    ?? sceneEntries.find((scene) => scene.status === "current")
    ?? sceneEntries[0];

  useEffect(() => {
    if (!activeScene) {
      setActiveSceneId("");
      return;
    }
    setActiveSceneId((current) =>
      sceneEntries.some((scene) => scene.entity_id === current)
        ? current
        : activeScene.entity_id,
    );
  }, [activeScene, sceneEntries]);

  useEffect(() => {
    if (!campaignId || !editing) {
      setPlayerPreview(null);
      return;
    }
    const controller = new AbortController();
    setPlayerPreview(null);
    getPlayerCaseEntry(
      campaignId,
      editing.kind,
      editing.entity_id,
      controller.signal,
    )
      .then(setPlayerPreview)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(errorMessage(error, "无法读取玩家视图。"));
        }
      });
    return () => controller.abort();
  }, [campaignId, editing]);

  const selectedKind = KINDS.find((item) => item.kind === kind) ?? KINDS[4];
  const entries = entryCache[kind];
  const references = useMemo(() => entryCache, [entryCache]);

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
      selectCampaign(created.campaign_id);
      setMessage("案件已建立。");
    } catch (error: unknown) {
      setMessage(errorMessage(error, "案件建立失败，请检查本地服务。"));
    } finally {
      setBusy(false);
    }
  }

  function beginNew(): void {
    setEditing(null);
    setPlayerPreview(null);
    setDraft({ ...EMPTY_DRAFT, status: kind === "sessions" ? "planned" : "active" });
  }

  function beginEdit(entry: CaseEntry): void {
    setEditing(entry);
    setPlayerPreview(null);
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
      const payload = payloadForKind(kind, draft);
      const saved = editing
        ? await updateCaseEntry(campaignId, kind, editing.entity_id, {
            ...payload,
            expected_version: editing.version,
          })
        : await createCaseEntry(campaignId, kind, payload);
      setEntryCache((current) => {
        const others = current[kind].filter(
          (item) => item.entity_id !== saved.entity_id,
        );
        return { ...current, [kind]: [...others, saved] };
      });
      beginEdit(saved);
      setMessage(editing ? "修改已保存并记录审计。" : "资料已创建并记录审计。");
    } catch (error: unknown) {
      setMessage(errorMessage(error, "保存失败；请重新载入。"));
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
      setEntryCache((current) => ({
        ...current,
        [kind]: current[kind].filter(
          (item) => item.entity_id !== editing.entity_id,
        ),
      }));
      beginNew();
      setMessage("资料已删除，审计记录仍保留。");
    } catch (error: unknown) {
      setMessage(errorMessage(error, "删除失败；请重新载入最新版本。"));
    } finally {
      setBusy(false);
    }
  }

  async function moveScene(scene: CaseEntry, status: "current" | "completed"): Promise<void> {
    setBusy(true);
    try {
      // Scene status is the durable, campaign-scoped progression marker. Clear
      // the previous current scene first, then promote the selected scene.
      const current = sceneEntries.find((item) => item.status === "current");
      if (current && current.entity_id !== scene.entity_id) {
        const cleared = await updateCaseEntry(campaignId, "scenes", current.entity_id, {
          title: current.title,
          player_visible_text: current.player_visible_text,
          keeper_truth: current.keeper_truth,
          status: "planned",
          session_id: current.session_id,
          location_id: current.location_id,
          expected_version: current.version,
        });
        setEntryCache((cache) => ({
          ...cache,
          scenes: cache.scenes.map((item) => item.entity_id === cleared.entity_id ? cleared : item),
        }));
      }
      const updated = await updateCaseEntry(campaignId, "scenes", scene.entity_id, {
        title: scene.title,
        player_visible_text: scene.player_visible_text,
        keeper_truth: scene.keeper_truth,
        status,
        session_id: scene.session_id,
        location_id: scene.location_id,
        expected_version: scene.version,
      });
      setEntryCache((cache) => ({
        ...cache,
        scenes: cache.scenes.map((item) => item.entity_id === updated.entity_id ? updated : item),
      }));
      setActiveSceneId(updated.entity_id);
      setMessage(status === "current" ? `已进入场景：${updated.title}` : `已完成场景：${updated.title}`);
    } catch (error: unknown) {
      setMessage(errorMessage(error, "场景转场失败；请重新载入最新版本。"));
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
            <select
              value={campaignId}
              onChange={(event) => {
                setCampaignId(event.target.value);
                selectCampaign(event.target.value);
                beginNew();
              }}
            >
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

      {(kind === "sessions" || kind === "scenes") && campaignId ? (
        <section className="scene-progression" aria-label="章节与场景推进台">
          <div className="scene-progression-heading">
            <div>
              <p className="eyebrow">CHAPTER / SCENE FLOW · COC7</p>
              <h3>章节推进</h3>
              <p>把场景按顺序编排；当前场景只保留一个，转场由 KP 明确确认。</p>
            </div>
            <label className="field">
              <span>当前场景</span>
              <select
                aria-label="当前场景"
                value={activeScene?.entity_id ?? ""}
                onChange={(event) => {
                  const next = sceneEntries.find((item) => item.entity_id === event.target.value);
                  if (next) void moveScene(next, "current");
                }}
              >
                <option value="">尚未编排场景</option>
                {sceneEntries.map((scene, index) => (
                  <option key={scene.entity_id} value={scene.entity_id}>
                    {index + 1}. {scene.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="scene-progression-body">
            <div className="scene-outline">
              {sceneEntries.length === 0 ? <p className="case-empty">先在“场景”分栏创建 Scene 1。</p> : null}
              {sceneEntries.map((scene, index) => (
                <article className={`scene-outline-item ${scene.entity_id === activeScene?.entity_id ? "current" : ""}`} key={scene.entity_id}>
                  <div className="scene-outline-index">{index + 1}</div>
                  <div>
                    <strong>{scene.title}</strong>
                    <small>{scene.status === "current" ? "进行中" : scene.status === "completed" ? "已完成" : "待推进"}</small>
                  </div>
                  <div className="scene-outline-actions">
                    {scene.status !== "current" ? <button disabled={busy} onClick={() => void moveScene(scene, "current")} type="button">进入</button> : null}
                    {scene.status === "current" ? <button className="secondary-button" disabled={busy} onClick={() => void moveScene(scene, "completed")} type="button">完成</button> : null}
                  </div>
                </article>
              ))}
            </div>
            <div className="scene-live-context">
              <span className="eyebrow">KP LIVE CONTEXT</span>
              <h4>{activeScene?.title ?? "等待场景"}</h4>
              <p>{activeScene?.player_visible_text || "补充本幕玩家可见叙述，作为推进台的当前场景背景。"}</p>
              <label>
                KP 推进记录 / AI 建议
                <textarea rows={3} value={sceneHint} onChange={(event) => setSceneHint(event.target.value)} placeholder="记录玩家行为，或粘贴 AI 提示后再决定是否转场。" />
              </label>
              <small>KP 真相仅在编辑器和 AI KP 私密上下文中可见，不会进入玩家投影。</small>
            </div>
          </div>
        </section>
      ) : null}

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
          {editing ? (
            <section
              aria-label="玩家视图预览"
              className="player-view-preview"
              role="region"
            >
              <div className="case-section-title">
                <div>
                  <span>玩家视图预览</span>
                  <small>来自只读玩家投影 API</small>
                </div>
              </div>
              {playerPreview ? (
                <>
                  <strong>{playerPreview.title}</strong>
                  <p>{playerPreview.player_visible_text || "暂无玩家可见信息"}</p>
                  <small>
                    {playerPreview.status}
                    {playerPreview.time_label ? ` · ${playerPreview.time_label}` : ""}
                    {playerPreview.role ? ` · ${playerPreview.role}` : ""}
                  </small>
                </>
              ) : (
                <p>正在读取玩家视图……</p>
              )}
            </section>
          ) : null}
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
            {kind === "scenes" ? (
              <>
                <label>
                  所属团次
                  <select
                    value={draft.session_id ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, session_id: event.target.value || null })
                    }
                  >
                    <option value="">未指定</option>
                    {references.sessions.map((entry) => (
                      <option key={entry.entity_id} value={entry.entity_id}>
                        {entry.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  发生地点
                  <select
                    value={draft.location_id ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, location_id: event.target.value || null })
                    }
                  >
                    <option value="">未指定</option>
                    {references.locations.map((entry) => (
                      <option key={entry.entity_id} value={entry.entity_id}>
                        {entry.title}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : null}
            {kind === "clues" ? (
              <>
                <label>
                  所属场景
                  <select
                    value={draft.scene_id ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, scene_id: event.target.value || null })
                    }
                  >
                    <option value="">未指定</option>
                    {references.scenes.map((entry) => (
                      <option key={entry.entity_id} value={entry.entity_id}>
                        {entry.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  相关人物
                  <select
                    value={draft.person_id ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, person_id: event.target.value || null })
                    }
                  >
                    <option value="">未指定</option>
                    {references.people.map((entry) => (
                      <option key={entry.entity_id} value={entry.entity_id}>
                        {entry.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  相关地点
                  <select
                    value={draft.location_id ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, location_id: event.target.value || null })
                    }
                  >
                    <option value="">未指定</option>
                    {references.locations.map((entry) => (
                      <option key={entry.entity_id} value={entry.entity_id}>
                        {entry.title}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : null}
            {kind === "relationships" ? (
              <>
                <label>
                  起点线索
                  <select
                    required
                    value={draft.source_clue_id ?? ""}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        source_clue_id: event.target.value || null,
                      })
                    }
                  >
                    <option value="">请选择线索</option>
                    {references.clues.map((entry) => (
                      <option key={entry.entity_id} value={entry.entity_id}>
                        {entry.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  终点线索
                  <select
                    required
                    value={draft.target_clue_id ?? ""}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        target_clue_id: event.target.value || null,
                      })
                    }
                  >
                    <option value="">请选择线索</option>
                    {references.clues.map((entry) => (
                      <option key={entry.entity_id} value={entry.entity_id}>
                        {entry.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  关联性质
                  <input
                    required
                    value={draft.relationship_type ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, relationship_type: event.target.value })
                    }
                  />
                </label>
              </>
            ) : null}
            {kind === "handouts" ? (
              <label>
                关联线索
                <select
                  value={draft.clue_id ?? ""}
                  onChange={(event) =>
                    setDraft({ ...draft, clue_id: event.target.value || null })
                  }
                >
                  <option value="">未指定</option>
                  {references.clues.map((entry) => (
                    <option key={entry.entity_id} value={entry.entity_id}>
                      {entry.title}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {kind === "timeline-events" ? (
              <>
                <label>
                  所属团次
                  <select
                    value={draft.session_id ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, session_id: event.target.value || null })
                    }
                  >
                    <option value="">未指定</option>
                    {references.sessions.map((entry) => (
                      <option key={entry.entity_id} value={entry.entity_id}>
                        {entry.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  所属场景
                  <select
                    value={draft.scene_id ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, scene_id: event.target.value || null })
                    }
                  >
                    <option value="">未指定</option>
                    {references.scenes.map((entry) => (
                      <option key={entry.entity_id} value={entry.entity_id}>
                        {entry.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  排序
                  <input
                    type="number"
                    value={draft.sort_order ?? 0}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        sort_order: Number.parseInt(event.target.value, 10) || 0,
                      })
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
