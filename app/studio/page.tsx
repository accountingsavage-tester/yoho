import "./v8.css";
import "./v9.css";
import V8Studio from "./V8Studio";

export default function StudioPage() {
  return (
    <>
      <div className="v9-studio-ambient" aria-hidden="true" />
      <div className="v9-studio-shell">
        <V8Studio />
      </div>
      <a className="v9-studio-copilot" href="/ai" aria-label="Open Yoho AI Copilot">
        <i aria-hidden="true" />
        <span>AI Copilot</span>
        <b>↗</b>
      </a>
    </>
  );
}
