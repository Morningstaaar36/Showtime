/** Replay clock. Read with usePlayback.getState() inside useFrame to avoid React re-renders. */
import { create } from "zustand";

interface PlaybackState {
  t: number;
  duration: number;
  playing: boolean;
  speed: number;
  setT: (t: number) => void;
  setDuration: (d: number) => void;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  setSpeed: (s: number) => void;
  tick: (dt: number) => void;
  reset: () => void;
}

export const usePlayback = create<PlaybackState>((set, get) => ({
  t: 0,
  duration: 0,
  playing: false,
  speed: 4,
  setT: (t) => set({ t: Math.max(0, Math.min(t, get().duration)) }),
  setDuration: (duration) => set({ duration, t: Math.min(get().t, duration) }),
  play: () => {
    const { t, duration } = get();
    set({ playing: true, t: t >= duration ? 0 : t });
  },
  pause: () => set({ playing: false }),
  toggle: () => (get().playing ? get().pause() : get().play()),
  setSpeed: (speed) => set({ speed }),
  tick: (dt) => {
    const s = get();
    if (!s.playing) return;
    const t = s.t + dt * s.speed;
    if (t >= s.duration) set({ t: s.duration, playing: false });
    else set({ t });
  },
  reset: () => set({ t: 0, playing: false, duration: 0 }),
}));
