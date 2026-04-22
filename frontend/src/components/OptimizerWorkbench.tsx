"use client";

import MonacoEditor, { loader as monacoLoader } from "@monaco-editor/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

if (typeof window !== "undefined") {
  monacoLoader.config({ paths: { vs: "/monaco-vs" } });
}
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type {
  ApiErrorPayload,
  OptimizeCodeResponse,
  OptimizeCodeRequest,
} from "@/lib/contracts";
import { useTheme } from "@/lib/useTheme";

const DEFAULT_CPP_CODE = `#include <bits/stdc++.h>
using namespace std;

int main() {
    vector<int> nums = {4, 2, 7, 1, 9, 3};
    int target = 10;

    for (int i = 0; i < (int)nums.size(); i++) {
        for (int j = i + 1; j < (int)nums.size(); j++) {
            if (nums[i] + nums[j] == target) {
                cout << i << " " << j << "\\n";
            }
        }
    }

    return 0;
}
`;

const PROGRESS_STEPS = [
  "Parsing source and analyzing complexity",
  "Researching optimal algorithms",
  "Rewriting and validating with g++",
  "Generating visualization payload",
] as const;

function normalizeErrorMessage(payload: unknown): string {
  if (!payload || typeof payload !== "object") {
    return "Optimization failed with an unknown response.";
  }

  const candidate = payload as ApiErrorPayload;

  if (typeof candidate.detail === "string" && candidate.detail.trim().length > 0) {
    return candidate.detail;
  }

  if (typeof candidate.error === "string" && candidate.error.trim().length > 0) {
    return candidate.error;
  }

  return "Optimization failed without a readable error payload.";
}

function isOptimizeResponse(payload: unknown): payload is OptimizeCodeResponse {
  if (!payload || typeof payload !== "object") {
    return false;
  }

  const candidate = payload as Partial<OptimizeCodeResponse>;
  return (
    typeof candidate.request_id === "string" &&
    typeof candidate.result === "object" &&
    candidate.result !== null
  );
}

function formatCompact(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact" }).format(value);
}

interface CopyButtonProps {
  text: string;
  label?: string;
}

function CopyButton({ text, label = "Copy" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const onCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }, [text]);

  return (
    <button
      type="button"
      className={copied ? "copy-button copied" : "copy-button"}
      onClick={onCopy}
      aria-label={copied ? "Copied to clipboard" : `${label} to clipboard`}
    >
      <span aria-hidden="true">{copied ? "✓" : "⧉"}</span>
      <span>{copied ? "Copied" : label}</span>
    </button>
  );
}

function ProgressTracker() {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setStepIndex((current) =>
        current < PROGRESS_STEPS.length - 1 ? current + 1 : current,
      );
    }, 9000);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <div className="progress-panel" role="status" aria-live="polite">
      <div className="progress-title">
        <span className="spinner" aria-hidden="true" />
        <span>Running multi-agent swarm...</span>
      </div>
      <ol className="progress-steps">
        {PROGRESS_STEPS.map((label, index) => {
          let state = "";
          if (index < stepIndex) state = "done";
          else if (index === stepIndex) state = "active";
          return (
            <li
              className={state ? `progress-step ${state}` : "progress-step"}
              key={label}
            >
              <span className="progress-step-bullet" aria-hidden="true">
                {index < stepIndex ? "✓" : index + 1}
              </span>
              <span>{label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

const CODE_FILE_EXTENSIONS = [
  ".cpp",
  ".cc",
  ".cxx",
  ".c",
  ".h",
  ".hpp",
  ".hh",
  ".txt",
];
const MAX_CODE_FILE_BYTES = 200_000;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

type EditorMode = "editor" | "plain";

export default function OptimizerWorkbench() {
  const [cppCode, setCppCode] = useState(DEFAULT_CPP_CODE);
  const [stdinData, setStdinData] = useState("");
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [response, setResponse] = useState<OptimizeCodeResponse | null>(null);
  const [useLogScale, setUseLogScale] = useState(true);
  const [editorMode, setEditorMode] = useState<EditorMode>("editor");
  const [isExtractingImage, setIsExtractingImage] = useState(false);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);

  const theme = useTheme();
  const monacoTheme = theme === "dark" ? "vs-dark" : "vs";

  const visualizationPoints = useMemo(
    () => response?.result.visualization.points ?? [],
    [response],
  );

  const canSubmit = cppCode.trim().length > 0 && !isLoading;

  const onOptimize = useCallback(async () => {
    if (cppCode.trim().length === 0) {
      setErrorMessage("Provide C++ source code before optimizing.");
      return;
    }
    if (isLoading) {
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    const payload: OptimizeCodeRequest = {
      cpp_code: cppCode,
      stdin_data: stdinData,
      max_self_correction_attempts: maxAttempts,
    };

    try {
      const optimizeResponse = await fetch("/api/optimize", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const rawBody = await optimizeResponse.text();
      const parsedBody: unknown =
        rawBody.length > 0 ? JSON.parse(rawBody) : null;

      if (!optimizeResponse.ok) {
        setResponse(null);
        setErrorMessage(normalizeErrorMessage(parsedBody));
        return;
      }

      if (!isOptimizeResponse(parsedBody)) {
        setResponse(null);
        setErrorMessage("Optimizer returned an unexpected JSON shape.");
        return;
      }

      setResponse(parsedBody);
    } catch (error) {
      setResponse(null);
      if (error instanceof Error) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage(
          "Unexpected frontend error while requesting optimization.",
        );
      }
    } finally {
      setIsLoading(false);
    }
  }, [cppCode, stdinData, maxAttempts, isLoading]);

  const onResetCode = useCallback(() => {
    setCppCode(DEFAULT_CPP_CODE);
    setUploadNotice(null);
  }, []);

  const onPickFile = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const onPickImage = useCallback(() => {
    imageInputRef.current?.click();
  }, []);

  const onFileSelected = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      if (file.size > MAX_CODE_FILE_BYTES) {
        setErrorMessage(
          `Source file exceeds ${Math.round(MAX_CODE_FILE_BYTES / 1024)} KB limit.`,
        );
        return;
      }
      try {
        const text = await file.text();
        setCppCode(text);
        setUploadNotice(`Loaded ${file.name}`);
        setErrorMessage(null);
      } catch {
        setErrorMessage("Unable to read the selected file.");
      }
    },
    [],
  );

  const onImageSelected = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      if (file.size > MAX_IMAGE_BYTES) {
        setErrorMessage("Image exceeds 8 MB limit.");
        return;
      }

      setIsExtractingImage(true);
      setErrorMessage(null);
      setUploadNotice(null);

      try {
        const form = new FormData();
        form.append("file", file, file.name || "upload");
        const res = await fetch("/api/extract-cpp-from-image", {
          method: "POST",
          body: form,
        });
        const raw = await res.text();
        const parsed: unknown = raw.length > 0 ? JSON.parse(raw) : null;
        if (!res.ok) {
          setErrorMessage(normalizeErrorMessage(parsed));
          return;
        }
        if (
          !parsed ||
          typeof parsed !== "object" ||
          typeof (parsed as { cpp_code?: unknown }).cpp_code !== "string"
        ) {
          setErrorMessage("Image extractor returned an unexpected shape.");
          return;
        }
        setCppCode((parsed as { cpp_code: string }).cpp_code);
        setUploadNotice(`Extracted C++ from ${file.name}`);
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Unexpected error while extracting code from image.",
        );
      } finally {
        setIsExtractingImage(false);
      }
    },
    [],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        if (!isLoading && cppCode.trim().length > 0) {
          void onOptimize();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOptimize, isLoading, cppCode]);

  const result = response?.result ?? null;
  const status = result?.status ?? null;

  return (
    <div className="workbench-shell">
      <section className="panel panel-input" aria-labelledby="input-panel-title">
        <header className="panel-header">
          <p className="eyebrow">Perception + Reasoning + Action</p>
          <h2 id="input-panel-title">Submit C++ and trigger optimizer swarm</h2>
          <p>
            The UI sends your code to FastAPI, then renders strict JSON from the
            multi-agent pipeline.
          </p>
        </header>

        <div>
          <label className="field-label" htmlFor="cpp-code-editor">
            <span>C++ Source Code</span>
            <button
              type="button"
              className="field-label-action"
              onClick={onResetCode}
            >
              Reset sample
            </button>
          </label>

          <div className="editor-toolbar" role="toolbar" aria-label="Code input">
            <div className="editor-mode-group" role="group" aria-label="Editor mode">
              <button
                type="button"
                className={
                  editorMode === "editor"
                    ? "chart-toggle active"
                    : "chart-toggle"
                }
                onClick={() => setEditorMode("editor")}
                aria-pressed={editorMode === "editor"}
              >
                Rich editor
              </button>
              <button
                type="button"
                className={
                  editorMode === "plain"
                    ? "chart-toggle active"
                    : "chart-toggle"
                }
                onClick={() => setEditorMode("plain")}
                aria-pressed={editorMode === "plain"}
              >
                Plain paste
              </button>
            </div>
            <div className="editor-upload-group">
              <button
                type="button"
                className="chart-toggle"
                onClick={onPickFile}
                disabled={isExtractingImage}
              >
                Upload file
              </button>
              <button
                type="button"
                className="chart-toggle"
                onClick={onPickImage}
                disabled={isExtractingImage}
              >
                {isExtractingImage ? "Extracting..." : "Upload image"}
              </button>
            </div>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept={CODE_FILE_EXTENSIONS.join(",")}
            onChange={onFileSelected}
            style={{ display: "none" }}
          />
          <input
            ref={imageInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif,image/bmp"
            onChange={onImageSelected}
            style={{ display: "none" }}
          />
          {uploadNotice ? (
            <p className="hint-text" role="status">
              {uploadNotice}
            </p>
          ) : null}

          <div className="editor-frame" id="cpp-code-editor">
            {editorMode === "editor" ? (
              <MonacoEditor
                height="460px"
                width="100%"
                loading={
                  <div className="editor-loading">Loading C++ editor...</div>
                }
                defaultLanguage="cpp"
                language="cpp"
                value={cppCode}
                onChange={(value) => setCppCode(value ?? "")}
                theme={monacoTheme}
                options={{
                  minimap: { enabled: false },
                  fontSize: 14,
                  fontLigatures: true,
                  smoothScrolling: true,
                  automaticLayout: true,
                  scrollBeyondLastLine: false,
                  tabSize: 2,
                  wordWrap: "on",
                  padding: { top: 12, bottom: 12 },
                }}
              />
            ) : (
              <textarea
                className="text-area plain-code-area"
                value={cppCode}
                onChange={(event) => setCppCode(event.target.value)}
                spellCheck={false}
                placeholder="Paste C++ code here"
              />
            )}
          </div>
        </div>

        <div className="field-grid">
          <div>
            <label className="field-label" htmlFor="stdin-data">
              <span>Optional stdin</span>
            </label>
            <textarea
              id="stdin-data"
              className="text-area"
              placeholder="Input passed to the executable, one line per value"
              value={stdinData}
              onChange={(event) => setStdinData(event.target.value)}
            />
          </div>

          <div>
            <label className="field-label" htmlFor="max-attempts">
              <span>Self-correction attempts</span>
            </label>
            <input
              id="max-attempts"
              className="number-input"
              type="number"
              min={1}
              max={8}
              value={maxAttempts}
              onChange={(event) => {
                const nextValue = Number(event.target.value);
                const safeValue = Number.isNaN(nextValue)
                  ? 3
                  : Math.max(1, Math.min(8, Math.round(nextValue)));
                setMaxAttempts(safeValue);
              }}
            />
            <p className="hint-text">Range: 1 to 8 compiler feedback loops.</p>
          </div>
        </div>

        <div className="form-actions">
          <span className="keyboard-hint">
            Press <span className="kbd">Ctrl</span> +{" "}
            <span className="kbd">Enter</span> to optimize
          </span>
          <button
            type="button"
            className="optimize-button"
            onClick={onOptimize}
            disabled={!canSubmit}
          >
            {isLoading ? (
              <>
                <span className="spinner" aria-hidden="true" />
                <span>Optimizing with CrewAI...</span>
              </>
            ) : (
              <>
                <span aria-hidden="true">⚡</span>
                <span>Optimize Code</span>
              </>
            )}
          </button>
        </div>
      </section>

      <section className="panel panel-output" aria-labelledby="output-panel-title">
        <header className="panel-header">
          <p className="eyebrow">Structured Response</p>
          <h2 id="output-panel-title">Optimization output</h2>
          <p>Each card maps directly to a strict backend JSON field.</p>
        </header>

        {errorMessage ? (
          <div className="error-banner" role="alert">
            <span className="error-banner-icon" aria-hidden="true">
              !
            </span>
            <span>{errorMessage}</span>
          </div>
        ) : null}

        {isLoading ? <ProgressTracker /> : null}

        {!response && !isLoading ? (
          <div className="empty-state">
            <p className="empty-state-title">No optimization yet</p>
            <p className="empty-state-body">
              Submit a C++ snippet to view complexity deltas, algorithm picks,
              and compile attempts.
            </p>
          </div>
        ) : null}

        {result ? (
          <div className="results-stack">
            <article className="result-card">
              <div className="card-head">
                <h3>Optimization summary</h3>
                {status ? (
                  <span
                    className={
                      status === "success"
                        ? "status-banner ok"
                        : "status-banner failed"
                    }
                  >
                    <span className="status-dot" aria-hidden="true" />
                    <span>{status === "success" ? "Success" : "Failed"}</span>
                  </span>
                ) : null}
              </div>
              <p className="card-subtitle">{result.problem_summary}</p>
              <div className="meta-row">
                <span>
                  Request ID: <code>{response!.request_id}</code>
                </span>
                <span>
                  Attempts: <code>{result.compiler_attempts.length}</code>
                </span>
              </div>
            </article>

            <article className="result-card">
              <h3>Complexity comparison</h3>
              <div className="metrics-grid">
                <div className="metric">
                  <span className="metric-label">Original Time</span>
                  <strong className="metric-value">
                    {result.complexity.original_time_complexity}
                  </strong>
                </div>
                <div className="metric">
                  <span className="metric-label">Optimized Time</span>
                  <strong className="metric-value">
                    {result.complexity.optimized_time_complexity}
                  </strong>
                </div>
                <div className="metric">
                  <span className="metric-label">Original Space</span>
                  <strong className="metric-value">
                    {result.complexity.original_space_complexity}
                  </strong>
                </div>
                <div className="metric">
                  <span className="metric-label">Optimized Space</span>
                  <strong className="metric-value">
                    {result.complexity.optimized_space_complexity}
                  </strong>
                </div>
                <div className="metric highlight">
                  <span className="metric-label">Estimated Speedup</span>
                  <strong className="metric-value">
                    {`×${result.complexity.estimated_speedup_ratio.toFixed(2)}`}
                  </strong>
                </div>
              </div>
            </article>

            <article className="result-card">
              <h3>Algorithm choices</h3>
              <ul className="pill-list">
                {result.algorithm_choices.map((choice, index) => (
                  <li key={`${choice}-${index}`}>{choice}</li>
                ))}
              </ul>
            </article>

            <article className="result-card chart-card">
              <div className="card-head">
                <h3>{result.visualization.chart_title}</h3>
                <div
                  className="chart-controls"
                  role="group"
                  aria-label="Chart scale"
                >
                  <button
                    type="button"
                    className={
                      useLogScale ? "chart-toggle" : "chart-toggle active"
                    }
                    onClick={() => setUseLogScale(false)}
                    aria-pressed={!useLogScale}
                  >
                    Linear
                  </button>
                  <button
                    type="button"
                    className={
                      useLogScale ? "chart-toggle active" : "chart-toggle"
                    }
                    onClick={() => setUseLogScale(true)}
                    aria-pressed={useLogScale}
                  >
                    Log
                  </button>
                </div>
              </div>
              <div className="chart-shell">
                <ResponsiveContainer width="100%" height={320}>
                  <LineChart
                    data={visualizationPoints}
                    margin={{ top: 8, right: 16, bottom: 8, left: 4 }}
                  >
                    <CartesianGrid
                      strokeDasharray="4 4"
                      stroke="var(--grid-color)"
                    />
                    <XAxis
                      dataKey="input_size"
                      stroke="var(--ink-muted)"
                      tickFormatter={(value) => formatCompact(Number(value))}
                    />
                    <YAxis
                      stroke="var(--ink-muted)"
                      scale={useLogScale ? "log" : "linear"}
                      domain={useLogScale ? [1, "auto"] : ["auto", "auto"]}
                      allowDataOverflow
                      tickFormatter={(value) => formatCompact(Number(value))}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "var(--panel-bg-solid)",
                        border: "1px solid var(--panel-border-strong)",
                        borderRadius: "0.6rem",
                        color: "var(--ink-strong)",
                      }}
                      formatter={(value) => formatCompact(Number(value ?? 0))}
                      labelFormatter={(label) => `Input size: ${label}`}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="brute_force_ops"
                      stroke="var(--line-brute)"
                      strokeWidth={2.4}
                      dot={false}
                      name="Brute force"
                    />
                    <Line
                      type="monotone"
                      dataKey="optimized_ops"
                      stroke="var(--line-optimized)"
                      strokeWidth={2.4}
                      dot={false}
                      name="Optimized"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="result-card">
              <h3>Optimization notes</h3>
              <ul className="bullet-list">
                {result.optimization_notes.map((note, index) => (
                  <li key={`${note}-${index}`}>{note}</li>
                ))}
              </ul>
              <p className="correctness-note">{result.correctness_notes}</p>
            </article>

            <article className="result-card">
              <div className="card-head">
                <h3>Optimized C++ output</h3>
              </div>
              <div className="code-block-wrap">
                <CopyButton text={result.optimized_code} label="Copy code" />
                <pre className="code-block">{result.optimized_code}</pre>
              </div>
            </article>

            <article className="result-card">
              <h3>Compiler attempts</h3>
              <div className="attempt-list">
                {result.compiler_attempts.map((attempt) => (
                  <div
                    className={
                      attempt.success ? "attempt-item" : "attempt-item failed"
                    }
                    key={`attempt-${attempt.attempt}`}
                  >
                    <div className="attempt-head">
                      <div>
                        <strong>Attempt {attempt.attempt}</strong>
                        <span className="attempt-meta">
                          {" "}
                          Exit code:{" "}
                          {typeof attempt.exit_code === "number"
                            ? attempt.exit_code
                            : "N/A"}
                        </span>
                      </div>
                      <span
                        className={
                          attempt.success
                            ? "status-chip ok"
                            : "status-chip failed"
                        }
                      >
                        <span aria-hidden="true">
                          {attempt.success ? "✓" : "✕"}
                        </span>
                        {attempt.success ? "Compiled" : "Failed"}
                      </span>
                    </div>
                    <details open={!attempt.success}>
                      <summary>Compiler output</summary>
                      <pre className="log-block">
                        {attempt.compiler_stderr ||
                          attempt.compiler_stdout ||
                          "No compiler messages."}
                      </pre>
                    </details>
                    <details>
                      <summary>Program output</summary>
                      <pre className="log-block">
                        {attempt.run_stdout ||
                          attempt.run_stderr ||
                          "No program output captured."}
                      </pre>
                    </details>
                  </div>
                ))}
              </div>
            </article>
          </div>
        ) : null}
      </section>
    </div>
  );
}
