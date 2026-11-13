"use client";

import { type FormEvent, useState } from "react";

import { Icon } from "@/components/Icon";
import { AdminOnly, Message, PageHead, useSession } from "@/components/Shell";
import { api, useApi } from "@/lib/client";
import { initials } from "@/lib/format";
import type { StaffMember, Student } from "@/lib/types";

const STAFF_TYPES: Record<StaffMember["staff_type"], string> = {
  TEACHER: "Docente",
  ADMINISTRATIVE: "Administrativo",
  SUPPORT: "Apoyo",
};

export default function PeoplePage() {
  const { isAdmin, isTeacher } = useSession();
  const canList = isAdmin || isTeacher;
  const students = useApi<Student[]>(canList ? "students" : null);
  const staff = useApi<StaffMember[]>(isAdmin ? "staff" : null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  async function submit(
    event: FormEvent<HTMLFormElement>,
    path: string,
    body: Record<string, unknown>,
    success: string,
  ) {
    event.preventDefault();
    const target = event.currentTarget;
    setError(null);
    setDone(null);
    try {
      await api(path, { method: "POST", body: JSON.stringify(body) });
      target.reset();
      setDone(success);
      students.reload();
      staff.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function updateStudent(student: Student, body: Record<string, unknown>) {
    setError(null);
    setDone(null);
    try {
      await api(`students/${student.id}`, { method: "PATCH", body: JSON.stringify(body) });
      students.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function linkAccount(student: Student) {
    const email = window.prompt(`Correo de la cuenta de la app de ${student.full_name}:`);
    if (email) void updateStudent(student, { user_email: email.trim() });
  }

  if (!canList) return <Message tone="notice">Solo la administración y los docentes ven esta página.</Message>;

  const needle = query.trim().toLowerCase();
  const visible = (students.data ?? []).filter(
    (s) => !needle || s.full_name.toLowerCase().includes(needle) || s.student_code.toLowerCase().includes(needle),
  );

  return (
    <>
      <PageHead title="Personas">
        Estudiantes y funcionarios de la institución, y las cuentas con las que usan la app.
      </PageHead>
      {error && <Message tone="error">{error}</Message>}
      {done && <Message tone="success">{done}</Message>}

      <AdminOnly>
        <details className="panel">
          <summary>
            Crear una cuenta para la app
            <Icon name="plus" />
          </summary>
          <p className="muted">
            Para estudiantes, funcionarios o acudientes. Entrega la contraseña inicial en privado; la persona
            puede cambiarla desde la app. Después vincula la cuenta con su correo.
          </p>
          <form
            className="inline"
            onSubmit={(e) => {
              const f = new FormData(e.currentTarget);
              void submit(
                e,
                "accounts",
                { email: f.get("email"), full_name: f.get("name"), initial_password: f.get("password") },
                `Cuenta creada para ${String(f.get("email"))}. Ya puedes vincularla.`,
              );
            }}
          >
            <label>Correo<input name="email" type="email" required /></label>
            <label>Nombre completo<input name="name" required /></label>
            <label>
              Contraseña inicial <span className="hint">(12 o más caracteres)</span>
              <input name="password" type="text" minLength={12} required autoComplete="off" />
            </label>
            <button type="submit">Crear cuenta</button>
          </form>
        </details>

        <details className="panel">
          <summary>
            Registrar estudiante
            <Icon name="plus" />
          </summary>
          <form
            className="inline"
            onSubmit={(e) => {
              const f = new FormData(e.currentTarget);
              void submit(
                e,
                "students",
                {
                  student_code: f.get("code"),
                  full_name: f.get("name"),
                  date_of_birth: f.get("dob") || null,
                  user_email: f.get("email") || null,
                },
                `${String(f.get("name"))} quedó registrado.`,
              );
            }}
          >
            <label>Código<input name="code" required /></label>
            <label>Nombre completo<input name="name" required /></label>
            <label>Fecha de nacimiento<input name="dob" type="date" /></label>
            <label>
              Cuenta de la app <span className="hint">(opcional)</span>
              <input name="email" type="email" placeholder="correo ya creado" />
            </label>
            <button type="submit">Registrar estudiante</button>
          </form>
        </details>

        <details className="panel">
          <summary>
            Registrar funcionario
            <Icon name="plus" />
          </summary>
          <p className="muted">El funcionario necesita una cuenta: créala primero en “Crear una cuenta para la app”.</p>
          <form
            className="inline"
            onSubmit={(e) => {
              const f = new FormData(e.currentTarget);
              void submit(
                e,
                "staff",
                { employee_code: f.get("code"), staff_type: f.get("type"), user_email: f.get("email") },
                "Funcionario registrado.",
              );
            }}
          >
            <label>Código<input name="code" required /></label>
            <label>
              Tipo
              <select name="type">
                {Object.entries(STAFF_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>Correo de la cuenta<input name="email" type="email" required /></label>
            <button type="submit">Registrar funcionario</button>
          </form>
        </details>
      </AdminOnly>

      <section className="panel">
        <div className="panel-head">
          <h2>Estudiantes <span className="muted num">{students.data?.length ?? ""}</span></h2>
          <input
            type="search"
            placeholder="Buscar por nombre o código"
            aria-label="Buscar estudiantes"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ minWidth: 240 }}
          />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Estudiante</th><th>Cuenta de la app</th><th>Estado</th>{isAdmin && <th />}</tr>
            </thead>
            <tbody>
              {visible.map((s) => (
                <tr key={s.id}>
                  <td>
                    <span className="person">
                      <span className="avatar">{initials(s.full_name)}</span>
                      <span>
                        <strong>{s.full_name}</strong>
                        <div className="muted small">{s.student_code}</div>
                      </span>
                    </span>
                  </td>
                  <td>
                    {s.user_id ? (
                      <span className="badge ok">Vinculada</span>
                    ) : (
                      <span className="muted small">Sin cuenta: asistencia manual</span>
                    )}
                  </td>
                  <td>
                    <span className={`badge ${s.is_active ? "ok" : "neutral"}`}>{s.is_active ? "Activo" : "Inactivo"}</span>
                  </td>
                  {isAdmin && (
                    <td className="actions">
                      {s.user_id ? (
                        <button className="ghost small" onClick={() => void updateStudent(s, { unlink_account: true })}>
                          Desvincular cuenta
                        </button>
                      ) : (
                        <button className="secondary small" onClick={() => linkAccount(s)}>
                          <Icon name="link" size={16} />
                          Vincular cuenta
                        </button>
                      )}
                      <button className="ghost small" onClick={() => void updateStudent(s, { is_active: !s.is_active })}>
                        {s.is_active ? "Desactivar" : "Activar"}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {students.data && visible.length === 0 && (
          <p className="empty">{needle ? "Nadie coincide con la búsqueda." : "Aún no hay estudiantes registrados."}</p>
        )}
      </section>

      <AdminOnly>
        <section className="panel">
          <div className="panel-head">
            <h2>Funcionarios <span className="muted num">{staff.data?.length ?? ""}</span></h2>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Código</th><th>Tipo</th><th>Estado</th></tr></thead>
              <tbody>
                {staff.data?.map((m) => (
                  <tr key={m.id}>
                    <td><strong>{m.employee_code}</strong></td>
                    <td>{STAFF_TYPES[m.staff_type]}</td>
                    <td>
                      <span className={`badge ${m.is_active ? "ok" : "neutral"}`}>{m.is_active ? "Activo" : "Inactivo"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {staff.data?.length === 0 && <p className="empty">Aún no hay funcionarios registrados.</p>}
        </section>
      </AdminOnly>
    </>
  );
}
