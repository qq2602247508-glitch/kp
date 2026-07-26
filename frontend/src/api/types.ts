export type CampaignEra =
  | "ancient"
  | "dark_ages"
  | "gaslight"
  | "1920s"
  | "modern"
  | "future"
  | "apocalypse"
  | "dreamlands"
  | "custom";

export type CampaignCreate = {
  title: string;
  ruleset?: "coc7e";
  era: CampaignEra;
  custom_era_label?: string | null;
  in_world_date?: string | null;
  starting_location?: string | null;
  enabled_source_pack_ids: string[];
  house_rules: string[];
  keeper_notes?: string | null;
};

export type Campaign = CampaignCreate & {
  ruleset: "coc7e";
  campaign_id: string;
  version: number;
};

export type Characteristics = {
  strength: number;
  constitution: number;
  size: number;
  dexterity: number;
  appearance: number;
  intelligence: number;
  power: number;
  education: number;
};

export type SkillEntry = {
  skill_key: string;
  display_name: string;
  specialization: string | null;
  base_value: number;
  current_value: number;
  improvement_mark: boolean;
  source_pack_id: string | null;
};

export type InvestigatorBackstory = {
  personal_description: string[];
  ideology_and_beliefs: string[];
  significant_people: string[];
  meaningful_locations: string[];
  treasured_possessions: string[];
  traits: string[];
  injuries_and_scars: string[];
  phobias_and_manias: string[];
  mythos_tomes_spells_artifacts: string[];
  strange_encounters: string[];
};

export type InvestigatorProfile = {
  name: string;
  player_name: string | null;
  occupation: string;
  age: number;
  gender: string | null;
  residence: string | null;
  birthplace: string | null;
  era: string;
  characteristics: Characteristics;
  luck: number;
  move_rate: number;
  damage_bonus: string;
  build: number;
  credit_rating: number;
  spending_level: string | null;
  cash: string | null;
  assets: string | null;
  skills: SkillEntry[];
  backstory: InvestigatorBackstory;
};

export type InvestigatorCondition =
  | "major_wound"
  | "unconscious"
  | "dying"
  | "temporary_insanity"
  | "indefinite_insanity";

export type Investigator = {
  investigator_id: string;
  campaign_id: string;
  profile: InvestigatorProfile;
  hit_points: number;
  magic_points: number;
  sanity: number;
  mythos: number;
  conditions: InvestigatorCondition[];
  version: number;
};

export type InvestigatorUpdate = InvestigatorProfile & {
  hit_points: number;
  magic_points: number;
  sanity: number;
  mythos: number;
  conditions: InvestigatorCondition[];
  expected_version: number;
};

export type RollDifficulty = "regular" | "hard" | "extreme";

export type RollRequest = {
  campaign_id: string;
  investigator_id?: string;
  skill_key?: string;
  label: string;
  target: number;
  difficulty: RollDifficulty;
  bonus_penalty: number;
};

export type RollResult = {
  roll_id: string;
  roll: number;
  tens: number[];
  ones: number;
  target: number;
  regular_threshold: number;
  hard_threshold: number;
  extreme_threshold: number;
  outcome: "fumble" | "failure" | "regular" | "hard" | "extreme" | "critical";
  difficulty: RollDifficulty;
  bonus_penalty: number;
  passed: boolean;
};

