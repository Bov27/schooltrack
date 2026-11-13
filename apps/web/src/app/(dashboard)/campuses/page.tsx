"use client";

import { type FormEvent, useState } from "react";

import { AdminOnly, StatusBadge, useSession } from "@/components/Shell";
import { api, useApi } from "@/lib/client";
import { formatArea, parseLatLng, reasonLabel } from "@/lib/format";
import type { Campus, Geofence, LocationVerdict } from "@/lib/types";

function useFormAction() {
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function run(action: () => Promise<string | void>) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await action();
      if (result) setMessage(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return { error, message, busy, run };
}

function GeofenceForm({ campus, onCreated }: { campus: Campus; onCreated: () => void }) {
  const [mode, setMode] = useState<"circle" | "polygon">("circle");
  const action = useFormAction();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    void action.run(async () => {
      const body: Record<string, unknown> = { campus_id: campus.id, name: String(form.get("name")) };
      if (mode === "circle") {
        const center = parseLatLng(String(form.get("center")));
        if (!center) throw new Error("Centre must look like: 2.4419, -76.6063");
        body.center = center;
        const radius = Number(form.get("radius"));
        if (radius > 0) body.radius_m = radius;
      } else {
        try {
          body.area = JSON.parse(String(form.get("geojson")));
        } catch {
          throw new Error("The polygon must be valid GeoJSON");
        }
      }
      await api<Geofence>("geofences", { method: "POST", body: JSON.stringify(body) });
      target.reset();
      onCreated();
      return "Geofence created";
    });
  }

  return (
    <form className="inline" onSubmit={submit}>
      {action.error && <div className="error" style={{ width: "100%" }}>{action.error}</div>}
      {action.message && <div className="success" style={{ width: "100%" }}>{action.message}</div>}
      <label>
        Name
        <input name="name" required defaultValue="Perímetro" />
      </label>
      <label>
        Shape
        <select value={mode} onChange={(e) => setMode(e.target.value as "circle" | "polygon")}>
          <option value="circle">Centre + radius</option>
          <option value="polygon">GeoJSON polygon</option>
        </select>
      </label>
      {mode === "circle" ? (
        <>
          <label>
            Centre (lat, lng)
            <input name="center" placeholder="2.4419, -76.6063" required />
          </label>
          <label>
            Radius (m)
            <input name="radius" type="number" min={10} max={5000} placeholder="100" />
          </label>
        </>
      ) : (
        <label style={{ flex: "1 1 100%" }}>
          GeoJSON polygon ([lng, lat] positions)
          <textarea name="geojson" required placeholder='{"type":"Polygon","coordinates":[[[-76.607,2.441], …]]}' />
        </label>
      )}
      <button type="submit" disabled={action.busy}>Add geofence</button>
    </form>
  );
}

function LocationTester({ campus }: { campus: Campus }) {
  const action = useFormAction();
  const [verdict, setVerdict] = useState<LocationVerdict | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void action.run(async () => {
      const point = parseLatLng(String(form.get("point")));
      if (!point) throw new Error("Point must look like: 2.4419, -76.6063");
      const result = await api<LocationVerdict>("geofences/check", {
        method: "POST",
        body: JSON.stringify({
          campus_id: campus.id,
          ...point,
          accuracy_m: Number(form.get("accuracy")),
          captured_at: new Date().toISOString(),
        }),
      });
      setVerdict(result);
    });
  }

  return (
    <form className="inline" onSubmit={submit}>
      {action.error && <div className="error" style={{ width: "100%" }}>{action.error}</div>}
      <label>
        Test a point (lat, lng)
        <input name="point" placeholder="2.4419, -76.6063" required />
      </label>
      <label>
        GPS accuracy (m)
        <input name="accuracy" type="number" min={0} defaultValue={10} />
      </label>
      <button type="submit" className="secondary" disabled={action.busy}>Check (nothing is stored)</button>
      {verdict && (
        <div style={{ width: "100%" }}>
          <StatusBadge status={verdict.verdict} /> {verdict.geofence_result.toLowerCase()}
          {verdict.distance_m !== null && verdict.distance_m > 0 && ` · ${verdict.distance_m} m from the edge`}
          {verdict.reasons.length > 0 && (
            <span className="muted"> · {verdict.reasons.map(reasonLabel).join("; ")}</span>
          )}
        </div>
      )}
    </form>
  );
}

function GeofenceActions({ geofence, onChanged }: { geofence: Geofence; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const toggle = () =>
    run(() =>
      api(`geofences/${geofence.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !geofence.is_active }),
      }),
    );

  const remove = () => {
    if (!window.confirm(`Delete geofence "${geofence.name}"? This cannot be undone.`)) return;
    void run(() => api(`geofences/${geofence.id}`, { method: "DELETE" }));
  };

  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <button className="secondary" disabled={busy} onClick={() => void toggle()}>
        {geofence.is_active ? "Deactivate" : "Activate"}
      </button>
      <button className="danger" disabled={busy} onClick={remove}>
        Delete
      </button>
      {error && <span className="error">{error}</span>}
    </span>
  );
}

function CampusCard({ campus }: { campus: Campus }) {
  const { isAdmin } = useSession();
  const geofences = useApi<Geofence[]>(`geofences?campus_id=${campus.id}`);
  return (
    <div className="panel">
      <h3>{campus.name}</h3>
      <p className="muted">{campus.address ?? "No address"} · {campus.timezone ?? "institution timezone"}</p>
      {geofences.error && <div className="error">{geofences.error}</div>}
      <table>
        <thead>
          <tr><th>Geofence</th><th>Area</th><th>Status</th>{isAdmin && <th />}</tr>
        </thead>
        <tbody>
          {geofences.data?.map((g) => (
            <tr key={g.id}>
              <td>{g.name}</td>
              <td>{formatArea(g.area_m2)}</td>
              <td>
                <span className={`badge ${g.is_active ? "ok" : "neutral"}`}>{g.is_active ? "active" : "inactive"}</span>
              </td>
              {isAdmin && (
                <td>
                  <GeofenceActions geofence={g} onChanged={geofences.reload} />
                </td>
              )}
            </tr>
          ))}
          {geofences.data?.length === 0 && (
            <tr><td colSpan={4} className="muted">No geofence yet: attendance on this campus will be rejected.</td></tr>
          )}
        </tbody>
      </table>
      {geofences.data && geofences.data.length > 0 && geofences.data.every((g) => !g.is_active) && (
        <div className="error" style={{ marginTop: 10 }}>
          Every geofence of this campus is inactive: attendance here will be rejected.
        </div>
      )}
      <p className="muted">
        A geofence that already validated attendance cannot be deleted (it is evidence for those events);
        deactivate it instead.
      </p>
      <AdminOnly>
        <h3 style={{ marginTop: 18 }}>Add a geofence</h3>
        <GeofenceForm campus={campus} onCreated={geofences.reload} />
      </AdminOnly>
      <h3 style={{ marginTop: 18 }}>Test a location</h3>
      <LocationTester campus={campus} />
    </div>
  );
}

export default function CampusesPage() {
  const campuses = useApi<Campus[]>("campuses");
  const action = useFormAction();

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    void action.run(async () => {
      await api<Campus>("campuses", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          address: form.get("address") || null,
          timezone: form.get("timezone") || null,
        }),
      });
      target.reset();
      campuses.reload();
      return "Campus created";
    });
  }

  return (
    <>
      <h2>Campuses & geofences</h2>
      <AdminOnly>
        <div className="panel">
          <h3>New campus</h3>
          {action.error && <div className="error">{action.error}</div>}
          {action.message && <div className="success">{action.message}</div>}
          <form className="inline" onSubmit={create}>
            <label>Name<input name="name" required /></label>
            <label>Address<input name="address" /></label>
            <label>Timezone<input name="timezone" placeholder="America/Bogota" /></label>
            <button type="submit" disabled={action.busy}>Create</button>
          </form>
        </div>
      </AdminOnly>
      {campuses.error && <div className="error">{campuses.error}</div>}
      {campuses.data?.map((campus) => <CampusCard key={campus.id} campus={campus} />)}
    </>
  );
}
