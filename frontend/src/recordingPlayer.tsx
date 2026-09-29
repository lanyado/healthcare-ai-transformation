import { useEffect, useRef, useState } from "react";

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

type Props = {
  src: string;
  title: string;
  subtitle?: string;
  onTime?: (seconds: number) => void;
  onDuration?: (seconds: number) => void;
  onClose: () => void;
};

export function RecordingPlayer({ src, title, subtitle, onTime, onDuration, onClose }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const audio = audioRef.current;
    void audio?.play().catch(() => setPlaying(false));
    return () => {
      window.removeEventListener("keydown", onKey);
      audio?.pause();
    };
  }, [onClose, src]);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void audio.play();
    else audio.pause();
  };

  const seekTo = (time: number) => {
    const audio = audioRef.current;
    if (!audio || !Number.isFinite(audio.duration)) return;
    audio.currentTime = Math.min(Math.max(time, 0), audio.duration);
    setCurrent(audio.currentTime);
    onTime?.(audio.currentTime);
  };

  return (
    <div className="recording-overlay" onClick={onClose} role="presentation">
      <div
        className="recording-card"
        role="dialog"
        aria-labelledby="recording-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="recording-close" type="button" onClick={onClose} aria-label="Close recording">
          ×
        </button>
        <audio
          ref={audioRef}
          src={src}
          preload="auto"
          onLoadedMetadata={() => {
            const length = audioRef.current?.duration || 0;
            setDuration(length);
            onDuration?.(length);
          }}
          onTimeUpdate={() => {
            const audio = audioRef.current;
            if (!audio) return;
            setCurrent(audio.currentTime);
            setDuration(audio.duration || 0);
            onTime?.(audio.currentTime);
          }}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
        />
        <div className="recording-cover" aria-hidden="true">
          {[8, 14, 22, 16, 26, 12, 20, 10, 24, 18, 13, 21].map((height, index) => (
            <span
              key={index}
              className={playing ? "is-playing" : ""}
              style={{ height: `${height * 4}px`, animationDelay: `${index * 80}ms` }}
            />
          ))}
        </div>
        <h2 id="recording-title">{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
        <input
          className="recording-track"
          type="range"
          min={0}
          max={duration || 0}
          step={0.1}
          value={current}
          aria-label="Seek recording"
          disabled={!duration}
          onChange={(event) => seekTo(Number(event.target.value))}
        />
        <div className="recording-times">
          <span>{formatTime(current)}</span>
          <span>{formatTime(duration)}</span>
        </div>
        <div className="recording-controls">
          <button className="recording-play" type="button" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
            {playing ? "❚❚" : "▶"}
          </button>
        </div>
      </div>
    </div>
  );
}
