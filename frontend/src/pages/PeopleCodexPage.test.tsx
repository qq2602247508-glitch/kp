import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PeopleCodexPage } from "./PeopleCodexPage";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("PeopleCodexPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a COC7 mythos entity sheet with skills and attacks", async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      requests.push({ url, init });
      if (url.endsWith("/campaigns")) return Promise.resolve(json([{ campaign_id: "case-1", title: "雾港", ruleset: "coc7e", era: "1920s", enabled_source_pack_ids: [], house_rules: [], version: 1 }]));
      if (url.endsWith("/case-state/people") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        return Promise.resolve(json({ ...body, entity_id: "person-1", campaign_id: "case-1", kind: "people", version: 1, created_at: "2026-01-01", updated_at: "2026-01-01" }, 201));
      }
      if (url.endsWith("/case-state/people")) return Promise.resolve(json([]));
      return Promise.resolve(json({}));
    });

    render(<PeopleCodexPage />);
    await screen.findByText("本案图鉴");
    fireEvent.change(screen.getByLabelText("名称"), { target: { value: "深潜者" } });
    fireEvent.change(screen.getByLabelText("类型"), { target: { value: "mythos_entity" } });
    fireEvent.click(screen.getByRole("button", { name: "保存单位卡" }));

    await waitFor(() => expect(screen.getByText("人物已加入本案图鉴。")).toBeInTheDocument());
    const post = requests.find((request) => request.init?.method === "POST");
    const payload = JSON.parse(String(post?.init?.body));
    expect(payload.person_type).toBe("mythos_entity");
    expect(payload.characteristics.dexterity).toBe(50);
    expect(payload.skills[0]).toMatchObject({ name: "侦查", value: 50 });
    expect(payload.attacks[0]).toMatchObject({ skill_name: "斗殴", damage: "1D3+DB" });
  });
});
