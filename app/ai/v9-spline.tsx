"use client";

import { useEffect, useRef } from "react";

export default function V9SplineScene() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let frame = 0;
    const started = performance.now();
    const tick = (now: number) => {
      const t = (now - started) / 1000;
      el.style.setProperty("--mx", `${50 + Math.sin(t * 0.28) * 10}%`);
      el.style.setProperty("--my", `${45 + Math.cos(t * 0.22) * 8}%`);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);
  return <div ref={ref} className="v9-spline-scene" aria-hidden="true"><div className="v9-orb v9-orb-a"/><div className="v9-orb v9-orb-b"/><div className="v9-ring"/></div>;
}
