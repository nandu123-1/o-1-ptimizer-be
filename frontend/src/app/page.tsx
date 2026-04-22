import OptimizerWorkbench from "@/components/OptimizerWorkbench";
import ThemeToggle from "@/components/ThemeToggle";

export default function Home() {
  return (
    <main className="page-root">
      <div className="top-bar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            ⟡
          </span>
          <span>DSA Tutor</span>
        </div>
        <ThemeToggle />
      </div>

      <section className="hero">
        <p className="hero-badge">
          <span className="hero-badge-dot" aria-hidden="true" />
          CrewAI + FastAPI + Recharts
        </p>
        <h1>DSA Tutor and C++ Code Optimizer</h1>
        <p>
          Write or paste brute-force code, run an optimizer swarm, and inspect
          complexity reduction with chart-ready JSON data.
        </p>
        <div className="hero-stats">
          <span className="hero-stat">
            <strong>4</strong> specialist agents
          </span>
          <span className="hero-stat">
            <strong>g++</strong> feedback loop
          </span>
          <span className="hero-stat">
            <strong>Recharts</strong> visualization
          </span>
        </div>
      </section>

      <OptimizerWorkbench />
    </main>
  );
}
