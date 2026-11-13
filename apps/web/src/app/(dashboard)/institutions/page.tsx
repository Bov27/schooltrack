"use client";

import { type FormEvent, useState } from "react";

import { useSession } from "@/components/Shell";
import { api, useApi } from "@/lib/client";
import type { Institution } from "@/lib/types";

interface PlatformInstitution extends Institution {
  school_admins: number;
}

function AssignAdmin({ institution, onDone }: { institution: PlatformInstitution; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    setError(null);
    setOk(false);
    try {
      await api(`platform/institutions/${institution.id}/admins`, {
        method: "POST",
        body: JSON.stringify({ user_email: form.get("email") }),
      });
      target.reset();
      setOk(true);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <form className="inline" onSubmit={submit}>
      <input name="email" type="email" required placeholder="account email" aria-label="School admin email" />
      <button type="submit" className="secondary">Make school admin</button>
      {ok && <span className="muted">Done. If it is you, reload the page to see the institution.</span>}
      {error && <span className="error">{error}</span>}
    </form>
  );
}

export default function InstitutionsPage() {
  const { me } = useSession();
  const [error, setError] = useState<string | null>(null);
  const institutions = useApi<PlatformInstitution[]>(me.is_platform_admin ? "platform/institutions" : null);

  if (!me.is_platform_admin) return <div className="panel muted">Platform administrators only.</div>;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    setError(null);
    try {
      await api<Institution>("institutions", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          slug: form.get("slug"),
          timezone: form.get("timezone") || "America/Bogota",
          admin_email: form.get("admin_email") || null,
        }),
      });
      target.reset();
      institutions.reload();
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
          <label>
            First school admin (existing account email)
            <input name="admin_email" type="email" defaultValue={me.email} />
          </label>
          <button type="submit">Create</button>
        </form>
      </div>
      <div className="panel">
        <h3>All institutions</h3>
        {institutions.error && <div className="error">{institutions.error}</div>}
        <table>
          <thead>
            <tr><th>Name</th><th>Slug</th><th>School admins</th><th>Assign a school admin</th></tr>
          </thead>
          <tbody>
            {institutions.data?.map((i) => (
              <tr key={i.id}>
                <td>{i.name}</td>
                <td className="muted">{i.slug}</td>
                <td>{i.school_admins === 0 ? <span className="badge warn">none</span> : i.school_admins}</td>
                <td><AssignAdmin institution={i} onDone={institutions.reload} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
