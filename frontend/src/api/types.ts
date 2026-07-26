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
  | "stabilized"
  | "dead"
  | "bout_of_madness"
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
  case_session_id?: string;
  investigator_id?: string;
  skill_key?: string;
  label: string;
  target: number;
  difficulty: RollDifficulty;
  bonus_penalty: number;
  dice?: {
    units_digit: number;
    tens_digits: number[];
  };
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

export type RuleFilters = {
  sourcePack?: string;
  edition?: string;
  module?: string;
  era?: string;
};

export type RuleCitation = {
  citation_id: string;
  chunk_id: string;
  excerpt: string;
  score: number;
  source_pack: string;
  edition: string;
  module: string;
  era: string[];
  filename: string;
  page: number | null;
  section: string;
  checksum: string;
};

export type RuleSearchResponse = {
  query: string;
  results: RuleCitation[];
};

export type RuleAnswerResponse = {
  question: string;
  answer: string;
  citations: RuleCitation[];
  abstained: boolean;
  reason: string | null;
};

export type CaseEntityKind =
  | "sessions"
  | "people"
  | "locations"
  | "scenes"
  | "clues"
  | "relationships"
  | "handouts"
  | "timeline-events";

export type CaseEntryDraft = {
  title: string;
  player_visible_text: string;
  keeper_truth: string;
  status: string;
  time_label?: string | null;
  role?: string | null;
  session_id?: string | null;
  location_id?: string | null;
  scene_id?: string | null;
  person_id?: string | null;
  clue_id?: string | null;
  source_clue_id?: string | null;
  target_clue_id?: string | null;
  relationship_type?: string | null;
  discovered?: boolean;
  revealed?: boolean;
  sort_order?: number;
};

export type CaseEntry = Required<
  Omit<CaseEntryDraft, "time_label" | "role">
> & {
  time_label: string | null;
  role: string | null;
  entity_id: string;
  campaign_id: string;
  kind: CaseEntityKind;
  version: number;
  created_at: string;
  updated_at: string;
};

export type PlayerCaseEntry = {
  entity_id: string;
  campaign_id: string;
  kind: CaseEntityKind;
  title: string;
  player_visible_text: string;
  status: string;
  time_label: string | null;
  role: string | null;
  discovered: boolean;
  revealed: boolean;
};

export type EngineCitation = {
  citation_id: string;
  source_pack_id: string;
  filename: string;
  page: number;
  section: string;
  edition: string;
  module: string;
  era: string[];
  checksum: string;
};

export type EngineOperation = {
  operation_id: string;
  operation_type: string;
  investigator: Investigator;
  target: Investigator | null;
  citation: EngineCitation;
  citations: EngineCitation[];
  loss: number | null;
  session_sanity_loss: number | null;
  reason: string | null;
  damage_applied: number | null;
  injury_id: string | null;
  healed: number | null;
  care_type: string | null;
  hit: boolean | null;
  weapon_key: string | null;
  attack_roll_id: string | null;
  created_at: string;
};

export type RuleOperationLog = {
  operation_id: string;
  campaign_id: string;
  subject_id: string;
  case_session_id: string | null;
  session_key: string | null;
  operation_type: string;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown>;
  citation: EngineCitation;
  citations: EngineCitation[];
  created_at: string;
};

export type StateAuditLog = {
  audit_id: string;
  campaign_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  expected_version: number | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

export type WeaponPolicy = {
  weapon_key: string;
  name: string;
  damage_notation: string;
  maximum_rolled_damage: number;
  skill_key: string;
  uses_damage_bonus: boolean;
  citation: EngineCitation;
  citations: EngineCitation[];
};

export type ChaseParticipant = {
  investigator_id: string;
  role: "pursuer" | "fleeing";
  position: number;
  move_rate: number;
  actions_remaining: number;
};

export type Chase = {
  chase_id: string;
  campaign_id: string;
  title: string;
  case_session_id: string | null;
  session_key: string | null;
  status: string;
  participants: ChaseParticipant[];
  round: number;
  escape_distance: number;
  track_length: number;
  version: number;
  citation: EngineCitation;
  citations: EngineCitation[];
  created_at: string;
  updated_at: string;
};

export type AIProposal = {
  proposal_id: string;
  campaign_id: string;
  proposal_type: "case_state_create" | "case_state_replace";
  case_kind: CaseEntityKind;
  target_entity_id: string | null;
  campaign_version: number;
  target_version: number | null;
  payload: Record<string, unknown>;
  diff: Record<string, { before: unknown; after: unknown }>;
  evidence: Record<string, unknown>[];
  citation_ids: string[];
  model_name: string;
  model_metadata: Record<string, unknown>;
  status: "pending" | "confirmed" | "rejected";
  version: number;
  rejection_reason: string | null;
  applied_entity_id: string | null;
  created_at: string;
  expires_at: string;
  is_expired: boolean;
  resolved_at: string | null;
};

export type ProposalAuditLog = {
  audit_id: string;
  proposal_id: string;
  campaign_id: string;
  action: "confirm" | "reject";
  expected_version: number;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  reason: string | null;
  created_at: string;
};

export type AIKPResponse = {
  answer: string;
  keeper_private_hints: string[];
  scene_suggestions: string[];
  citations: Record<string, unknown>[];
  proposals: AIProposal[];
  model_name: string;
  advisory_only: true;
};

export type ReadinessItem = {
  status: "ready" | "missing" | "failed" | "incompatible" | "unavailable";
  [key: string]: unknown;
};

export type DeliveryReadiness = {
  product: "local-coc-kp-assistant";
  ruleset: "coc7e";
  ready: boolean;
  database: ReadinessItem;
  sources: ReadinessItem & { ready_packs: number; failed_packs: number };
  vector_index: ReadinessItem & { chunk_count: number };
  models: {
    provider: "ollama";
    provider_status: string;
    embedding: ReadinessItem & {
      name: "bge-m3:latest";
      installed: boolean;
      download_attempted: false;
    };
    completion: ReadinessItem & {
      name: "qwen3:30b-instruct";
      installed: boolean;
      download_attempted: false;
    };
  };
};

export type SourcePackSetting = {
  pack_id: string;
  title: string;
  version: string;
  edition: string;
  kind: string;
  default_enabled: boolean;
  eras: string[];
  compatible: boolean;
  required_default: boolean;
  enabled: boolean;
};

export type CampaignSourcePacks = {
  campaign_id: string;
  campaign_version: number;
  enabled_source_pack_ids: string[];
  packs: SourcePackSetting[];
};

export type CampaignExport = {
  product: "local-coc-kp-assistant";
  ruleset: "coc7e";
  schema_version: 1;
  namespace: "local-coc-kp-assistant/coc7e";
  exported_at: string;
  campaign_id: string;
  tables: Record<string, Record<string, unknown>[]>;
};

export type BackupResult = {
  path: string;
  manifest: Record<string, unknown>;
};
