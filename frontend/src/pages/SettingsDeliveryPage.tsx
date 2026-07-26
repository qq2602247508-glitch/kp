import { useEffect, useMemo, useState, type ChangeEvent, type ReactElement } from "react";

import {
  createBackup,
  exportCampaign,
  getCampaignSourcePacks,
  getDeliveryReadiness,
  importCampaign,
  listCampaigns,
  updateCampaignSourcePacks,
  verifyBackup,
} from "../api/client";
import type {
  Campaign,
  CampaignExport,
  CampaignSourcePacks,
  DeliveryReadiness,
} from "../api/types";
import {
  chooseAvailableCampaign,
  selectCampaign,
  subscribeToCampaignSelection,
} from "../state/campaignSelection";

const STATUS_LABELS: Record<string, string> = {
  ready: "就绪",
  missing: "缺失",
  failed: "失败",
  incompatible: "不兼容",
  unavailable: "不可用",
};

export function SettingsDeliveryPage(): ReactElement {
  const [readiness, setReadiness] = useState<DeliveryReadiness | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [packSettings, setPackSettings] = useState<CampaignSourcePacks | null>(null);
  const [selectedPacks, setSelectedPacks] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [backupPath, setBackupPath] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getDeliveryReadiness(controller.signal),
      listCampaigns(controller.signal),
    ])
      .then(([nextReadiness, nextCampaigns]) => {
        setReadiness(nextReadiness);
        setCampaigns(nextCampaigns);
        const selected = chooseAvailableCampaign(
          nextCampaigns.map((item) => item.campaign_id),
          "",
        );
        setCampaignId(selected);
        selectCampaign(selected);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(error instanceof Error ? error.message : "读取交付状态失败。");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(
    () =>
      subscribeToCampaignSelection((nextCampaignId) => {
        setCampaignId((current) =>
          current === nextCampaignId ? current : nextCampaignId,
        );
      }),
    [],
  );

  useEffect(() => {
    if (!campaignId) {
      setPackSettings(null);
      return;
    }
    const controller = new AbortController();
    getCampaignSourcePacks(campaignId, controller.signal)
      .then((settings) => {
        setPackSettings(settings);
        setSelectedPacks(new Set(settings.enabled_source_pack_ids));
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(error instanceof Error ? error.message : "读取资料包失败。");
        }
      });
    return () => controller.abort();
  }, [campaignId]);

  const readinessRows = useMemo(() => {
    if (!readiness) return [];
    return [
      ["SQLite 战役数据库", readiness.database.status, "独立 COC7 数据库"],
      [
        "规则来源",
        readiness.sources.status,
        `${readiness.sources.ready_packs} 个资料包就绪`,
      ],
      [
        "Qdrant 本地索引",
        readiness.vector_index.status,
        `${readiness.vector_index.chunk_count} 个规则片段`,
      ],
      [
        readiness.models.embedding.name,
        readiness.models.embedding.status,
        "本地向量模型；本页面不会下载",
      ],
      [
        readiness.models.completion.name,
        readiness.models.completion.status,
        "本地回答模型；本页面不会下载",
      ],
    ];
  }, [readiness]);

  async function savePacks(): Promise<void> {
    if (!packSettings) return;
    setBusy(true);
    setMessage("");
    try {
      const updated = await updateCampaignSourcePacks(
        packSettings.campaign_id,
        packSettings.campaign_version,
        [...selectedPacks],
      );
      setPackSettings(updated);
      setSelectedPacks(new Set(updated.enabled_source_pack_ids));
      setMessage("战役资料包已保存；默认核心来源保持启用。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败。");
    } finally {
      setBusy(false);
    }
  }

  async function downloadExport(): Promise<void> {
    if (!campaignId) return;
    setBusy(true);
    try {
      const bundle = await exportCampaign(campaignId);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `coc7e-campaign-${campaignId}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage("战役导出包已生成。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "导出失败。");
    } finally {
      setBusy(false);
    }
  }

  async function uploadImport(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const parsed = JSON.parse(await file.text()) as CampaignExport;
      const result = await importCampaign(parsed);
      setMessage(`已原子导入战役 ${result.campaign_id}；不会覆盖已有战役。`);
      setCampaigns(await listCampaigns());
      setCampaignId(result.campaign_id);
      selectCampaign(result.campaign_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "导入包无效。");
    } finally {
      event.target.value = "";
      setBusy(false);
    }
  }

  async function makeBackup(): Promise<void> {
    setBusy(true);
    try {
      const backup = await createBackup();
      setBackupPath(backup.path);
      setMessage("一致性备份已完成。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "备份失败。");
    } finally {
      setBusy(false);
    }
  }

  async function validateBackup(): Promise<void> {
    if (!backupPath) return;
    setBusy(true);
    try {
      const result = await verifyBackup(backupPath);
      setMessage(
        result.valid
          ? "备份校验通过。这里只验证，不会隐式覆盖当前数据。"
          : `备份校验失败：${result.mismatches.join("、")}`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "校验失败。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="delivery-workspace">
      <section className="opening-card">
        <div>
          <p className="eyebrow">LOCAL DELIVERY CONTROL</p>
          <h2>设置、资料与可恢复交付</h2>
          <p>
            检查本机依赖，按战役启用 COC7 资料包，并创建带校验清单的一致性备份。
            所有检测只读，不会自动下载模型或浏览器。
          </p>
        </div>
        <span className={readiness?.ready ? "delivery-ready" : "delivery-warning"}>
          {readiness?.ready ? "全部就绪" : "需要检查"}
        </span>
      </section>

      <section className="delivery-panel">
        <h3>运行就绪度</h3>
        <div className="readiness-grid">
          {readinessRows.map(([name, status, detail]) => (
            <article key={name}>
              <strong>{name}</strong>
              <span data-status={status}>{STATUS_LABELS[status] ?? status}</span>
              <small>{detail}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="delivery-panel">
        <h3>战役资料包</h3>
        <label>
          当前战役
          <select
            value={campaignId}
            onChange={(event) => {
              setCampaignId(event.target.value);
              selectCampaign(event.target.value);
            }}
          >
            <option value="">请选择战役</option>
            {campaigns.map((campaign) => (
              <option key={campaign.campaign_id} value={campaign.campaign_id}>
                {campaign.title}
              </option>
            ))}
          </select>
        </label>
        <div className="pack-toggle-list">
          {packSettings?.packs.map((pack) => (
            <label className={!pack.compatible ? "pack-incompatible" : ""} key={pack.pack_id}>
              <input
                checked={selectedPacks.has(pack.pack_id)}
                disabled={!pack.compatible || pack.required_default}
                onChange={(event) => {
                  const next = new Set(selectedPacks);
                  if (event.target.checked) next.add(pack.pack_id);
                  else next.delete(pack.pack_id);
                  setSelectedPacks(next);
                }}
                type="checkbox"
              />
              <span>
                <strong>{pack.title}</strong>
                <small>
                  {pack.edition} · {pack.kind} · {pack.version}
                  {pack.required_default ? " · 默认权威" : ""}
                  {!pack.compatible ? " · 与当前时代不兼容" : ""}
                </small>
              </span>
            </label>
          ))}
        </div>
        <button disabled={!packSettings || busy} onClick={() => void savePacks()} type="button">
          保存资料包
        </button>
      </section>

      <section className="delivery-panel delivery-actions">
        <h3>导出、导入与备份</h3>
        <div>
          <button disabled={!campaignId || busy} onClick={() => void downloadExport()} type="button">
            导出当前战役 JSON
          </button>
          <label className="file-action">
            导入 COC7 战役包
            <input accept="application/json,.json" disabled={busy} onChange={(event) => void uploadImport(event)} type="file" />
          </label>
          <button disabled={busy} onClick={() => void makeBackup()} type="button">
            创建一致性备份
          </button>
        </div>
        <label>
          备份路径（只做校验）
          <input value={backupPath} onChange={(event) => setBackupPath(event.target.value)} />
        </label>
        <button disabled={!backupPath || busy} onClick={() => void validateBackup()} type="button">
          校验备份
        </button>
        <p className="delivery-safety">
          导入严格要求 product=local-coc-kp-assistant、ruleset=coc7e 和受支持的
          schema_version；同 ID 战役不会被覆盖。备份校验不会执行恢复。
        </p>
      </section>

      {message ? <p className="delivery-message" role="status">{message}</p> : null}
    </div>
  );
}
