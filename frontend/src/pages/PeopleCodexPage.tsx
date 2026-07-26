import { useEffect, useState, type FormEvent, type ReactElement } from "react";

import {
  createCaseEntry,
  listCampaigns,
  listCaseEntries,
  updateCaseEntry,
} from "../api/client";
import type {
  Campaign,
  CaseEntry,
  CaseEntryDraft,
  PersonAttack,
  PersonCharacteristics,
  PersonEntityType,
  PersonSkill,
} from "../api/types";
import {
  chooseAvailableCampaign,
  selectCampaign,
  subscribeToCampaignSelection,
} from "../state/campaignSelection";
import "./PeopleCodexPage.css";

const DEFAULT_CHARACTERISTICS: PersonCharacteristics = {
  strength: 50,
  constitution: 50,
  size: 50,
  dexterity: 50,
  appearance: 50,
  intelligence: 50,
  power: 50,
  education: 50,
};

const CHARACTERISTIC_LABELS: Array<[keyof PersonCharacteristics, string]> = [
  ["strength", "力量 STR"], ["constitution", "体质 CON"], ["size", "体型 SIZ"],
  ["dexterity", "敏捷 DEX"], ["appearance", "外貌 APP"], ["intelligence", "智力 INT"],
  ["power", "意志 POW"], ["education", "教育 EDU"],
];

type Editor = {
  title: string;
  role: string;
  personType: PersonEntityType;
  status: string;
  playerText: string;
  keeperTruth: string;
  characteristics: PersonCharacteristics;
  hitPoints: number;
  moveRate: number;
  damageBonus: string;
  build: number;
  armor: string;
  sanityLoss: string;
  skillsText: string;
  attacksText: string;
  abilitiesText: string;
};

function blankEditor(): Editor {
  return {
    title: "", role: "", personType: "keeper_npc", status: "active",
    playerText: "", keeperTruth: "", characteristics: { ...DEFAULT_CHARACTERISTICS },
    hitPoints: 10, moveRate: 8, damageBonus: "0", build: 0, armor: "无",
    sanityLoss: "0/0", skillsText: "侦查 | 50 | 发现隐蔽事物",
    attacksText: "斗殴 | 斗殴 | 50 | 1D3+DB | 1 | 接触",
    abilitiesText: "",
  };
}

function skillsFromText(text: string): PersonSkill[] {
  return text.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [name = "", value = "0", description = ""] = line.split("|").map((part) => part.trim());
    return { name, value: Number(value), description };
  });
}

function attacksFromText(text: string): PersonAttack[] {
  return text.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [name = "", skill_name = "", skill_value = "0", damage = "", attacks = "1", range = ""] = line.split("|").map((part) => part.trim());
    return { name, skill_name, skill_value: Number(skill_value), damage, attacks_per_round: Number(attacks), range: range || null, malfunction: null, description: "" };
  });
}

function editorFromEntry(entry: CaseEntry): Editor {
  return {
    title: entry.title, role: entry.role ?? "", personType: entry.person_type,
    status: entry.status, playerText: entry.player_visible_text, keeperTruth: entry.keeper_truth,
    characteristics: entry.characteristics ?? { ...DEFAULT_CHARACTERISTICS },
    hitPoints: entry.hit_points ?? 10, moveRate: entry.move_rate ?? 8,
    damageBonus: entry.damage_bonus ?? "0", build: entry.build ?? 0,
    armor: entry.armor ?? "无", sanityLoss: entry.sanity_loss ?? "0/0",
    skillsText: entry.skills.map((item) => `${item.name} | ${item.value} | ${item.description}`).join("\n"),
    attacksText: entry.attacks.map((item) => `${item.name} | ${item.skill_name} | ${item.skill_value} | ${item.damage} | ${item.attacks_per_round} | ${item.range ?? ""}`).join("\n"),
    abilitiesText: entry.special_abilities.join("\n"),
  };
}

export function PeopleCodexPage(): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [entries, setEntries] = useState<CaseEntry[]>([]);
  const [editing, setEditing] = useState<CaseEntry | null>(null);
  const [editor, setEditor] = useState<Editor>(blankEditor);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    listCampaigns(controller.signal).then((items) => {
      setCampaigns(items);
      const selected = chooseAvailableCampaign(items.map((item) => item.campaign_id), "");
      setCampaignId(selected);
    }).catch(() => setMessage("无法读取案件。"));
    return () => controller.abort();
  }, []);

  useEffect(() => subscribeToCampaignSelection((id) => setCampaignId(id)), []);

  useEffect(() => {
    if (!campaignId) { setEntries([]); return; }
    const controller = new AbortController();
    listCaseEntries(campaignId, "people", controller.signal)
      .then(setEntries).catch(() => setMessage("无法读取人物图鉴。"));
    return () => controller.abort();
  }, [campaignId]);

  function choose(entry: CaseEntry): void {
    setEditing(entry);
    setEditor(editorFromEntry(entry));
  }

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!campaignId) return;
    setBusy(true);
    const payload: CaseEntryDraft = {
      title: editor.title.trim(), role: editor.role || null, person_type: editor.personType,
      status: editor.status, player_visible_text: editor.playerText, keeper_truth: editor.keeperTruth,
      characteristics: editor.characteristics, hit_points: editor.hitPoints, move_rate: editor.moveRate,
      damage_bonus: editor.damageBonus, build: editor.build, armor: editor.armor,
      sanity_loss: editor.sanityLoss, skills: skillsFromText(editor.skillsText),
      attacks: attacksFromText(editor.attacksText),
      special_abilities: editor.abilitiesText.split("\n").map((item) => item.trim()).filter(Boolean),
    };
    try {
      const saved = editing
        ? await updateCaseEntry(campaignId, "people", editing.entity_id, { ...payload, expected_version: editing.version })
        : await createCaseEntry(campaignId, "people", payload);
      setEntries((current) => [...current.filter((item) => item.entity_id !== saved.entity_id), saved]);
      choose(saved);
      setMessage(editing ? "人物卡已更新并记录审计。" : "人物已加入本案图鉴。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败。");
    } finally { setBusy(false); }
  }

  return <div className="people-codex">
    <header className="people-codex-header">
      <div><p className="eyebrow">COC7 KEEPER NPC / MYTHOS CODEX</p><h2>人物与神话存在</h2><p>独立于调查员的 KP 单位卡；使用百分技能、伤害加值、体格、护甲与理智损失。</p></div>
      <label>当前案件<select value={campaignId} onChange={(event) => { setCampaignId(event.target.value); selectCampaign(event.target.value); }}><option value="">请选择案件</option>{campaigns.map((item) => <option key={item.campaign_id} value={item.campaign_id}>{item.title}</option>)}</select></label>
    </header>
    <div className="people-codex-layout">
      <section className="people-codex-list">
        <div className="people-codex-title"><strong>本案图鉴</strong><button onClick={() => { setEditing(null); setEditor(blankEditor()); }} type="button">新建人物 / 存在</button></div>
        {entries.map((entry) => <button className={`people-codex-card ${editing?.entity_id === entry.entity_id ? "selected" : ""}`} key={entry.entity_id} onClick={() => choose(entry)} type="button">
          <span><strong>{entry.title}</strong><small>{entry.person_type === "mythos_entity" ? "神话存在" : entry.person_type === "animal" ? "动物" : "NPC"} · {entry.role || "未设身份"}</small></span>
          <span><b>HP {entry.hit_points ?? "—"}</b><b>MOV {entry.move_rate ?? "—"}</b><b>DEX {entry.characteristics?.dexterity ?? "—"}</b></span>
          <p>{entry.attacks[0] ? `${entry.attacks[0].name} ${entry.attacks[0].skill_value}% · ${entry.attacks[0].damage}` : "尚未记录攻击"}</p>
        </button>)}
      </section>
      <form className="people-codex-editor" onSubmit={save}>
        <div className="people-codex-title"><strong>{editing ? `编辑：${editing.title}` : "新建 COC7 单位卡"}</strong><small>{editing ? `v${editing.version}` : "待保存"}</small></div>
        <div className="people-form-grid"><label>名称<input required value={editor.title} onChange={(event) => setEditor({ ...editor, title: event.target.value })} /></label><label>类型<select value={editor.personType} onChange={(event) => setEditor({ ...editor, personType: event.target.value as PersonEntityType })}><option value="keeper_npc">守秘人 NPC</option><option value="mythos_entity">神话存在</option><option value="animal">动物</option><option value="custom">自定义存在</option></select></label><label>身份 / 作用<input value={editor.role} onChange={(event) => setEditor({ ...editor, role: event.target.value })} /></label><label>状态<input value={editor.status} onChange={(event) => setEditor({ ...editor, status: event.target.value })} /></label></div>
        <fieldset><legend>COC7 属性</legend><div className="people-stat-grid">{CHARACTERISTIC_LABELS.map(([key, label]) => <label key={key}>{label}<input min="0" max="999" type="number" value={editor.characteristics[key]} onChange={(event) => setEditor({ ...editor, characteristics: { ...editor.characteristics, [key]: Number(event.target.value) } })} /></label>)}</div></fieldset>
        <div className="people-form-grid compact"><label>HP<input min="0" type="number" value={editor.hitPoints} onChange={(event) => setEditor({ ...editor, hitPoints: Number(event.target.value) })} /></label><label>MOV<input min="0" type="number" value={editor.moveRate} onChange={(event) => setEditor({ ...editor, moveRate: Number(event.target.value) })} /></label><label>伤害加值<input value={editor.damageBonus} onChange={(event) => setEditor({ ...editor, damageBonus: event.target.value })} /></label><label>体格<input type="number" value={editor.build} onChange={(event) => setEditor({ ...editor, build: Number(event.target.value) })} /></label><label>护甲<input value={editor.armor} onChange={(event) => setEditor({ ...editor, armor: event.target.value })} /></label><label>目击理智损失<input value={editor.sanityLoss} onChange={(event) => setEditor({ ...editor, sanityLoss: event.target.value })} /></label></div>
        <div className="people-text-grid"><label>技能（每行：名称 | 百分值 | 说明）<textarea rows={5} value={editor.skillsText} onChange={(event) => setEditor({ ...editor, skillsText: event.target.value })} /></label><label>攻击（名称 | 技能 | 百分值 | 伤害 | 每轮次数 | 距离）<textarea rows={5} value={editor.attacksText} onChange={(event) => setEditor({ ...editor, attacksText: event.target.value })} /></label><label>特殊能力（每行一项）<textarea rows={4} value={editor.abilitiesText} onChange={(event) => setEditor({ ...editor, abilitiesText: event.target.value })} /></label><label>KP 真相<textarea rows={4} value={editor.keeperTruth} onChange={(event) => setEditor({ ...editor, keeperTruth: event.target.value })} /></label><label>玩家可见描述<textarea rows={4} value={editor.playerText} onChange={(event) => setEditor({ ...editor, playerText: event.target.value })} /></label></div>
        <div className="people-codex-actions"><button disabled={busy || !campaignId} type="submit">{busy ? "保存中…" : "保存单位卡"}</button><span aria-live="polite">{message}</span></div>
      </form>
    </div>
  </div>;
}
