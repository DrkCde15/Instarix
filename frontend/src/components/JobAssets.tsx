import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../api";
import { useToast } from "../toast";
import { formatBytes } from "../utils";

interface JobAsset {
  id: string;
  media_pk: string;
  kind: string;
  size_bytes: number;
  content_type: string;
}

const EXTENSIONS: Record<string, string> = {
  "image/jpeg": ".jpg",
  "image/png": ".png",
  "image/webp": ".webp",
  "video/mp4": ".mp4",
  "video/quicktime": ".mov",
};

function assetsFrom(result: Record<string, unknown> | null): JobAsset[] {
  const raw = result?.assets;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (item): item is JobAsset =>
      typeof item === "object" &&
      item !== null &&
      typeof (item as JobAsset).id === "string" &&
      typeof (item as JobAsset).media_pk === "string",
  );
}

export function JobAssets({ result }: { result: Record<string, unknown> | null }) {
  const { notify } = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const assets = assetsFrom(result);

  if (assets.length === 0) return null;

  async function download(asset: JobAsset) {
    setBusy(asset.id);
    try {
      const extension = EXTENSIONS[asset.content_type] ?? "";
      await api.downloadAsset(
        asset.id,
        `${asset.media_pk}_${asset.kind}${extension}`,
      );
    } catch (err) {
      notify(
        err instanceof ApiError ? err.message : "Falha ao baixar o arquivo.",
        "error",
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="job-assets">
      <span className="label">Arquivos baixados</span>
      <div className="inline-actions">
        {assets.map((asset) => (
          <button
            key={asset.id}
            type="button"
            className="button button-ghost button-small"
            onClick={() => void download(asset)}
            disabled={busy !== null}
          >
            {busy === asset.id ? (
              <Loader2 size={13} className="spin" />
            ) : (
              <Download size={13} />
            )}
            {asset.kind} · {formatBytes(asset.size_bytes)}
          </button>
        ))}
      </div>
    </div>
  );
}
