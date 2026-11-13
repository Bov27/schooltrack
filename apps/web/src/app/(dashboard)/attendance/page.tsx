"use client";

import { type FormEvent, useMemo, useState } from "react";

import { AdminOnly, StatusBadge, useSession } from "@/components/Shell";
import { api, newIdempotencyKey, useApi } from "@/lib/client";
import { formatDateTime, reasonLabel } from "@/lib/format";
import type { AttendanceEvent, Campus, Student, ValidationStatus } from "@/lib/types";

const FILTERS: { value: ValidationStatus | ""; label: string }[] = [
  { value: "FLAGGED_FOR_REVIEW", label: "Waiting for review" },
  { value: "", label: "All" },
  { value: "VALIDATED", label: "Validated" },
  { value: "REJECTED", label: "Rejected" },
];

function ReviewButtons({ event, onDone }: { event: AttendanceEvent; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  if (event.validation_status !== "FLAGGED_FOR_REVIEW" && event.validation_status !== "PENDING") return null;

  async function decide(decision: "VALIDATED" | "REJECTED") {
    const note = window.prompt(decision === "VALIDATED" ? "Why is this event valid?" : "Why is it rejected?");
    if (!note || note.trim().length < 3) return;
    try {
      await api(`attendance/events/${event.id}/review`, {
        method: "POST",
        body: JSON.stringify({ decision, note: note.trim() }),
      });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <span style={{ display: "inline-flex", gap: 6 }}>
      <button className="secondary" onClick={() => void decide("VALIDATED")}>Validate</button>
      <button className="danger" onClick={() => void decide("REJECTED")}>Reject</button>
      {error && <span className="error">{error}</span>}
    </span>
  );
}

function ManualEventForm({ students, campuses, onDone }: {
  students: Student[];
  campuses: Campus[];
  onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    setError(null);
    setOk(null);
    try {
      await api("attendance/manual-events", {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: newIdempotencyKey(),
          event_type: form.get("event_type"),
          campus_id: form.get("campus_id"),
          student_id: form.get("student_id"),
          reason: form.get("reason"),
        }),
      });
      target.reset();
      setOk("Manual event recorded (and audited)");
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <form className="inline" onSubmit={submit}>
      {error && <div className="error" style={{ width: "100%" }}>{error}</div>}
      {ok && <div className="success" style={{ width: "100%" }}>{ok}</div>}
      <label>
        Student
        <select name="student_id" required>
          {students.map((s) => <option key={s.id} value={s.id}>{s.full_name} ({s.student_code})</option>)}
        </select>
      </label>
      <label>
        Campus
        <select name="campus_id" required>
          {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label>
        Action
        <select name="event_type">
          <option value="CHECK_IN">Check in</option>
          <option value="TEMPORARY_CHECK_OUT">Temporary exit</option>
          <option value="RETURN">Return</option>
          <option value="CHECK_OUT">Check out</option>
        </select>
      </label>
      <label style={{ flex: 1 }}>
        Reason (required)
        <input name="reason" minLength={3} required placeholder="No phone, first grade" />
      </label>
      <button type="submit">Record</button>
    </form>
  );
}

export default function AttendancePage() {
  const { isAdmin } = useSession();
  const [filter, setFilter] = useState<ValidationStatus | "">(isAdmin ? "FLAGGED_FOR_REVIEW" : "");
  const events = useApi<AttendanceEvent[]>(
    `attendance/events?limit=200${filter ? `&validation_status=${filter}` : ""}`,
  );
  const students = useApi<Student[]>(isAdmin ? "students" : null);
  const campuses = useApi<Campus[]>("campuses");

  const studentName = useMemo(() => {
    const names = new Map(students.data?.map((s) => [s.id, s.full_name]));
    return (id: string | null) => (id ? (names.get(id) ?? id.slice(0, 8)) : "staff");
  }, [students.data]);
  const campusName = useMemo(() => {
    const names = new Map(campuses.data?.map((c) => [c.id, c.name]));
    return (id: string) => names.get(id) ?? id.slice(0, 8);
  }, [campuses.data]);

  return (
    <>
      <h2>Attendance</h2>
      <AdminOnly>
        <div className="panel">
          <h3>Manual entry</h3>
          <p className="muted">For people who cannot use the app. The reason is stored in the audit log.</p>
          {students.data && campuses.data && (
            <ManualEventForm students={students.data} campuses={campuses.data} onDone={events.reload} />
          )}
        </div>
      </AdminOnly>
      <div className="panel">
        <form className="inline" onSubmit={(e) => e.preventDefault()}>
          <label>
            Show
            <select value={filter} onChange={(e) => setFilter(e.target.value as ValidationStatus | "")}>
              {FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </label>
        </form>
        {events.error && <div className="error">{events.error}</div>}
        <table style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>When</th><th>Who</th><th>Action</th><th>Campus</th><th>Status</th><th>Why</th>
              {isAdmin && <th>Location</th>}
              {isAdmin && <th />}
            </tr>
          </thead>
          <tbody>
            {events.data?.map((e) => (
              <tr key={e.id}>
                <td>{formatDateTime(e.occurred_at)}</td>
                <td>{studentName(e.student_id)}</td>
                <td>{e.event_type.replaceAll("_", " ").toLowerCase()}<br /><span className="muted">{e.source.toLowerCase()}</span></td>
                <td>{campusName(e.campus_id)}</td>
                <td><StatusBadge status={e.validation_status} /></td>
                <td className="muted">{e.validation_reasons.map(reasonLabel).join("; ") || "–"}</td>
                {isAdmin && (
                  <td className="muted">
                    {e.location
                      ? `${e.location.latitude.toFixed(5)}, ${e.location.longitude.toFixed(5)} ±${Math.round(e.location.accuracy_m ?? 0)} m`
                      : "–"}
                  </td>
                )}
                {isAdmin && <td><ReviewButtons event={e} onDone={events.reload} /></td>}
              </tr>
            ))}
            {events.data?.length === 0 && (
              <tr><td colSpan={8} className="muted">No events.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
