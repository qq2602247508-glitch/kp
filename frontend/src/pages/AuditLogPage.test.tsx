import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuditLogPage } from "./AuditLogPage";

vi.mock("../api/client", () => ({
  listCampaigns: vi.fn(),
  listRuleOperations: vi.fn(),
  listStateAudits: vi.fn(),
}));

import { listCampaigns, listRuleOperations, listStateAudits } from "../api/client";

afterEach(() => vi.clearAllMocks());

const campaign = {
  campaign_id: "campaign-1", title: "雾港", ruleset: "coc7e" as const, era: "1920s" as const,
  enabled_source_pack_ids: [], house_rules: [], version: 1,
};

describe("AuditLogPage", () => {
  it("shows state changes, switches to rule operations, and renders diffs/citations", async () => {
    vi.mocked(listCampaigns).mockResolvedValue([campaign]);
    vi.mocked(listStateAudits).mockResolvedValue([{
      audit_id: "audit-1", campaign_id: "campaign-1", action: "更新线索", entity_type: "case",
      entity_id: "clue-1", expected_version: 1, before: { status: "open" },
      after: { status: "resolved" }, created_at: "2026-01-01T00:00:00Z",
    }]);
    vi.mocked(listRuleOperations).mockResolvedValue([{
      operation_id: "op-1", campaign_id: "campaign-1", subject_id: "investigator-1",
      case_session_id: null, session_key: null, operation_type: "技能检定",
      input_data: { target: 60 }, output_data: { outcome: "hard" },
      citation: { citation_id: "cite-1", source_pack_id: "core", filename: "core.pdf", page: 88,
        section: "技能", edition: "7e", module: "core", era: ["1920s"], checksum: "a".repeat(64) },
      citations: [{ citation_id: "cite-1", source_pack_id: "core", filename: "core.pdf", page: 88,
        section: "技能", edition: "7e", module: "core", era: ["1920s"], checksum: "a".repeat(64) }],
      created_at: "2026-01-01T00:00:00Z",
    }]);

    render(<AuditLogPage />);
    expect(await screen.findByText("更新线索")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /规则操作/ }));
    expect(await screen.findByText("技能检定")).toBeInTheDocument();
    expect(screen.getByText("core.pdf 第88页")).toBeInTheDocument();
    fireEvent.click(screen.getByText("查看判定输入与输出"));
    expect(screen.getByText(/"target": 60/)).toBeInTheDocument();
    expect(screen.getByText(/"outcome": "hard"/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /状态变更/ }));
    fireEvent.click(screen.getByText("查看变更前后"));
    expect(screen.getByText(/"status": "open"/)).toBeInTheDocument();
    expect(screen.getByText(/"status": "resolved"/)).toBeInTheDocument();
  });

  it("shows API errors from campaign and audit loading", async () => {
    vi.mocked(listCampaigns).mockRejectedValueOnce(new Error("campaign unavailable"));
    render(<AuditLogPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("campaign unavailable");

    cleanup();
    vi.clearAllMocks();
    vi.mocked(listCampaigns).mockResolvedValue([campaign]);
    vi.mocked(listStateAudits).mockRejectedValue(new Error("audit unavailable"));
    vi.mocked(listRuleOperations).mockResolvedValue([]);
    render(<AuditLogPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("audit unavailable");
  });
});
