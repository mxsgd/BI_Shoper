/** Static demo mode: the app reads pre-generated JSON files instead of calling a backend.
 *  Enabled by `vite build --mode demo` (see .env.demo). Files come from `python -m app.demo.snapshot`. */
export const STATIC_DEMO = import.meta.env.VITE_STATIC_DEMO === "1";

/** Must match snapshot_name() in backend/app/demo/snapshot.py. */
export function snapshotName(path: string, params: Record<string, string | number | undefined | null>): string {
  const base = path.replace(/^\/+|\/+$/g, "").replace(/\//g, "_");
  const parts = Object.entries(params)
    .filter(([k, v]) => v !== undefined && v !== null && k !== "store_id")
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([k, v]) => `__${k}-${v}`);
  return base + parts.join("");
}

export async function getSnapshot<T>(
  path: string,
  params: Record<string, string | number | undefined | null>,
): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}demo-data/${snapshotName(path, params)}.json`);
  if (!res.ok) throw new Error("Not available in the static demo");
  return res.json();
}

export interface DemoManifest {
  generated_at: string;
  as_of: string;
  files: number;
}

export async function getManifest(): Promise<DemoManifest | null> {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}demo-data/manifest.json`);
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

export function readOnlyError(): Error {
  return new Error("This is a read-only static demo.");
}
