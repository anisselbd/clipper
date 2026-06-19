// Client de l'API moteur. Le front ne parle QUE HTTP/JSON sur cette base :
// c'est exactement la frontiere qu'on aura en SaaS (front Vercel -> worker GPU).

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8008";

export type Job = {
  id: string;
  url: string;
  status: "queued" | "running" | "done" | "error";
  step?: string | null;
  progress: number;
  error?: string | null;
  created_at: string;
  updated_at: string;
  clip_count: number;
};

export type Clip = {
  id: string;
  clip_id: string;
  title?: string | null;
  hook_score?: number | null;
  duration?: number | null;
  width?: number | null;
  height?: number | null;
  start?: number | null;
  end?: number | null;
  reason?: string | null;
  selection_source?: string | null;
  url?: string | null;
  thumb_url?: string | null;
  file_path?: string | null;
  social?: SocialKit | null;
};

export type SocialKit = {
  caption?: string;
  youtube_title?: string;
  hashtags?: string[];
  source?: string;
  platforms?: {
    tiktok?: { caption?: string };
    shorts?: { title?: string; description?: string };
    reels?: { caption?: string };
  };
};

export type Preflight = {
  subtitle_backend: string;
  video_encoder: string;
  face_backend: string;
  selection_backend: string;
  llm_reachable: boolean;
  warnings: string[];
  [k: string]: unknown;
};

export type CreateJobInput = {
  url: string;
  num_clips?: number;
  lang?: string;
  whisper_model?: string;
  reframe_mode?: string;
};

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function getHealth(): Promise<{ status: string; preflight: Preflight }> {
  return jsonOrThrow(await fetch(`${API_BASE}/health`));
}

export async function createJob(input: CreateJobInput): Promise<Job> {
  return jsonOrThrow(
    await fetch(`${API_BASE}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    })
  );
}

export async function getJob(id: string): Promise<Job> {
  return jsonOrThrow(await fetch(`${API_BASE}/jobs/${id}`));
}

export async function getClips(id: string): Promise<Clip[]> {
  return jsonOrThrow(await fetch(`${API_BASE}/jobs/${id}/clips`));
}

export async function revealJob(id: string): Promise<void> {
  await fetch(`${API_BASE}/jobs/${id}/reveal`, { method: "POST" });
}

export function jobEventsUrl(id: string): string {
  return `${API_BASE}/jobs/${id}/events`;
}

type TauriGlobal = {
  core?: { invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> };
};

function tauri(): TauriGlobal | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as unknown as { __TAURI__?: TauriGlobal }).__TAURI__;
}

/** Enregistre un clip. Dans l'app desktop : copie vers ~/Telechargements +
 * revele dans le Finder (sans navigation du webview). Dans un navigateur :
 * telechargement classique. Renvoie le chemin enregistre (desktop) ou null. */
export async function saveClip(clip: Clip): Promise<string | null> {
  const name = `${(clip.title || clip.clip_id).slice(0, 60).trim() || clip.clip_id}.mp4`;
  const t = tauri();
  if (t?.core?.invoke && clip.file_path) {
    return (await t.core.invoke("save_clip", { src: clip.file_path, name })) as string;
  }
  if (clip.url) {
    const a = document.createElement("a");
    a.href = clip.url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  return null;
}
