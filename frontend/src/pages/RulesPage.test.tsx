import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RulesPage } from "./RulesPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Rules workspace", () => {
  it("searches with filters and shows source locations", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        query: "困难成功",
        results: [
          {
            citation_id: "chunk-1",
            chunk_id: "chunk-1",
            excerpt: "困难成功需要不高于技能值的一半。",
            score: 0.93,
            source_pack: "coc7e.core.zh-v1.2.1",
            edition: "7e",
            module: "core",
            era: ["1920s"],
            filename: "COC7核心规则书v1.2.1.pdf",
            page: 88,
            section: "技能检定",
            checksum: "a".repeat(64),
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<RulesPage />);

    fireEvent.change(screen.getByLabelText("规则问题"), {
      target: { value: "困难成功" },
    });
    fireEvent.change(screen.getByLabelText("来源包"), {
      target: { value: "coc7e.core.zh-v1.2.1" },
    });
    fireEvent.change(screen.getByLabelText("版本"), {
      target: { value: "7e" },
    });
    fireEvent.change(screen.getByLabelText("模块"), {
      target: { value: "core" },
    });
    fireEvent.change(screen.getByLabelText("时代"), {
      target: { value: "1920s" },
    });
    fireEvent.click(screen.getByRole("button", { name: "检索规则" }));

    expect(await screen.findByText("困难成功需要不高于技能值的一半。")).toBeInTheDocument();
    expect(screen.getByText(/第 88 页/)).toBeInTheDocument();
    expect(screen.getByText(/技能检定/)).toBeInTheDocument();
    await waitFor(() => {
      const url = String(fetchMock.mock.calls[0][0]);
      expect(url).toContain("source_pack=coc7e.core.zh-v1.2.1");
      expect(url).toContain("edition=7e");
      expect(url).toContain("module=core");
      expect(url).toContain("era=1920s");
    });
  });

  it("shows an explicit abstention instead of an uncited answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          question: "未知问题",
          answer: "",
          citations: [],
          abstained: true,
          reason: "insufficient_evidence",
        }),
      }),
    );
    render(<RulesPage />);

    fireEvent.change(screen.getByLabelText("规则问题"), {
      target: { value: "未知问题" },
    });
    fireEvent.click(screen.getByRole("button", { name: "依据资料回答" }));

    expect(await screen.findByText("现有资料不足，无法给出有引用的回答。")).toBeInTheDocument();
  });
});
