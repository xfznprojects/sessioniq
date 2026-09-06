import { Pause, Play, SkipBack, SkipForward, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { SessionAsset } from "../types";
import { formatSeconds } from "../lib/utils";
import { Button } from "./ui";

type Resume = { id?: string; time?: number };
function readResume(): Resume {
  try {
    const data = JSON.parse(localStorage.getItem("sessioniq-resume") ?? "{}");
    return data && typeof data === "object" ? data : {};
  }
  catch { return {}; }
}

/** Imperative jump request: play this track from a time position. */
export type PlayerSeek = { id: string; time: number; nonce: number };

export function Player({
  assets,
  selected,
  seek
}: {
  assets: SessionAsset[];
  selected?: SessionAsset;
  seek?: PlayerSeek | null;
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const [resume] = useState(readResume);
  const [trackId, setTrackId] = useState<string | undefined>(resume.id);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [error, setError] = useState("");
  const lastSaved = useRef(0);
  const loadedTrack = useRef<string | undefined>(undefined);
  const resumed = useRef(false);
  const previousSelection = useRef<string | undefined>(undefined);
  // A seek for a track that is still loading; applied once metadata is ready.
  const pendingSeek = useRef<PlayerSeek | null>(null);
  const appliedSeek = useRef(0);
  const tracks = assets.filter(a => a.display_type === "Audio" && a.media_url);
  const track = tracks.find(a => a.id === trackId) ?? tracks[0];

  useEffect(() => {
    if (selected?.id === previousSelection.current) return;
    previousSelection.current = selected?.id;
    if (selected?.display_type === "Audio") setTrackId(selected.id);
  }, [selected?.id, selected?.display_type]);

  useEffect(() => {
    loadedTrack.current = undefined;
    setPlaying(false); setTime(0); setDuration(0); setError("");
    if (audio.current) audio.current.volume = volume;
  }, [track?.id, track?.media_url]);

  useEffect(() => {
    if (!seek || seek.nonce === appliedSeek.current) return;
    appliedSeek.current = seek.nonce;
    pendingSeek.current = seek;
    setTrackId(seek.id);
    // Track already loaded: jump immediately.
    if (loadedTrack.current === seek.id && audio.current && audio.current.duration) {
      audio.current.currentTime = Math.max(0, Math.min(seek.time, audio.current.duration));
      void audio.current.play().catch(() => setError("Could not play this file."));
      pendingSeek.current = null;
    }
  }, [seek]);

  function applyPendingSeek() {
    const request = pendingSeek.current;
    const element = audio.current;
    if (!request || !element) return;
    pendingSeek.current = null;
    element.currentTime = Math.max(0, Math.min(request.time, element.duration || request.time));
    void element.play().catch(() => setError("Could not play this file."));
  }

  function remember() {
    if (!loadedTrack.current || !audio.current) return;
    try { localStorage.setItem("sessioniq-resume", JSON.stringify({ id: loadedTrack.current, time: audio.current.currentTime })); }
    catch { /* Playback works even when storage is unavailable. */ }
  }
  async function toggle() {
    if (!audio.current || !track) return;
    if (!audio.current.paused) audio.current.pause();
    else {
      try { await audio.current.play(); setError(""); }
      catch { setError("Could not play this file. Try another track or check the audio format."); }
    }
  }
  function step(offset: number) {
    if (!tracks.length) return;
    remember();
    const index = tracks.findIndex(a => a.id === track?.id);
    setTrackId(tracks[(index + offset + tracks.length) % tracks.length].id);
  }
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, button, dialog, [contenteditable], [role=dialog]")) return;
      if (event.code === "Space") { event.preventDefault(); void toggle(); }
      if (event.altKey && event.key === "ArrowRight") { event.preventDefault(); step(1); }
      if (event.altKey && event.key === "ArrowLeft") { event.preventDefault(); step(-1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!track) return null;
  return (
    <section aria-label="Audio player" className="shrink-0 border-t border-border bg-card px-4 py-3">
      <audio ref={audio} src={track.media_url!} preload="metadata"
        onLoadedMetadata={() => {
          const element = audio.current!;
          loadedTrack.current = track.id;
          setDuration(Number.isFinite(element.duration) ? element.duration : 0);
          if (!resumed.current && resume.id === track.id && Number.isFinite(resume.time)) {
            element.currentTime = Math.max(0, Math.min(resume.time!, element.duration || 0));
          }
          resumed.current = true;
          applyPendingSeek();
        }}
        onTimeUpdate={() => {
          setTime(audio.current?.currentTime ?? 0);
          if (Date.now() - lastSaved.current > 2000) { remember(); lastSaved.current = Date.now(); }
        }}
        onPlay={() => setPlaying(true)} onPause={() => { setPlaying(false); remember(); }}
        onEnded={() => { setPlaying(false); remember(); }}
        onError={() => { setPlaying(false); setError("Audio unavailable. Check that the file still exists."); }}
      />
      <div className="flex flex-wrap items-center gap-4">
        <div className="min-w-0 w-48">
          <p className="truncate text-sm font-semibold" title={track.file_name}>{track.file_name}</p>
          <p className="truncate text-xs text-muted-foreground">{track.project_name}</p>
        </div>
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" aria-label="Previous track" disabled={tracks.length < 2} onClick={() => step(-1)}><SkipBack className="size-4" /></Button>
          <Button size="icon" variant="primary" aria-label={playing ? "Pause audio" : "Play audio"} onClick={() => void toggle()}>{playing ? <Pause className="size-4" /> : <Play className="size-4" />}</Button>
          <Button size="icon" variant="ghost" aria-label="Next track" disabled={tracks.length < 2} onClick={() => step(1)}><SkipForward className="size-4" /></Button>
        </div>
        <div className="flex min-w-40 flex-1 items-center gap-3">
          <span className="text-xs tabular-nums text-muted-foreground">{formatSeconds(time)}</span>
          <input type="range" aria-label="Playback position" min={0} max={duration || 1} step={0.1} value={Math.min(time, duration || 1)} disabled={!duration}
            className="w-full accent-accent" onChange={e => {
              if (!audio.current) return;
              audio.current.currentTime = Number(e.target.value);
              setTime(audio.current.currentTime);
              // Explicit seeks must survive refresh even while paused and within
              // the periodic timeupdate save throttle.
              remember();
            }} />
          <span className="text-xs tabular-nums text-muted-foreground">{formatSeconds(duration)}</span>
        </div>
        <label className="hidden items-center gap-2 md:flex"><Volume2 className="size-4 text-muted-foreground" />
          <input type="range" aria-label="Playback volume" min={0} max={1} step={0.01} value={volume} className="w-20 accent-accent"
            onChange={e => { setVolume(Number(e.target.value)); if (audio.current) audio.current.volume = Number(e.target.value); }} />
        </label>
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
    </section>
  );
}
