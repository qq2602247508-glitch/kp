const STORAGE_KEY = "local-coc-kp-assistant:selected-campaign";
const EVENT_NAME = "coc-kp:campaign-selected";
let inMemoryCampaignId = "";

export function readSelectedCampaignId(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? inMemoryCampaignId;
  } catch {
    return inMemoryCampaignId;
  }
}

export function selectCampaign(campaignId: string): void {
  inMemoryCampaignId = campaignId;
  try {
    if (campaignId) {
      window.localStorage.setItem(STORAGE_KEY, campaignId);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // The in-memory selection still works when browser storage is unavailable.
  }
  window.dispatchEvent(
    new CustomEvent<string>(EVENT_NAME, { detail: campaignId }),
  );
}

export function subscribeToCampaignSelection(
  listener: (campaignId: string) => void,
): () => void {
  const handler = (event: Event): void => {
    listener((event as CustomEvent<string>).detail ?? "");
  };
  window.addEventListener(EVENT_NAME, handler);
  return () => window.removeEventListener(EVENT_NAME, handler);
}

export function chooseAvailableCampaign(
  campaignIds: string[],
  currentCampaignId: string,
): string {
  if (currentCampaignId && campaignIds.includes(currentCampaignId)) {
    return currentCampaignId;
  }
  const stored = readSelectedCampaignId();
  if (stored && campaignIds.includes(stored)) {
    return stored;
  }
  return campaignIds[0] ?? "";
}
