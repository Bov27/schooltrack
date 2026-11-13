"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { Icon } from "@/components/Icon";
import { errorMessage } from "@/lib/client";
import type { ApiErrorBody } from "@/lib/types";

// Arched windows of a white colonial facade; a few are lit, like classrooms in use.
const WINDOWS = [false, true, false, false, false, false, true, false, false, false, false, true];

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
      setError(
        response.status === 401 ? "El correo o la contraseña no son correctos." : errorMessage(body, response.status),
      );
      return;
    }
    const next = params.get("next");
    // Only same-site relative paths: never redirect to another origin.
    router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
  }

  return (
    <form onSubmit={submit}>
      <div>
        <h2>Ingresar</h2>
        <p className="muted" style={{ marginTop: 6 }}>Con la cuenta que te dio tu institución.</p>
      </div>
      {error && (
        <div className="error" role="alert">
          <Icon name="alert" size={18} />
          {error}
        </div>
      )}
      <label>
        Correo
        <input name="email" type="email" autoComplete="username" required autoFocus />
      </label>
      <label>
        Contraseña
        <input name="password" type="password" autoComplete="current-password" required />
      </label>
      <button type="submit" disabled={busy}>
        {busy ? "Ingresando…" : "Ingresar"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="login">
      <section className="login-art">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="bell" size={20} />
          </span>
          <span className="brand-name">SchoolTrack</span>
        </div>
        <div>
          <h1>Quién está en el colegio, en este momento.</h1>
          <p>
            Estudiantes y funcionarios registran su entrada desde el celular. La ubicación se valida contra la
            geocerca de la sede y solo se consulta cuando la persona toca el botón.
          </p>
        </div>
        <div className="windows" aria-hidden="true">
          {WINDOWS.map((lit, i) => (
            <span key={i} className={lit ? "lit" : undefined} style={{ animationDelay: `${i * 0.4}s` }} />
          ))}
        </div>
      </section>
      <section className="login-form">
        <Suspense>
          <LoginForm />
        </Suspense>
      </section>
    </div>
  );
}
