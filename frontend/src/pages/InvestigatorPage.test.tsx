import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Investigator } from "../api/types";
import { InvestigatorPage } from "./InvestigatorPage";

const investigator: Investigator = {
  investigator_id: "inv-1",
  campaign_id: "campaign-1",
  hit_points: 10,
  magic_points: 10,
  sanity: 50,
  mythos: 0,
  conditions: [],
  version: 1,
  profile: {
    name: "林若岚",
    player_name: "测试玩家",
    occupation: "记者",
    age: 28,
    gender: "女",
    residence: "上海",
    birthplace: "苏州",
    era: "1920s",
    characteristics: {
      strength: 50,
      constitution: 50,
      size: 50,
      dexterity: 60,
      appearance: 55,
      intelligence: 70,
      power: 50,
      education: 65,
    },
    luck: 45,
    move_rate: 8,
    damage_bonus: "0",
    build: 0,
    credit_rating: 30,
    spending_level: "普通",
    cash: "10",
    assets: "相机",
    skills: [
      {
        skill_key: "spot_hidden",
        display_name: "侦查",
        specialization: null,
        base_value: 25,
        current_value: 65,
        improvement_mark: false,
        source_pack_id: null,
      },
    ],
    backstory: {
      personal_description: ["总带着一台相机"],
      ideology_and_beliefs: [],
      significant_people: [],
      meaningful_locations: [],
      treasured_possessions: [],
      traits: [],
      injuries_and_scars: [],
      phobias_and_manias: [],
      mythos_tomes_spells_artifacts: [],
      strange_encounters: [],
    },
  },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("InvestigatorPage", () => {
  it("shows an actionable empty investigation state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));

    render(<InvestigatorPage />);

    expect(await screen.findByText("先建立一场调查")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建调查" })).toBeEnabled();
  });

  it("loads a native sheet and resolves a percentile check", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/campaigns") && !init?.method) {
        return Promise.resolve(
          jsonResponse([
            {
              campaign_id: "campaign-1",
              title: "雾中来客",
              ruleset: "coc7e",
              era: "1920s",
              enabled_source_pack_ids: [],
              house_rules: [],
              version: 1,
            },
          ]),
        );
      }
      if (url.endsWith("/campaigns/campaign-1/investigators")) {
        return Promise.resolve(jsonResponse([investigator]));
      }
      if (url.endsWith("/rolls")) {
        return Promise.resolve(
          jsonResponse({
            roll_id: "roll-1",
            roll: 23,
            tens: [2],
            ones: 3,
            target: 65,
            regular_threshold: 65,
            hard_threshold: 32,
            extreme_threshold: 13,
            outcome: "hard",
            difficulty: "regular",
            bonus_penalty: 0,
            passed: true,
          }),
        );
      }
      return Promise.resolve(jsonResponse({ detail: "unexpected request" }, 500));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<InvestigatorPage />);

    await waitFor(() => expect(screen.getByLabelText("姓名")).toHaveValue("林若岚"));
    expect(screen.getByRole("region", { name: "调查员摘要" })).toHaveTextContent("生命 HP");
    expect(screen.getByRole("region", { name: "调查员摘要" })).toHaveTextContent("装备与资产");
    expect(screen.getByTitle(/发现隐藏的门/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("使用技能"), {
      target: { value: "spot_hidden" },
    });
    fireEvent.click(screen.getByRole("button", { name: "掷出 1D100" }));

    expect(await screen.findByText("困难成功")).toBeInTheDocument();
    expect(screen.getByText("达到所需难度")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  });
});
