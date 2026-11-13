"use client";

import { type FormEvent, useState } from "react";

import { AdminOnly, useSession } from "@/components/Shell";
import { api, useApi } from "@/lib/client";
import type { StaffMember, Student } from "@/lib/types";

export default function PeoplePage() {
  const { isAdmin, membership } = useSession();
  const canList = isAdmin || (membership?.roles.includes("TEACHER") ?? false);
  const students = useApi<Student[]>(canList ? "students" : null);
  const staff = useApi<StaffMember[]>(isAdmin ? "staff" : null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>, path: string, body: Record<string, unknown>) {
    event.preventDefault();
    const target = event.currentTarget;
    setError(null);
    try {
      await api(path, { method: "POST", body: JSON.stringify(body) });
      target.reset();
      students.reload();
      staff.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!canList) return <div className="panel muted">Only school administrators and teachers can see this page.</div>;

  return (
    <>
      <h2>Students & staff</h2>
      {error && <div className="error">{error}</div>}
      <AdminOnly>
        <div className="panel">
          <h3>Register a student</h3>
          <form
            className="inline"
            onSubmit={(e) => {
              const f = new FormData(e.currentTarget);
              void submit(e, "students", {
                student_code: f.get("code"),
                full_name: f.get("name"),
                date_of_birth: f.get("dob") || null,
                user_email: f.get("email") || null,
              });
            }}
          >
            <label>Code<input name="code" required /></label>
            <label>Full name<input name="name" required /></label>
            <label>Date of birth<input name="dob" type="date" /></label>
            <label>App account email (optional)<input name="email" type="email" /></label>
            <button type="submit">Register</button>
          </form>
        </div>
        <div className="panel">
          <h3>Register a staff member</h3>
          <form
            className="inline"
            onSubmit={(e) => {
              const f = new FormData(e.currentTarget);
              void submit(e, "staff", {
                employee_code: f.get("code"),
                staff_type: f.get("type"),
                user_email: f.get("email"),
              });
            }}
          >
            <label>Code<input name="code" required /></label>
            <label>
              Type
              <select name="type">
                <option value="TEACHER">Teacher</option>
                <option value="ADMINISTRATIVE">Administrative</option>
                <option value="SUPPORT">Support</option>
              </select>
            </label>
            <label>Account email<input name="email" type="email" required /></label>
            <button type="submit">Register</button>
          </form>
        </div>
      </AdminOnly>

      <div className="panel">
        <h3>Students ({students.data?.length ?? 0})</h3>
        <table>
          <thead><tr><th>Code</th><th>Name</th><th>App account</th></tr></thead>
          <tbody>
            {students.data?.map((s) => (
              <tr key={s.id}>
                <td>{s.student_code}</td>
                <td>{s.full_name}</td>
                <td>{s.user_id ? "linked" : <span className="muted">none (manual attendance)</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <AdminOnly>
        <div className="panel">
          <h3>Staff ({staff.data?.length ?? 0})</h3>
          <table>
            <thead><tr><th>Code</th><th>Type</th></tr></thead>
            <tbody>
              {staff.data?.map((m) => (
                <tr key={m.id}><td>{m.employee_code}</td><td>{m.staff_type.toLowerCase()}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </AdminOnly>
    </>
  );
}
