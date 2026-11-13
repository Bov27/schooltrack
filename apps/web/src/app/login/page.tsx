"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { errorMessage } from "@/lib/client";
import type { ApiErrorBody } from "@/lib/types";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
    });
    setBusy(false);
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
      setError(errorMessage(body, response.status));
      return;
    }
    const next = params.get("next");
    // Only same-site relative paths: never redirect to another origin.
    router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
  }

  return (
    <form onSubmit={submit}>
      {error && <div className="error">{error}</div>}
      <label>
        Email
        <input name="email" type="email" autoComplete="username" required />
      </label>
      <label>
        Password
        <input name="password" type="password" autoComplete="current-password" required />
      </label>
      <button type="submit" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="login">
      <div className="panel">
        <h2>SchoolTrack</h2>
        <p className="muted">Administration dashboard</p>
        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </div>
  );
}
