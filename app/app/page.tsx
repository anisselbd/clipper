"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  createJob,
  getClips,
  getHealth,
  getJob,
  jobEventsUrl,
  revealJob,
  type Clip,
  type CreateJobInput,
  type Preflight,
} from "@/lib/api";
import JobForm from "@/components/JobForm";
import Progress from "@/components/Progress";
import ClipGrid from "@/components/ClipGrid";

type Phase = "idle" | "running" | "done" | "error";

type RunState = {
  phase: Phase;
  step: string;
  progress: number;
  message: string;
  error: string | null;
};

type RunAction =
  | { type: "start" }
  | { type: "progress"; step?: string; progress?: number; message?: string }
  | { type: "done" }
  | { type: "error"; error: string }
  | { type: "reset" };

const INITIAL_RUN: RunState = {
  phase: "idle",
  step: "downloading",
  progress: 0,
  message: "",
  error: null,
};

function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.type) {
    case "start":
      return { phase: "running", step: "downloading", progress: 0, message: "Demarrage…", error: null };
    case "progress":
      return {
        ...state,
        step: action.step ?? state.step,
        progress: action.progress ?? state.progress,
        message: action.message ?? state.message,
      };
    case "done":
      return { ...state, phase: "done", step: "done", progress: 1 };
    case "error":
      return { ...state, phase: "error", error: action.error };
    case "reset":
      return INITIAL_RUN;
    default:
      return state;
  }
}

export default function Home() {
  const [run, dispatch] = useReducer(runReducer, INITIAL_RUN);
  const [clips, setClips] = useState<Clip[]>([]);
  const [health, setHealth] = useState<Preflight | null>(null);

  const jobIdRef = useRef<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Au lancement de l'app desktop, le moteur met quelques secondes a demarrer :
    // on reessaie /health jusqu'a ce qu'il reponde.
    let cancelled = false;
    let tries = 0;
    const tick = async () => {
      try {
        const h = await getHealth();
        if (!cancelled) setHealth(h.preflight);
      } catch {
        if (!cancelled && tries++ < 30) setTimeout(tick, 1000);
      }
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, []);

  const cleanup = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  const finish = useCallback(
    async (id: string) => {
      try {
        setClips(await getClips(id));
      } catch {
        /* ignore */
      }
      dispatch({ type: "done" });
      cleanup();
    },
    [cleanup]
  );

  const start = useCallback(
    async (input: CreateJobInput) => {
      setClips([]);
      dispatch({ type: "start" });
      let job;
      try {
        job = await createJob(input);
      } catch (e) {
        dispatch({ type: "error", error: e instanceof Error ? e.message : "Echec de creation du job" });
        return;
      }
      jobIdRef.current = job.id;

      // SSE : progression en direct
      const es = new EventSource(jobEventsUrl(job.id));
      esRef.current = es;
      es.addEventListener("progress", (e) => {
        const d = JSON.parse((e as MessageEvent).data);
        dispatch({ type: "progress", step: d.step, progress: d.progress, message: d.message });
      });
      es.addEventListener("clip", async () => {
        try {
          setClips(await getClips(job.id));
        } catch {
          /* ignore */
        }
      });
      es.addEventListener("done", () => finish(job.id));
      es.addEventListener("job_error", (e) => {
        const d = JSON.parse((e as MessageEvent).data || "{}");
        dispatch({ type: "error", error: d.error || "Le traitement a echoue" });
        cleanup();
      });

      // Filet de securite : reconciliation par polling si un evenement SSE est manque.
      pollRef.current = setInterval(async () => {
        try {
          const j = await getJob(job.id);
          if (j.status === "done") finish(job.id);
          else if (j.status === "error") {
            dispatch({ type: "error", error: j.error || "Le traitement a echoue" });
            cleanup();
          }
        } catch {
          /* ignore */
        }
      }, 5000);
    },
    [finish, cleanup]
  );

  const reset = useCallback(() => {
    cleanup();
    jobIdRef.current = null;
    setClips([]);
    dispatch({ type: "reset" });
  }, [cleanup]);

  const onReveal = () => jobIdRef.current && revealJob(jobIdRef.current);

  return (
    <main className="w-full max-w-5xl mx-auto px-5 py-12 sm:py-16">
      <header className="mb-10 text-center">
        <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight">clipper</h1>
        <p className="mt-3 text-[var(--muted)] text-[15px]">
          Transforme une video en clips verticaux 9:16 sous-titres. 100% en local.
        </p>
      </header>

      {run.phase === "idle" && (
        <div className="max-w-2xl mx-auto">
          <JobForm onSubmit={start} disabled={false} health={health} />
        </div>
      )}

      {run.phase === "running" && (
        <div className="flex flex-col gap-8">
          <div className="max-w-2xl mx-auto w-full">
            <Progress step={run.step} progress={run.progress} message={run.message} />
          </div>
          {clips.length > 0 && (
            <ClipGrid clips={clips} running onReveal={onReveal} onReset={reset} />
          )}
        </div>
      )}

      {run.phase === "done" && (
        <ClipGrid clips={clips} running={false} onReveal={onReveal} onReset={reset} />
      )}

      {run.phase === "error" && (
        <div className="max-w-2xl mx-auto glass rounded-3xl p-8 text-center fade-up">
          <p className="text-lg font-medium mb-2">Le traitement a echoue</p>
          <p className="text-[var(--muted)] text-sm mb-6 break-words">{run.error}</p>
          <button type="button" onClick={reset} className="btn-primary rounded-2xl px-6 py-3 font-semibold">
            Reessayer
          </button>
        </div>
      )}

      <footer className="mt-16 text-center text-[12px] text-[var(--muted)]">
        Moteur local ·{" "}
        {health
          ? `selection ${health.selection_backend === "llm" ? "LLM" : "heuristique"}`
          : "…"}{" "}
        · sous-titres {health?.subtitle_backend ?? "…"}
      </footer>
    </main>
  );
}
