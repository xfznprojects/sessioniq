import type { SessionAsset } from "../types";

export function assetsInScope(
  assets: SessionAsset[], project: string, collectionIds?: string[],
): SessionAsset[] {
  const ids = collectionIds ? new Set(collectionIds) : null;
  return assets.filter(asset =>
    (project === "All Projects" || asset.project_name === project || asset.project_name.startsWith(project + "/"))
    && (!ids || ids.has(asset.id)));
}
