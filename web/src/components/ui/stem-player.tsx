"use client";

import * as React from "react";
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Download,
  Headphones,
} from "lucide-react";
import { cn, formatDuration } from "@/lib/utils";
import { downloadUrl } from "@/lib/api";

/* ------------------------------------------------------------------ */
/* Lightweight sync bus so stems in the same group seek/play together  */
/* ------------------------------------------------------------------ */

type SyncEvent = { type: "seek"; time: number } | { type: "play" } | { type: "pause" };

const syncListeners = new Map<string, Set<(e: SyncEvent) => void>>();

function emit(group: string, e: SyncEvent) {
  syncListeners.get(group)?.forEach((fn) => fn(e));
}

function useSyncGroup(group: string, handler: (e: SyncEvent) => void) {
  React.useEffect(() => {
    let set = syncListeners.get(group);
    if (!set) {
      set = new Set();
      syncListeners.set(group, set);
    }
    set.add(handler);
    return () => {
      set.delete(handler);
      if (set.size === 0) syncListeners.delete(group);
    };
  }, [group, handler]);
}

/* ------------------------------------------------------------------ */
/* Shared AudioContext — one per page, reused across stem players      */
/* ------------------------------------------------------------------ */

let sharedCtx: AudioContext | null = null;
function getAudioContext(): AudioContext {
  if (!sharedCtx || sharedCtx.state === "closed") {
    sharedCtx = new (
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext
    )();
  }
  return sharedCtx;
}

/* ------------------------------------------------------------------ */
/* Waveform — decode peaks via Web Audio, fall back to a placeholder   */
/* ------------------------------------------------------------------ */

function useWaveform(url: string, color: string) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const [peaks, setPeaks] = React.useState<number[] | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    const ctx = getAudioContext();
    fetch(url)
      .then((r) => r.arrayBuffer())
      .then((buf) => ctx.decodeAudioData(buf))
      .then((audio) => {
        if (cancelled) return;
        const channel = audio.getChannelData(0);
        const bucket = Math.floor(channel.length / 240);
        const out: number[] = [];
        for (let i = 0; i < 240; i++) {
          let max = 0;
          for (let j = 0; j < bucket; j++) {
            const v = Math.abs(channel[i * bucket + j]);
            if (v > max) max = v;
          }
          out.push(max);
        }
        setPeaks(out);
      })
      .catch(() => {
        if (!cancelled) setPeaks(null);
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const g = canvas.getContext("2d");
    if (!g) return;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, w, h);
    const n = peaks?.length ?? 120;
    const bw = w / n;
    for (let i = 0; i < n; i++) {
      const v = peaks ? peaks[i] : 0.25 + 0.15 * Math.sin(i * 0.35) * Math.cos(i * 0.11);
      const bh = Math.max(2, v * h * 0.9);
      g.fillStyle = color;
      g.globalAlpha = 0.9;
      g.fillRect(i * bw + bw * 0.15, (h - bh) / 2, bw * 0.7, bh);
    }
  }, [peaks, color]);

  return canvasRef;
}

/* ------------------------------------------------------------------ */
/* StemPlayer                                                          */
/* ------------------------------------------------------------------ */

interface StemPlayerProps {
  name: string;
  url: string;
  color?: string;
  group?: string;
  onDownload?: () => void;
  className?: string;
}

export function StemPlayer({
  name,
  url,
  color = "#6366f1",
  group = "default",
  onDownload,
  className,
}: StemPlayerProps) {
  const audioRef = React.useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = React.useState(false);
  const [time, setTime] = React.useState(0);
  const [duration, setDuration] = React.useState(0);
  const [muted, setMuted] = React.useState(false);
  const [volume, setVolume] = React.useState(1);
  const canvasRef = useWaveform(downloadUrl(url), color);

  const seek = React.useCallback((t: number) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = t;
    setTime(t);
  }, []);

  useSyncGroup(group, (e) => {
    if (e.type === "seek") seek(e.time);
    if (e.type === "play") audioRef.current?.play().catch(() => {});
    if (e.type === "pause") audioRef.current?.pause();
  });

  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      emit(group, { type: "play" });
      a.play().catch(() => {});
    } else {
      emit(group, { type: "pause" });
      a.pause();
    }
  };

  const onSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const t = Number(e.target.value);
    seek(t);
    emit(group, { type: "seek", time: t });
  };

  return (
    <div
      className={cn(
        "rounded-xl border border-card-border bg-card p-3 transition-shadow hover:shadow-md",
        className,
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
            style={{ backgroundColor: `${color}22`, color }}
          >
            <Headphones className="h-3.5 w-3.5" />
          </span>
          <span className="truncate text-sm font-medium capitalize">{name}</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => {
              setMuted((m) => {
                if (audioRef.current) audioRef.current.muted = !m;
                return !m;
              });
            }}
            aria-label={muted ? "Unmute" : "Mute"}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-control hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
          >
            {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
          </button>
          {onDownload && (
            <button
              type="button"
              onClick={onDownload}
              aria-label={`Download ${name}`}
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-control hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
            >
              <Download className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      <div className="relative">
        <canvas ref={canvasRef} className="h-16 w-full rounded-lg" aria-hidden="true" />
        <button
          type="button"
          onClick={toggle}
          aria-label={playing ? "Pause" : "Play"}
          className="absolute left-1/2 top-1/2 flex h-11 w-11 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-primary-glow transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
        >
          {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 pl-0.5" />}
        </button>
      </div>

      <input
        type="range"
        min={0}
        max={duration || 0}
        step={0.1}
        value={time}
        onChange={onSeek}
        aria-label={`Seek ${name}`}
        className="mt-2 w-full accent-indigo-600"
      />
      <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
        <span>{formatDuration(time)}</span>
        <span>{formatDuration(duration)}</span>
      </div>

      <audio
        ref={audioRef}
        src={downloadUrl(url)}
        preload="metadata"
        aria-label={`Audio for ${name}`}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onVolumeChange={(e) => setVolume(e.currentTarget.volume)}
      />
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={muted ? 0 : volume}
        onChange={(e) => {
          const v = Number(e.target.value);
          setVolume(v);
          if (audioRef.current) {
            audioRef.current.volume = v;
            audioRef.current.muted = v === 0;
            setMuted(v === 0);
          }
        }}
        aria-label={`Volume ${name}`}
        className="mt-1 w-full accent-indigo-600"
      />
    </div>
  );
}