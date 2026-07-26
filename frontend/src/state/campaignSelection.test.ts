import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  chooseAvailableCampaign,
  readSelectedCampaignId,
  selectCampaign,
  subscribeToCampaignSelection,
} from "./campaignSelection";

describe("campaign selection", () => {
  beforeEach(() => {
    window.localStorage.clear();
    selectCampaign("");
  });

  it("prefers a valid current id, then stored id, then first available", () => {
    window.localStorage.setItem("local-coc-kp-assistant:selected-campaign", "stored");
    expect(chooseAvailableCampaign(["current", "stored"], "current")).toBe("current");
    expect(chooseAvailableCampaign(["stored", "other"], "missing")).toBe("stored");
    expect(chooseAvailableCampaign(["first", "other"], "missing")).toBe("first");
    expect(chooseAvailableCampaign([], "missing")).toBe("");
  });

  it("stores selections and dispatches them to subscribers", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToCampaignSelection(listener);
    selectCampaign("campaign-2");
    expect(readSelectedCampaignId()).toBe("campaign-2");
    expect(listener).toHaveBeenCalledWith("campaign-2");
    unsubscribe();
  });

  it("continues with in-memory events when storage throws", () => {
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    const listener = vi.fn();
    const unsubscribe = subscribeToCampaignSelection(listener);
    selectCampaign("campaign-3");
    expect(readSelectedCampaignId()).toBe("campaign-3");
    expect(chooseAvailableCampaign(["campaign-1", "campaign-3"], "")).toBe("campaign-3");
    expect(listener).toHaveBeenCalledWith("campaign-3");
    unsubscribe();
  });
});
