import { useCallback, useEffect, useMemo, useState, type ReactElement } from "react";

import {
  ApiError,
  applySkillImprovement,
  createCampaign,
  createInvestigator,
  listCampaigns,
  listInvestigators,
  resolveRoll,
  updateInvestigator,
} from "../api/client";
import type {
  Campaign,
  Characteristics,
  Investigator,
  InvestigatorBackstory,
  InvestigatorCondition,
  InvestigatorProfile,
  RollDifficulty,
  RollResult,
  SkillEntry,
} from "../api/types";
import {
  chooseAvailableCampaign,
  selectCampaign,
  subscribeToCampaignSelection,
} from "../state/campaignSelection";

const CHARACTERISTICS: {
  key: keyof Characteristics;
  short: string;
  label: string;
}[] = [
  { key: "strength", short: "STR", label: "力量" },
  { key: "constitution", short: "CON", label: "体质" },
  { key: "size", short: "SIZ", label: "体型" },
  { key: "dexterity", short: "DEX", label: "敏捷" },
  { key: "appearance", short: "APP", label: "外貌" },
  { key: "intelligence", short: "INT", label: "智力" },
  { key: "power", short: "POW", label: "意志" },
  { key: "education", short: "EDU", label: "教育" },
];

const BACKSTORY_FIELDS: {
  key: keyof InvestigatorBackstory;
  label: string;
}[] = [
  { key: "personal_description", label: "形象描述" },
  { key: "ideology_and_beliefs", label: "思想与信念" },
  { key: "significant_people", label: "重要之人" },
  { key: "meaningful_locations", label: "意义非凡之地" },
  { key: "treasured_possessions", label: "宝贵之物" },
  { key: "traits", label: "特质" },
  { key: "injuries_and_scars", label: "伤口和疤痕" },
  { key: "phobias_and_manias", label: "恐惧症和躁狂症" },
  { key: "mythos_tomes_spells_artifacts", label: "神话典籍、法术和魔法物品" },
  { key: "strange_encounters", label: "第三类接触" },
];

const CONDITION_LABELS: Record<InvestigatorCondition, string> = {
  major_wound: "重伤",
  unconscious: "昏迷",
  dying: "濒死",
  stabilized: "已稳定",
  dead: "死亡",
  bout_of_madness: "疯狂发作",
  temporary_insanity: "临时疯狂",
  indefinite_insanity: "不定性疯狂",
};

const COMMON_SKILLS: SkillEntry[] = [
  skill("accounting", "会计", 5),
  skill("anthropology", "人类学", 1),
  skill("archaeology", "考古学", 1),
  skill("charm", "魅惑", 15),
  skill("climb", "攀爬", 20),
  skill("dodge", "闪避", 25),
  skill("first_aid", "急救", 30),
  skill("history", "历史", 5),
  skill("intimidate", "恐吓", 15),
  skill("library_use", "图书馆使用", 20),
  skill("listen", "聆听", 20),
  skill("medicine", "医学", 1),
  skill("occult", "神秘学", 5),
  skill("persuade", "说服", 10),
  skill("psychology", "心理学", 10),
  skill("spot_hidden", "侦查", 25),
  skill("stealth", "潜行", 20),
];

const OCCUPATION_PRESETS = [
  "古董商",
  "艺术家",
  "运动员",
  "作家",
  "神职人员",
  "罪犯",
  "私家侦探",
  "医生",
  "流浪者",
  "工程师",
  "艺人",
  "农民",
  "记者",
  "律师",
  "图书管理员",
  "军官",
  "传教士",
  "音乐家",
  "护士",
  "警探",
  "警察",
  "教授",
  "士兵",
  "部落成员",
  "狂热者",
] as const;

/** Short, COC7-native reminders shown on hover; the rule engine remains authoritative. */
const SKILL_DESCRIPTIONS: Record<string, string> = {
  accounting: "评估财务状况、追查账目或发现资金异常。通常进行 INT/5 或技能百分骰。",
  anthropology: "理解人类文化、习俗与社会结构，辨认陌生群体的行为模式。",
  archaeology: "识别古代遗迹、器物与文字，判断年代和用途。",
  charm: "以魅力、礼貌或社交手段影响他人；抵抗时由 KP 设定对抗技能。",
  climb: "攀登、抓握和安全下降；失败可能造成坠落或伤势。",
  dodge: "躲避远程攻击、近战或环境危险；战斗中按 COC7 对抗规则处理。",
  first_aid: "处理创伤并稳定伤者；每名伤者通常只能从急救中获益一次。",
  history: "回忆历史人物、事件、地点和资料背景。",
  intimidate: "以威胁或强势姿态迫使目标让步，也可用于对抗意志。",
  library_use: "在档案、图书馆或数据库中高效检索线索。",
  listen: "察觉细微声音、脚步、谈话或异常动静。",
  medicine: "诊断疾病、处理复杂创伤并提供专业医疗。",
  occult: "辨认神秘传统、仪式与传说；不等于自动理解克苏鲁神话。",
  persuade: "用逻辑、谈判或真诚说服目标；效果取决于诉求与情境。",
  psychology: "判断情绪、动机和心理状态，识别异常或不自然的行为。",
  spot_hidden: "发现隐藏的门、物品、痕迹或环境异常。",
  stealth: "无声移动、隐藏身形和避开注意；受环境与对方侦查影响。",
};

function skill(skillKey: string, displayName: string, baseValue: number): SkillEntry {
  return {
    skill_key: skillKey,
    display_name: displayName,
    specialization: null,
    base_value: baseValue,
    current_value: baseValue,
    improvement_mark: false,
    source_pack_id: null,
  };
}

function emptyBackstory(): InvestigatorBackstory {
  return {
    personal_description: [],
    ideology_and_beliefs: [],
    significant_people: [],
    meaningful_locations: [],
    treasured_possessions: [],
    traits: [],
    injuries_and_scars: [],
    phobias_and_manias: [],
    mythos_tomes_spells_artifacts: [],
    strange_encounters: [],
  };
}

function emptyProfile(): InvestigatorProfile {
  return {
    name: "",
    player_name: null,
    occupation: "",
    age: 25,
    gender: null,
    residence: null,
    birthplace: null,
    era: "1920s",
    characteristics: {
      strength: 50,
      constitution: 50,
      size: 50,
      dexterity: 50,
      appearance: 50,
      intelligence: 50,
      power: 50,
      education: 50,
    },
    luck: 50,
    move_rate: 8,
    damage_bonus: "0",
    build: 0,
    credit_rating: 0,
    spending_level: null,
    cash: null,
    assets: null,
    skills: COMMON_SKILLS.map((entry) => ({ ...entry })),
    backstory: emptyBackstory(),
  };
}

type EditorState = {
  profile: InvestigatorProfile;
  hit_points: number;
  magic_points: number;
  sanity: number;
  mythos: number;
  conditions: InvestigatorCondition[];
  investigator_id: string | null;
  version: number | null;
};

function createEditor(investigator?: Investigator): EditorState {
  if (investigator) {
    return {
      profile: structuredClone(investigator.profile),
      hit_points: investigator.hit_points,
      magic_points: investigator.magic_points,
      sanity: investigator.sanity,
      mythos: investigator.mythos,
      conditions: [...investigator.conditions],
      investigator_id: investigator.investigator_id,
      version: investigator.version,
    };
  }
  const profile = emptyProfile();
  return {
    profile,
    hit_points: maximumHitPoints(profile.characteristics),
    magic_points: Math.floor(profile.characteristics.power / 5),
    sanity: profile.characteristics.power,
    mythos: 0,
    conditions: [],
    investigator_id: null,
    version: null,
  };
}

function maximumHitPoints(characteristics: Characteristics): number {
  return Math.floor((characteristics.constitution + characteristics.size) / 10);
}

function nullable(value: string): string | null {
  const clean = value.trim();
  return clean ? clean : null;
}

function lines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return `本地 API 返回 ${error.status}：${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "发生未知错误";
}

export function InvestigatorPage(): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [campaignTitle, setCampaignTitle] = useState("未命名调查");
  const [investigators, setInvestigators] = useState<Investigator[]>([]);
  const [editor, setEditor] = useState<EditorState>(() => createEditor());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [growthSkillKey, setGrowthSkillKey] = useState("");
  const [growthRoll, setGrowthRoll] = useState(100);
  const [growthIncrease, setGrowthIncrease] = useState(1);
  const [view, setView] = useState<"list" | "editor">("list");

  const loadCampaigns = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setFailure(null);
    try {
      const result = await listCampaigns(signal);
      setCampaigns(result);
      const selected = chooseAvailableCampaign(
        result.map((campaign) => campaign.campaign_id),
        "",
      );
      setCampaignId(selected);
      selectCampaign(selected);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setFailure(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadCampaigns(controller.signal);
    return () => controller.abort();
  }, [loadCampaigns]);

  useEffect(
    () =>
      subscribeToCampaignSelection((nextCampaignId) => {
        setCampaignId((current) =>
          current === nextCampaignId ? current : nextCampaignId,
        );
      }),
    [],
  );

  useEffect(() => {
    if (!campaignId) {
      setInvestigators([]);
      setEditor(createEditor());
      setView("list");
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    listInvestigators(campaignId, controller.signal)
      .then((result) => {
        setInvestigators(result);
        setEditor((current) => {
          const selected = result.find((item) => item.investigator_id === current.investigator_id);
          return selected ? createEditor(selected) : createEditor();
        });
        setView("list");
        setFailure(null);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailure(errorMessage(error));
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [campaignId]);

  async function handleCreateCampaign(): Promise<void> {
    if (!campaignTitle.trim()) {
      setFailure("调查名称不能为空。");
      return;
    }
    setSaving(true);
    setFailure(null);
    try {
      const created = await createCampaign({
        title: campaignTitle.trim(),
        ruleset: "coc7e",
        era: "1920s",
        enabled_source_pack_ids: [],
        house_rules: [],
      });
      setCampaigns((items) => [...items, created]);
      setCampaignId(created.campaign_id);
      selectCampaign(created.campaign_id);
      setNotice("调查已创建。");
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function handleSave(): Promise<void> {
    if (!campaignId) {
      setFailure("请先创建或选择调查。");
      return;
    }
    if (!editor.profile.name.trim() || !editor.profile.occupation.trim()) {
      setFailure("姓名和职业不能为空。");
      return;
    }
    setSaving(true);
    setFailure(null);
    setNotice(null);
    try {
      let saved: Investigator;
      if (editor.investigator_id && editor.version) {
        saved = await updateInvestigator(campaignId, editor.investigator_id, {
          ...editor.profile,
          hit_points: editor.hit_points,
          magic_points: editor.magic_points,
          sanity: editor.sanity,
          mythos: editor.mythos,
          conditions: editor.conditions,
          expected_version: editor.version,
        });
      } else {
        saved = await createInvestigator(campaignId, editor.profile);
      }
      setInvestigators((items) => {
        const index = items.findIndex(
          (item) => item.investigator_id === saved.investigator_id,
        );
        if (index < 0) {
          return [...items, saved];
        }
        return items.map((item, itemIndex) => (itemIndex === index ? saved : item));
      });
      setEditor(createEditor(saved));
      setView("editor");
      setNotice(editor.investigator_id ? "调查员已更新。" : "调查员已创建。");
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function handleSkillImprovement(): Promise<void> {
    if (!campaignId || !editor.investigator_id || !editor.version || !growthSkillKey) {
      setFailure("请先保存调查员，并选择一项带成长标记的技能。");
      return;
    }
    const selectedSkill = editor.profile.skills.find((item) => item.skill_key === growthSkillKey);
    if (!selectedSkill?.improvement_mark) {
      setFailure("只有带成长标记的技能可以进行幕间改善检定。");
      return;
    }
    const improved = growthRoll > selectedSkill.current_value || growthRoll > 95;
    setSaving(true);
    setFailure(null);
    try {
      const result = await applySkillImprovement(campaignId, editor.investigator_id, {
        expected_version: editor.version,
        skill_key: selectedSkill.skill_key,
        specialization: selectedSkill.specialization ?? undefined,
        improvement_roll: growthRoll,
        increase_roll: improved ? growthIncrease : undefined,
      });
      const saved = result.investigator;
      setInvestigators((items) => items.map((item) => item.investigator_id === saved.investigator_id ? saved : item));
      setEditor(createEditor(saved));
      setGrowthSkillKey("");
      setNotice(result.improved
        ? `${result.skill_name}改善成功：${result.previous_skill_value} → ${result.current_skill_value}。`
        : `${result.skill_name}本次未改善；成长标记已清除。`);
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  function patchProfile(patch: Partial<InvestigatorProfile>): void {
    setEditor((current) => ({
      ...current,
      profile: { ...current.profile, ...patch },
    }));
  }

  function patchCharacteristic(key: keyof Characteristics, value: number): void {
    setEditor((current) => {
      const characteristics = {
        ...current.profile.characteristics,
        [key]: value,
      };
      const next = {
        ...current,
        profile: { ...current.profile, characteristics },
      };
      if (!current.investigator_id) {
        next.hit_points = maximumHitPoints(characteristics);
        next.magic_points = Math.floor(characteristics.power / 5);
        next.sanity = characteristics.power;
      }
      return next;
    });
  }

  const selectedCampaign = campaigns.find(
    (campaign) => campaign.campaign_id === campaignId,
  );

  return (
    <div className="investigator-workspace">
      <section className="workspace-toolbar">
        <div>
          <p className="eyebrow">INVESTIGATOR RECORD</p>
          <h2>COC7 调查员角色卡</h2>
        </div>
        <div className="toolbar-controls">
          <label>
            当前调查
            <select
              aria-label="当前调查"
              onChange={(event) => {
                setCampaignId(event.target.value);
                selectCampaign(event.target.value);
              }}
              value={campaignId}
            >
              <option value="">未选择</option>
              {campaigns.map((campaign) => (
                <option key={campaign.campaign_id} value={campaign.campaign_id}>
                  {campaign.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            当前界面
            <span className="toolbar-view-label">{view === "list" ? "调查员列表" : editor.investigator_id ? "调查员详情" : "创建调查员"}</span>
          </label>
          {view === "editor" ? (
            <button className="secondary-button" onClick={() => setView("list")} type="button">
              返回列表
            </button>
          ) : (
            <button onClick={() => { setEditor(createEditor()); setView("editor"); }} type="button">
              创建调查员
            </button>
          )}
        </div>
      </section>

      {!campaignId && !loading ? (
        <section className="empty-campaign">
          <span aria-hidden="true">⌘</span>
          <h3>先建立一场调查</h3>
          <p>调查员必须归属于一场独立调查，所有检定也会进入该调查的审计记录。</p>
          <div>
            <input
              aria-label="调查名称"
              onChange={(event) => setCampaignTitle(event.target.value)}
              value={campaignTitle}
            />
            <button disabled={saving} onClick={() => void handleCreateCampaign()}>
              创建调查
            </button>
          </div>
        </section>
      ) : null}

      {failure ? <div className="message error-message">{failure}</div> : null}
      {notice ? <div className="message success-message">{notice}</div> : null}

      {campaignId && view === "list" ? (
        <section className="investigator-directory" aria-label="调查员列表">
          <header>
            <div>
              <p className="eyebrow">INVESTIGATOR ROSTER</p>
              <h3>调查员列表</h3>
              <p>外层只展示跑团时常用状态；点击卡片进入完整角色卡。</p>
            </div>
            <button onClick={() => { setEditor(createEditor()); setView("editor"); }} type="button">＋ 创建调查员</button>
          </header>
          {investigators.length === 0 ? (
            <div className="investigator-directory-empty">
              <strong>当前调查还没有调查员</strong>
              <span>点击“创建调查员”进入独立的完整车卡界面。</span>
            </div>
          ) : (
            <div className="investigator-card-grid">
              {investigators.map((investigator) => (
                <button
                  className="investigator-directory-card"
                  key={investigator.investigator_id}
                  onClick={() => { setEditor(createEditor(investigator)); setView("editor"); }}
                  type="button"
                >
                  <span>
                    <strong>{investigator.profile.name}</strong>
                    <small>{investigator.profile.occupation} · {investigator.profile.player_name || "未填写玩家"}</small>
                  </span>
                  <span className="directory-stats">
                    <b>HP {investigator.hit_points}/{maximumHitPoints(investigator.profile.characteristics)}</b>
                    <b>SAN {investigator.sanity}</b>
                    <b>MP {investigator.magic_points}</b>
                    <b>MOV {investigator.profile.move_rate}</b>
                  </span>
                  <small>{investigator.conditions.length ? investigator.conditions.map((item) => CONDITION_LABELS[item]).join(" · ") : "状态正常"}</small>
                </button>
              ))}
            </div>
          )}
        </section>
      ) : null}

      {campaignId && view === "editor" ? (
        <>
          <div className={`sheet-and-roll ${editor.investigator_id ? "detail-mode" : "creation-mode"}`}>
            <InvestigatorSheet
              editor={editor}
              onCharacteristicChange={patchCharacteristic}
              onEditorChange={setEditor}
              onProfileChange={patchProfile}
            />
            {editor.investigator_id ? <RollPanel
              campaignId={campaignId}
              investigator={editor}
              investigationTitle={selectedCampaign?.title ?? "当前调查"}
            /> : null}
          </div>
          {editor.investigator_id ? <section className="development-panel" aria-label="幕间成长">
            <div>
              <p className="eyebrow">COC7 DEVELOPMENT PHASE</p>
              <h3>幕间成长 · 技能改善检定</h3>
              <p>仅列出带成长标记的技能。掷 D100 高于当前技能值或结果大于 95 时，再掷 1D10 增加技能；无论成败都清除本次标记。</p>
            </div>
            <div className="engine-form-row">
              <label className="field"><span>已标记技能</span><select aria-label="成长技能" value={growthSkillKey} onChange={(event) => setGrowthSkillKey(event.target.value)}><option value="">请选择</option>{editor.profile.skills.filter((item) => item.improvement_mark && !["credit_rating", "cthulhu_mythos", "mythos"].includes(item.skill_key)).map((item) => <option key={`${item.skill_key}-${item.specialization ?? ""}`} value={item.skill_key}>{item.display_name} · 当前 {item.current_value}</option>)}</select></label>
              <label className="field"><span>D100 改善检定</span><input aria-label="改善检定 D100" min="1" max="100" type="number" value={growthRoll} onChange={(event) => setGrowthRoll(Number(event.target.value))} /></label>
              <label className="field"><span>成功时 1D10</span><input aria-label="技能增加 1D10" min="1" max="10" type="number" value={growthIncrease} onChange={(event) => setGrowthIncrease(Number(event.target.value))} /></label>
              <button disabled={saving || !growthSkillKey} onClick={() => void handleSkillImprovement()} type="button">结算改善检定</button>
            </div>
          </section> : null}
          <div className="sheet-actions">
            <span>
              {editor.investigator_id
                ? `正在编辑 v${editor.version ?? 1}`
                : "新角色卡尚未保存"}
            </span>
            <button disabled={saving || loading} onClick={() => void handleSave()}>
              {saving ? "保存中…" : editor.investigator_id ? "保存角色卡" : "创建调查员"}
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}

type SheetProps = {
  editor: EditorState;
  onEditorChange: (next: EditorState | ((current: EditorState) => EditorState)) => void;
  onProfileChange: (patch: Partial<InvestigatorProfile>) => void;
  onCharacteristicChange: (key: keyof Characteristics, value: number) => void;
};

function InvestigatorSheet({
  editor,
  onEditorChange,
  onProfileChange,
  onCharacteristicChange,
}: SheetProps): ReactElement {
  const profile = editor.profile;
  const maxHp = maximumHitPoints(profile.characteristics);
  const maxMp = Math.floor(profile.characteristics.power / 5);
  const sanityCap = Math.max(0, 99 - editor.mythos);

  function updateSkill(index: number, patch: Partial<SkillEntry>): void {
    const next = profile.skills.map((item, itemIndex) =>
      itemIndex === index ? { ...item, ...patch } : item,
    );
    onProfileChange({ skills: next });
  }

  return (
    <>
      <InvestigatorOverview editor={editor} />
      <form className="investigator-sheet" onSubmit={(event) => event.preventDefault()}>
      <section className="sheet-section identity-section">
        <div className="section-title">
          <span>01</span>
          <h3>调查员档案</h3>
        </div>
        <div className="identity-grid">
          <Field label="姓名">
            <input
              aria-label="姓名"
              onChange={(event) => onProfileChange({ name: event.target.value })}
              value={profile.name}
            />
          </Field>
          <Field label="玩家">
            <input
              aria-label="玩家"
              onChange={(event) =>
                onProfileChange({ player_name: nullable(event.target.value) })
              }
              value={profile.player_name ?? ""}
            />
          </Field>
          <Field label="职业">
            <select
              aria-label="职业"
              onChange={(event) => onProfileChange({ occupation: event.target.value })}
              value={profile.occupation}
            >
              <option value="">请选择 COC7 职业</option>
              {profile.occupation && !OCCUPATION_PRESETS.includes(profile.occupation as typeof OCCUPATION_PRESETS[number]) ? (
                <option value={profile.occupation}>{profile.occupation}</option>
              ) : null}
              {OCCUPATION_PRESETS.map((occupation) => (
                <option key={occupation} value={occupation}>{occupation}</option>
              ))}
            </select>
          </Field>
          <Field label="年龄">
            <NumberInput
              label="年龄"
              max={120}
              min={15}
              onChange={(value) => onProfileChange({ age: value })}
              value={profile.age}
            />
          </Field>
          <Field label="性别">
            <input
              aria-label="性别"
              onChange={(event) => onProfileChange({ gender: nullable(event.target.value) })}
              value={profile.gender ?? ""}
            />
          </Field>
          <Field label="时代">
            <input
              aria-label="时代"
              onChange={(event) => onProfileChange({ era: event.target.value })}
              value={profile.era}
            />
          </Field>
          <Field label="住址">
            <input
              aria-label="住址"
              onChange={(event) =>
                onProfileChange({ residence: nullable(event.target.value) })
              }
              value={profile.residence ?? ""}
            />
          </Field>
          <Field label="出生地">
            <input
              aria-label="出生地"
              onChange={(event) =>
                onProfileChange({ birthplace: nullable(event.target.value) })
              }
              value={profile.birthplace ?? ""}
            />
          </Field>
        </div>
      </section>

      <section className="sheet-section">
        <div className="section-title">
          <span>02</span>
          <h3>属性</h3>
        </div>
        <div className="characteristic-grid">
          {CHARACTERISTICS.map((item) => {
            const value = profile.characteristics[item.key];
            return (
              <div className="characteristic" key={item.key}>
                <div>
                  <strong>{item.short}</strong>
                  <small>{item.label}</small>
                </div>
                <NumberInput
                  label={item.label}
                  max={200}
                  min={0}
                  onChange={(next) => onCharacteristicChange(item.key, next)}
                  value={value}
                />
                <span>{Math.floor(value / 2)}</span>
                <span>{Math.floor(value / 5)}</span>
              </div>
            );
          })}
        </div>
        <div className="threshold-legend">
          <span>原值</span>
          <span>困难 ½</span>
          <span>极难 ⅕</span>
        </div>
      </section>

      <section className="sheet-section">
        <div className="section-title">
          <span>03</span>
          <h3>状态与派生值</h3>
        </div>
        <div className="vitals-grid">
          <Vital
            label="生命 HP"
            max={maxHp}
            onChange={(hit_points) =>
              onEditorChange((current) => ({ ...current, hit_points }))
            }
            value={editor.hit_points}
          />
          <Vital
            label="魔法 MP"
            max={maxMp}
            onChange={(magic_points) =>
              onEditorChange((current) => ({ ...current, magic_points }))
            }
            value={editor.magic_points}
          />
          <Vital
            label="理智 SAN"
            max={sanityCap}
            onChange={(sanity) => onEditorChange((current) => ({ ...current, sanity }))}
            value={editor.sanity}
          />
          <Vital
            label="幸运 Luck"
            max={100}
            onChange={(luck) => onProfileChange({ luck })}
            value={profile.luck}
          />
          <Vital
            label="克苏鲁神话"
            max={100}
            onChange={(mythos) => onEditorChange((current) => ({ ...current, mythos }))}
            value={editor.mythos}
          />
          <Field label="移动力">
            <NumberInput
              label="移动力"
              max={20}
              min={0}
              onChange={(move_rate) => onProfileChange({ move_rate })}
              value={profile.move_rate}
            />
          </Field>
          <Field label="伤害加值">
            <input
              aria-label="伤害加值"
              onChange={(event) => onProfileChange({ damage_bonus: event.target.value })}
              value={profile.damage_bonus}
            />
          </Field>
          <Field label="体格">
            <NumberInput
              label="体格"
              max={20}
              min={-5}
              onChange={(build) => onProfileChange({ build })}
              value={profile.build}
            />
          </Field>
        </div>
        <div className="conditions">
          {Object.entries(CONDITION_LABELS).map(([condition, label]) => {
            const typedCondition = condition as InvestigatorCondition;
            return (
              <label key={condition}>
                <input
                  checked={editor.conditions.includes(typedCondition)}
                  onChange={(event) =>
                    onEditorChange((current) => ({
                      ...current,
                      conditions: event.target.checked
                        ? [...current.conditions, typedCondition]
                        : current.conditions.filter((item) => item !== typedCondition),
                    }))
                  }
                  type="checkbox"
                />
                {label}
              </label>
            );
          })}
        </div>
      </section>

      <section className="sheet-section">
        <div className="section-title">
          <span>04</span>
          <h3>调查员技能</h3>
        </div>
        <div className="skill-header" aria-hidden="true">
          <span>技能</span>
          <span>成长</span>
          <span>普通</span>
          <span>困难</span>
          <span>极难</span>
        </div>
        <div className="skill-list">
          {profile.skills.map((entry, index) => (
            <div
              className="skill-row"
              key={`${entry.skill_key}-${index}`}
              title={SKILL_DESCRIPTIONS[entry.skill_key] ?? "COC7 百分骰技能；由 KP 根据情境设定目标值与难度。"}
            >
              <input
                aria-label={`技能名称 ${index + 1}`}
                onChange={(event) =>
                  updateSkill(index, {
                    display_name: event.target.value,
                    skill_key:
                      entry.skill_key ||
                      event.target.value.trim().toLowerCase().replace(/\s+/g, "_"),
                  })
                }
                value={entry.display_name}
              />
              <input
                aria-label={`${entry.display_name} 成长标记`}
                checked={entry.improvement_mark}
                onChange={(event) =>
                  updateSkill(index, { improvement_mark: event.target.checked })
                }
                type="checkbox"
              />
              <NumberInput
                label={`${entry.display_name} 普通`}
                max={100}
                min={0}
                onChange={(current_value) => updateSkill(index, { current_value })}
                value={entry.current_value}
              />
              <output>{Math.floor(entry.current_value / 2)}</output>
              <output>{Math.floor(entry.current_value / 5)}</output>
            </div>
          ))}
        </div>
        <button
          className="text-button"
          onClick={() =>
            onProfileChange({
              skills: [
                ...profile.skills,
                skill(`custom_${profile.skills.length + 1}`, "自定义技能", 1),
              ],
            })
          }
          type="button"
        >
          ＋ 添加技能
        </button>
      </section>

      <section className="sheet-section">
        <div className="section-title">
          <span>05</span>
          <h3>背景故事</h3>
        </div>
        <p className="section-help">每行保存为一条独立记录，便于 KP 与 AI 精确引用。</p>
        <div className="backstory-grid">
          {BACKSTORY_FIELDS.map((item) => (
            <Field key={item.key} label={item.label}>
              <textarea
                aria-label={item.label}
                onChange={(event) =>
                  onProfileChange({
                    backstory: {
                      ...profile.backstory,
                      [item.key]: lines(event.target.value),
                    },
                  })
                }
                rows={3}
                value={profile.backstory[item.key].join("\n")}
              />
            </Field>
          ))}
        </div>
      </section>

      <section className="sheet-section">
        <div className="section-title">
          <span>06</span>
          <h3>信用与资产</h3>
        </div>
        <div className="identity-grid">
          <Field label="信用评级">
            <NumberInput
              label="信用评级"
              max={100}
              min={0}
              onChange={(credit_rating) => onProfileChange({ credit_rating })}
              value={profile.credit_rating}
            />
          </Field>
          <Field label="消费水平">
            <input
              aria-label="消费水平"
              onChange={(event) =>
                onProfileChange({ spending_level: nullable(event.target.value) })
              }
              value={profile.spending_level ?? ""}
            />
          </Field>
          <Field label="现金">
            <input
              aria-label="现金"
              onChange={(event) => onProfileChange({ cash: nullable(event.target.value) })}
              value={profile.cash ?? ""}
            />
          </Field>
          <Field label="资产">
            <textarea
              aria-label="资产"
              onChange={(event) => onProfileChange({ assets: nullable(event.target.value) })}
              rows={2}
              value={profile.assets ?? ""}
            />
          </Field>
        </div>
      </section>
      </form>
    </>
  );
}

function InvestigatorOverview({ editor }: { editor: EditorState }): ReactElement {
  const { profile } = editor;
  const maxHp = maximumHitPoints(profile.characteristics);
  const maxMp = Math.floor(profile.characteristics.power / 5);
  const sanityCap = Math.max(0, 99 - editor.mythos);
  const assets = profile.assets?.split(/\n|、|,/).map((value) => value.trim()).filter(Boolean) ?? [];
  return (
    <section className="investigator-overview" aria-label="调查员摘要">
      <div className="overview-identity">
        <span className="eyebrow">CURRENT INVESTIGATOR</span>
        <h3>{profile.name.trim() || "未命名调查员"}</h3>
        <p>{profile.occupation.trim() || "尚未填写职业"}{profile.player_name ? ` · ${profile.player_name}` : ""}</p>
        <div className="overview-tags">
          <span>信用评级 {profile.credit_rating}</span>
          <span>移动力 {profile.move_rate}</span>
          <span>伤害加值 {profile.damage_bonus || "0"}</span>
        </div>
      </div>
      <div className="overview-vitals">
        <OverviewVital label="生命 HP" value={editor.hit_points} max={maxHp} />
        <OverviewVital label="魔法 MP" value={editor.magic_points} max={maxMp} />
        <OverviewVital label="理智 SAN" value={editor.sanity} max={sanityCap} />
        <OverviewVital label="幸运 Luck" value={profile.luck} max={100} />
      </div>
      <div className="overview-assets">
        <strong>装备与资产</strong>
        <p>{assets.length ? assets.join(" · ") : "尚未记录装备或资产"}</p>
        <small>克苏鲁神话 {editor.mythos} · 体格 {profile.build} · {profile.spending_level || "消费水平未设定"}</small>
      </div>
      {editor.conditions.length ? (
        <div className="overview-conditions" aria-label="当前状态">
          {editor.conditions.map((condition) => <span key={condition}>{CONDITION_LABELS[condition]}</span>)}
        </div>
      ) : null}
    </section>
  );
}

function OverviewVital({ label, value, max }: { label: string; value: number; max: number }): ReactElement {
  const safeMax = Math.max(1, max);
  const percent = Math.max(0, Math.min(100, (value / safeMax) * 100));
  return (
    <div className="overview-vital" title={`${label}：${value} / ${max}`}>
      <div><span>{label}</span><strong>{value}<small> / {max}</small></strong></div>
      <div className="overview-meter"><i style={{ width: `${percent}%` }} /></div>
    </div>
  );
}

function Field({
  children,
  label,
}: {
  children: ReactElement;
  label: string;
}): ReactElement {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function NumberInput({
  label,
  max,
  min,
  onChange,
  value,
}: {
  label: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  value: number;
}): ReactElement {
  return (
    <input
      aria-label={label}
      max={max}
      min={min}
      onChange={(event) => onChange(Number(event.target.value))}
      type="number"
      value={value}
    />
  );
}

function Vital({
  label,
  max,
  onChange,
  value,
}: {
  label: string;
  max: number;
  onChange: (value: number) => void;
  value: number;
}): ReactElement {
  return (
    <div className="vital">
      <span>{label}</span>
      <div>
        <NumberInput label={label} max={max} min={0} onChange={onChange} value={value} />
        <output>/ {max}</output>
      </div>
    </div>
  );
}

function RollPanel({
  campaignId,
  investigator,
  investigationTitle,
}: {
  campaignId: string;
  investigator: EditorState;
  investigationTitle: string;
}): ReactElement {
  const [skillKey, setSkillKey] = useState("");
  const [label, setLabel] = useState("自定义检定");
  const [target, setTarget] = useState(50);
  const [difficulty, setDifficulty] = useState<RollDifficulty>("regular");
  const [modifier, setModifier] = useState(0);
  const [result, setResult] = useState<RollResult | null>(null);
  const [rolling, setRolling] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const skill = useMemo(
    () => investigator.profile.skills.find((entry) => entry.skill_key === skillKey),
    [investigator.profile.skills, skillKey],
  );

  function selectSkill(nextKey: string): void {
    setSkillKey(nextKey);
    const selected = investigator.profile.skills.find((entry) => entry.skill_key === nextKey);
    if (selected) {
      setLabel(selected.display_name);
      setTarget(selected.current_value);
    }
  }

  async function roll(): Promise<void> {
    setRolling(true);
    setFailure(null);
    try {
      const resolved = await resolveRoll({
        campaign_id: campaignId,
        investigator_id: investigator.investigator_id ?? undefined,
        skill_key: skill?.skill_key,
        label: label.trim() || "自定义检定",
        target,
        difficulty,
        bonus_penalty: modifier,
      });
      setResult(resolved);
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setRolling(false);
    }
  }

  return (
    <aside className="roll-panel">
      <p className="eyebrow">PERCENTILE CHECK</p>
      <h3>百分骰检定</h3>
      <p className="roll-context">{investigationTitle}</p>

      <Field label="使用技能">
        <select
          aria-label="使用技能"
          onChange={(event) => selectSkill(event.target.value)}
          value={skillKey}
        >
          <option value="">自定义目标值</option>
          {investigator.profile.skills.map((entry) => (
            <option key={entry.skill_key} value={entry.skill_key}>
              {entry.display_name} · {entry.current_value}
            </option>
          ))}
        </select>
      </Field>
      <Field label="检定名称">
        <input
          aria-label="检定名称"
          onChange={(event) => setLabel(event.target.value)}
          value={label}
        />
      </Field>
      <Field label="目标值">
        <NumberInput
          label="目标值"
          max={100}
          min={0}
          onChange={setTarget}
          value={target}
        />
      </Field>
      <Field label="难度">
        <select
          aria-label="难度"
          onChange={(event) => setDifficulty(event.target.value as RollDifficulty)}
          value={difficulty}
        >
          <option value="regular">普通成功</option>
          <option value="hard">困难成功</option>
          <option value="extreme">极难成功</option>
        </select>
      </Field>
      <Field label="奖惩骰">
        <select
          aria-label="奖惩骰"
          onChange={(event) => setModifier(Number(event.target.value))}
          value={modifier}
        >
          <option value={-2}>2 颗奖励骰</option>
          <option value={-1}>1 颗奖励骰</option>
          <option value={0}>无</option>
          <option value={1}>1 颗惩罚骰</option>
          <option value={2}>2 颗惩罚骰</option>
        </select>
      </Field>

      <div className="threshold-preview">
        <span>普通 ≤ {target}</span>
        <span>困难 ≤ {Math.floor(target / 2)}</span>
        <span>极难 ≤ {Math.floor(target / 5)}</span>
      </div>

      <button className="roll-button" disabled={rolling} onClick={() => void roll()}>
        {rolling ? "骰子滚动中…" : "掷出 1D100"}
      </button>
      {failure ? <p className="inline-error">{failure}</p> : null}
      {result ? <RollResultCard result={result} /> : null}
    </aside>
  );
}

const OUTCOME_LABELS: Record<RollResult["outcome"], string> = {
  fumble: "大失败",
  failure: "失败",
  regular: "普通成功",
  hard: "困难成功",
  extreme: "极难成功",
  critical: "大成功",
};

function RollResultCard({ result }: { result: RollResult }): ReactElement {
  return (
    <section
      aria-live="polite"
      className={result.passed ? "roll-result passed" : "roll-result failed"}
    >
      <span className="roll-total">{String(result.roll).padStart(2, "0")}</span>
      <div>
        <strong>{OUTCOME_LABELS[result.outcome]}</strong>
        <small>{result.passed ? "达到所需难度" : "未达到所需难度"}</small>
      </div>
      <p>
        十位骰：{result.tens.join("、")} · 个位骰：{result.ones}
      </p>
    </section>
  );
}
