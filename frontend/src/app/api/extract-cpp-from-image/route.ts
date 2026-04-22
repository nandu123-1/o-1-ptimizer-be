import { NextResponse } from "next/server";

const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 60_000;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("multipart/form-data")) {
    return NextResponse.json(
      { detail: "Expected multipart/form-data upload." },
      { status: 400 },
    );
  }

  const incoming = await request.formData();
  const file = incoming.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json(
      { detail: "Missing 'file' field in upload." },
      { status: 400 },
    );
  }
  if (file.size === 0) {
    return NextResponse.json(
      { detail: "Uploaded image is empty." },
      { status: 400 },
    );
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return NextResponse.json(
      { detail: "Image exceeds 8 MB limit." },
      { status: 400 },
    );
  }

  const backendBaseUrl =
    process.env.BACKEND_API_BASE_URL ?? DEFAULT_BACKEND_BASE_URL;

  const forward = new FormData();
  forward.append("file", file, file.name || "upload");

  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => {
    controller.abort();
  }, REQUEST_TIMEOUT_MS);

  try {
    const upstream = await fetch(
      `${backendBaseUrl}/v1/extract-cpp-from-image`,
      {
        method: "POST",
        body: forward,
        cache: "no-store",
        signal: controller.signal,
      },
    );
    const body = await upstream.text();
    const parsed = body.length > 0 ? JSON.parse(body) : null;
    return NextResponse.json(parsed, { status: upstream.status });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return NextResponse.json(
        { detail: "Image extraction timed out before backend response." },
        { status: 504 },
      );
    }
    return NextResponse.json(
      {
        detail:
          "Failed to reach backend image extractor. Confirm FastAPI is running.",
      },
      { status: 502 },
    );
  } finally {
    clearTimeout(timeoutHandle);
  }
}
