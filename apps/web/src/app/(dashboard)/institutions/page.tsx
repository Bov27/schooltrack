"use client";

import { type FormEvent, useState } from "react";

import { Icon } from "@/components/Icon";
import { Message, PageHead, useSession } from "@/components/Shell";
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
    <form className="inline" onSubmit={submit} style={{ justifyContent: "flex-end" }}>
      <input
        name="email"
        type="email"
        required
        placeholder="correo de la cuenta"
        aria-label={`Correo del nuevo administrador de ${institution.name}`}
      />
      <button type="submit" className="secondary small">Asignar administrador</button>
      {ok && <span className="muted small">Listo. Si eres tú, recarga la página para ver la institución.</span>}
      {error && <span className="error small">{error}</span>}
    </form>
  );
}

export default function InstitutionsPage() {
  const { me } = useSession();
  const [error, setError] = useState<string | null>(null);
  const institutions = useApi<PlatformInstitution[]>(me.is_platform_admin ? "platform/institutions" : null);

  if (!me.is_platform_admin) return <Message tone="notice">Solo para administradores de la plataforma.</Message>;

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
      <PageHead title="Instituciones">Todas las instituciones de la plataforma y quién las administra.</PageHead>
      <details className="panel">
        <summary>
          Nueva institución
          <Icon name="plus" />
        </summary>
        {error && <Message tone="error">{error}</Message>}
        <form className="inline" onSubmit={submit}>
          <label>Nombre<input name="name" required placeholder="Colegio San José" /></label>
          <label>
            Identificador
            <input name="slug" required pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="colegio-san-jose" />
          </label>
          <label>Zona horaria<input name="timezone" placeholder="America/Bogota" /></label>
          <label>
            Primer administrador <span className="hint">(cuenta existente)</span>
            <input name="admin_email" type="email" defaultValue={me.email} />
          </label>
          <button type="submit">Crear institución</button>
        </form>
      </details>
      <section className="panel">
        {institutions.error && <Message tone="error">{institutions.error}</Message>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Institución</th><th>Administradores</th><th /></tr>
            </thead>
            <tbody>
              {institutions.data?.map((i) => (
                <tr key={i.id}>
                  <td>
                    <strong>{i.name}</strong>
                    <div className="muted small">{i.slug}</div>
                  </td>
                  <td>
                    {i.school_admins === 0 ? <span className="badge warn">Ninguno</span> : <span className="num">{i.school_admins}</span>}
                  </td>
                  <td><AssignAdmin institution={i} onDone={institutions.reload} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {institutions.data?.length === 0 && <p className="empty">Aún no hay instituciones.</p>}
      </section>
    </>
  );
}
