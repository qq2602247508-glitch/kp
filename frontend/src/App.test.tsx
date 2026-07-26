import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("COC KP application shell", () => {
  it("starts on the keeper dashboard", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "守秘人仪表板" }),
    ).toBeInTheDocument();
    expect(screen.getByText("AI 的变更必须经 KP 确认")).toBeInTheDocument();
  });

  it("opens the native investigator character sheet", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /调查员/ }));

    expect(
      await screen.findByRole("heading", { name: "COC7 调查员角色卡" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("先建立一场调查")).toBeInTheDocument();
  });
});
