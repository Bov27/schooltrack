"use client";

import { type FormEvent, useState } from "react";

import { Icon } from "@/components/Icon";
import { AdminOnly, Message, PageHead, StatusBadge, useSession } from "@/components/Shell";
import { api, useApi } from "@/lib/client";
import { formatArea, parseLatLng, reasonLabel, statusLabel } from "@/lib/format";
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
        if (!center) throw new Error("El centro debe tener la forma: 2.4419, -76.6063");
        body.center = center;
        const radius = Number(form.get("radius"));
        if (radius > 0) body.radius_m = radius;
      } else {
        try {
          body.area = JSON.parse(String(form.get("geojson")));
        } catch {
          throw new Error("El polígono debe ser GeoJSON válido");
        }
      }
      await api<Geofence>("geofences", { method: "POST", body: JSON.stringify(body) });
      target.reset();
      onCreated();
      return "Geocerca creada";
    });
  }

  return (
    <form className="inline" onSubmit={submit}>
      {action.error && <div style={{ width: "100%" }}><Message tone="error">{action.error}</Message></div>}
      {action.message && <div style={{ width: "100%" }}><Message tone="success">{action.message}</Message></div>}
      <label>
        Nombre
        <input name="name" required defaultValue="Perímetro" />
      </label>
      <label>
        Forma
        <select value={mode} onChange={(e) => setMode(e.target.value as "circle" | "polygon")}>
          <option value="circle">Centro y radio</option>
          <option value="polygon">Polígono GeoJSON</option>
        </select>
      </label>
      {mode === "circle" ? (
        <>
          <label>
            Centro <span className="hint">(lat, lng desde Google Maps)</span>
            <input name="center" placeholder="2.4419, -76.6063" required />
          </label>
          <label>
            Radio en metros
            <input name="radius" type="number" min={10} max={5000} placeholder="100" />
          </label>
        </>
      ) : (
        <label style={{ flex: "1 1 100%" }}>
          Polígono GeoJSON <span className="hint">(posiciones [lng, lat])</span>
          <textarea name="geojson" required placeholder='{"type":"Polygon","coordinates":[[[-76.607,2.441], …]]}' />
        </label>
      )}
      <button type="submit" disabled={action.busy}>Crear geocerca</button>
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
      if (!point) throw new Error("El punto debe tener la forma: 2.4419, -76.6063");
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
      {action.error && <div style={{ width: "100%" }}><Message tone="error">{action.error}</Message></div>}
      <label>
        Punto <span className="hint">(lat, lng)</span>
        <input name="point" placeholder="2.4419, -76.6063" required />
      </label>
      <label>
        Precisión del GPS en metros
        <input name="accuracy" type="number" min={0} defaultValue={10} />
      </label>
      <button type="submit" className="secondary" disabled={action.busy}>Probar punto</button>
      {verdict && (
        <div className="verdict" role="status">
          <StatusBadge status={verdict.verdict} />
          <strong>{statusLabel(verdict.geofence_result)} de la geocerca</strong>
          {verdict.distance_m !== null && verdict.distance_m > 0 && (
            <span className="muted">a {Math.round(verdict.distance_m)} m del borde</span>
          )}
          {verdict.reasons.length > 0 && (
            <span className="muted">{verdict.reasons.map(reasonLabel).join(". ")}</span>
          )}
          <span className="muted small">No se guarda nada.</span>
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
    if (!window.confirm(`¿Eliminar la geocerca "${geofence.name}"? No se puede deshacer.`)) return;
    void run(() => api(`geofences/${geofence.id}`, { method: "DELETE" }));
  };

  return (
    <>
      <button className="secondary small" disabled={busy} onClick={() => void toggle()}>
        {geofence.is_active ? "Desactivar" : "Activar"}
      </button>
      <button className="danger small" disabled={busy} onClick={remove}>
        Eliminar
      </button>
      {error && <div className="error small">{error}</div>}
    </>
  );
}

function CampusCard({ campus }: { campus: Campus }) {
  const { isAdmin } = useSession();
  const geofences = useApi<Geofence[]>(`geofences?campus_id=${campus.id}`);
  const noneActive = geofences.data !== undefined && !geofences.data.some((g) => g.is_active);
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>{campus.name}</h2>
          <p className="muted">
            {campus.address ?? "Sin dirección"}
            {campus.timezone ? `, ${campus.timezone}` : ""}
          </p>
        </div>
      </div>
      {geofences.error && <Message tone="error">{geofences.error}</Message>}
      {noneActive && (
        <Message tone="notice">
          Esta sede no tiene ninguna geocerca activa: la asistencia registrada aquí se va a rechazar.
        </Message>
      )}
      {geofences.data && geofences.data.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Geocerca</th><th>Área</th><th>Estado</th>{isAdmin && <th />}</tr>
            </thead>
            <tbody>
              {geofences.data.map((g) => (
                <tr key={g.id}>
                  <td><strong>{g.name}</strong></td>
                  <td className="num">{formatArea(g.area_m2)}</td>
                  <td>
                    <span className={`badge ${g.is_active ? "ok" : "neutral"}`}>{g.is_active ? "Activa" : "Inactiva"}</span>
                  </td>
                  {isAdmin && (
                    <td className="actions">
                      <GeofenceActions geofence={g} onChanged={geofences.reload} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {isAdmin && (
        <p className="muted small" style={{ marginTop: 10 }}>
          Una geocerca que ya validó asistencia no se puede eliminar, porque es la evidencia de esos registros.
          En ese caso, desactívala.
        </p>
      )}
      <AdminOnly>
        <h3 className="subhead">Nueva geocerca</h3>
        <GeofenceForm campus={campus} onCreated={geofences.reload} />
      </AdminOnly>
      <h3 className="subhead">Probar una ubicación</h3>
      <LocationTester campus={campus} />
    </section>
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
      return "Sede creada";
    });
  }

  return (
    <>
      <PageHead title="Sedes y geocercas">
        La geocerca es el perímetro de la sede. Una entrada solo es válida si la ubicación del celular cae
        dentro de ella.
      </PageHead>
      <AdminOnly>
        <details className="panel">
          <summary>
            Nueva sede
            <Icon name="plus" />
          </summary>
          {action.error && <Message tone="error">{action.error}</Message>}
          {action.message && <Message tone="success">{action.message}</Message>}
          <form className="inline" onSubmit={create}>
            <label>Nombre<input name="name" required placeholder="Sede Principal" /></label>
            <label>Dirección<input name="address" /></label>
            <label>Zona horaria<input name="timezone" placeholder="America/Bogota" /></label>
            <button type="submit" disabled={action.busy}>Crear sede</button>
          </form>
        </details>
      </AdminOnly>
      {campuses.error && <Message tone="error">{campuses.error}</Message>}
      {campuses.data?.length === 0 && <p className="empty">Aún no hay sedes.</p>}
      {campuses.data?.map((campus) => <CampusCard key={campus.id} campus={campus} />)}
    </>
  );
}
