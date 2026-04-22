import { NextResponse } from "next/server";

import type { OptimizeCodeRequest } from "@/lib/contracts";

const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 180_000;
const MAX_CODE_BYTES = 200_000;

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function isValidPayload(payload: unknown): payload is OptimizeCodeRequest {
  if (!payload || typeof payload !== "object") {
    return false;
  }

  const candidate = payload as Partial<OptimizeCodeRequest>;
  if (
    typeof candidate.cpp_code !== "string" ||
    candidate.cpp_code.length === 0 ||
    candidate.cpp_code.length > MAX_CODE_BYTES
  ) {
    return false;
  }
  if (typeof candidate.stdin_data !== "string") {
    return false;
  }
  if (
    typeof candidate.max_self_correction_attempts !== "number" ||
    !Number.isFinite(candidate.max_self_correction_attempts) ||
    candidate.max_self_correction_attempts < 1 ||
    candidate.max_self_correction_attempts > 8
  ) {
    return false;
  }
  return true;
}

export async function POST(request: Request) {
  let payload: unknown;

  try {
    payload = await request.json();
  } catch {
    return NextResponse.json(
      { detail: "Request body must be valid JSON." },
      { status: 400 },
    );
  }

  if (!isValidPayload(payload)) {
    return NextResponse.json(
      {
        detail:
          "Invalid payload. Expected cpp_code (1..200000 chars), stdin_data (string), and max_self_correction_attempts (1-8).",
      },
      { status: 400 },
    );
  }

  const backendBaseUrl =
    process.env.BACKEND_API_BASE_URL ?? DEFAULT_BACKEND_BASE_URL;
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => {
    controller.abort();
  }, REQUEST_TIMEOUT_MS);

  try {
    const upstreamResponse = await fetch(`${backendBaseUrl}/v1/optimize-code`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: controller.signal,
    });

    const contentType = upstreamResponse.headers.get("content-type") ?? "";
    const body = contentType.includes("application/json")
      ? await upstreamResponse.json()
      : { detail: await upstreamResponse.text() };

    return NextResponse.json(body, { status: upstreamResponse.status });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return NextResponse.json(
        { detail: "Optimization request timed out before backend response." },
        { status: 504 },
      );
    }

    return NextResponse.json(
      {
        detail:
          "Failed to reach backend optimizer API. Confirm FastAPI is running on the configured BACKEND_API_BASE_URL.",
      },
      { status: 502 },
    );
  } finally {
    clearTimeout(timeoutHandle);
  }
}
