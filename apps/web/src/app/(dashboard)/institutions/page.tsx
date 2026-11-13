"use client";

import { type FormEvent, useState } from "react";

import { useSession } from "@/components/Shell";
import { api } from "@/lib/client";
import type { Institution } from "@/lib/types";

export default function InstitutionsPage() {
  const { me } = useSession();
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Institution[]>([]);

  if (!me.is_platform_admin) return <div className="panel muted">Platform administrators only.</div>;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    setError(null);
    try {
      const institution = await api<Institution>("institutions", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          slug: form.get("slug"),
          timezone: form.get("timezone") || "America/Bogota",
          admin_email: form.get("admin_email") || null,
        }),
      });
      setCreated((list) => [institution, ...list]);
      target.reset();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <>
      <h2>Institutions</h2>
      <div className="panel">
        <h3>New institution</h3>
        {error && <div className="error">{error}</div>}
        <form className="inline" onSubmit={submit}>
          <label>Name<input name="name" required /></label>
          <label>Slug<input name="slug" required pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="colegio-san-jose" /></label>
          <label>Timezone<input name="timezone" placeholder="America/Bogota" /></label>
          <label>First school admin (existing account email)<input name="admin_email" type="email" /></label>
          <button type="submit">Create</button>
        </form>
      </div>
      {created.length > 0 && (
        <div className="panel">
          <h3>Created in this session</h3>
          <ul>{created.map((i) => <li key={i.id}>{i.name} <span className="muted">({i.slug})</span></li>)}</ul>
        </div>
      )}
    </>
  );
}
