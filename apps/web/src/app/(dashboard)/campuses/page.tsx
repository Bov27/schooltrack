"use client";

import { type FormEvent, useMemo, useState } from "react";

import { CampusMap, type Draft, type LatLng, type MapMode, type MapPoint } from "@/components/CampusMap";

import { Icon } from "@/components/Icon";
import { AdminOnly, Message, PageHead, StatusBadge, useSession } from "@/components/Shell";
import { api, useApi } from "@/lib/client";
import {
  EVENT_LABELS,
  formatArea,
  formatDateTime,
  parseLatLng,
  reasonLabel,
  statusLabel,
  statusTone,
} from "@/lib/format";
import type { AttendanceEvent, Campus, Geofence, LocationVerdict } from "@/lib/types";

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

const EMPTY_DRAFT: Draft = { polygon: [], circle: { center: null, radius: 80 } };

const MODE_HINTS: Record<MapMode, string> = {
  view: "Verde: geocerca activa. Gris punteado: inactiva. Los puntos son los últimos registros.",
  test: "Toca un punto del mapa para ver si una entrada desde ahí sería válida. No se guarda nada.",
  polygon: "Toca las esquinas del colegio en orden. Con tres o más puntos ya puedes guardar.",
  circle: "Toca el centro del colegio y ajusta el radio.",
};

function toneOf(status: string): MapPoint["tone"] {
  const tone = statusTone(status);
  return tone === "neutral" ? "warn" : tone;
}

/** The campus map: see the geofences, test a point, or draw a new geofence. */
function GeofenceMapPanel({ campus, geofences, onCreated }: {
  campus: Campus;
  geofences: Geofence[];
  onCreated: () => void;
}) {
  const { isAdmin } = useSession();
  const events = useApi<AttendanceEvent[]>(isAdmin ? "attendance/events?limit=200" : null);
  const [mode, setMode] = useState<MapMode>("view");
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [probe, setProbe] = useState<MapPoint | null>(null);
  const [verdict, setVerdict] = useState<LocationVerdict | null>(null);
  const [accuracy, setAccuracy] = useState(10);
  const [name, setName] = useState("Perímetro");
  const action = useFormAction();

  const points = useMemo<MapPoint[]>(
    () =>
      (events.data ?? [])
        .filter((e) => e.campus_id === campus.id && e.location)
        .slice(0, 60)
        .map((e) => ({
          id: e.id,
          position: [e.location?.latitude ?? 0, e.location?.longitude ?? 0] as LatLng,
          tone: toneOf(e.validation_status),
          label: `${EVENT_LABELS[e.event_type] ?? e.event_type}, ${formatDateTime(e.occurred_at)}: ${statusLabel(e.validation_status)}`,
        })),
    [events.data, campus.id],
  );

  function choose(next: MapMode) {
    setMode(next);
    setDraft(EMPTY_DRAFT);
    setProbe(null);
    setVerdict(null);
  }

  function onMapClick([lat, lng]: LatLng) {
    if (mode === "polygon") setDraft((d) => ({ ...d, polygon: [...d.polygon, [lat, lng]] }));
    if (mode === "circle") setDraft((d) => ({ ...d, circle: { ...d.circle, center: [lat, lng] } }));
    if (mode === "test") {
      void action.run(async () => {
        const result = await api<LocationVerdict>("geofences/check", {
          method: "POST",
          body: JSON.stringify({
            campus_id: campus.id,
            latitude: lat,
            longitude: lng,
            accuracy_m: accuracy,
            captured_at: new Date().toISOString(),
          }),
        });
        setVerdict(result);
        setProbe({ id: "probe", position: [lat, lng], tone: toneOf(result.verdict), label: statusLabel(result.verdict) });
      });
    }
  }

  const canSave =
    name.trim().length > 0 &&
    ((mode === "polygon" && draft.polygon.length >= 3) || (mode === "circle" && draft.circle.center !== null));

  function save() {
    void action.run(async () => {
      const body: Record<string, unknown> = { campus_id: campus.id, name: name.trim() };
      if (mode === "polygon") {
        const ring = draft.polygon.map(([lat, lng]) => [lng, lat]);
        const first = ring[0];
        if (first) ring.push(first); // GeoJSON rings are closed
        body.area = { type: "Polygon", coordinates: [ring] };
      } else if (draft.circle.center) {
        const [latitude, longitude] = draft.circle.center;
        body.center = { latitude, longitude };
        body.radius_m = draft.circle.radius;
      }
      await api<Geofence>("geofences", { method: "POST", body: JSON.stringify(body) });
      choose("view");
      onCreated();
      return `Geocerca "${name.trim()}" creada`;
    });
  }

  const modes: { value: MapMode; label: string }[] = [
    { value: "view", label: "Ver" },
    { value: "test", label: "Probar un punto" },
    ...(isAdmin
      ? [
          { value: "polygon" as const, label: "Dibujar polígono" },
          { value: "circle" as const, label: "Dibujar círculo" },
        ]
      : []),
  ];

  return (
    <div className="map-panel">
      <div className="panel-head" style={{ marginBottom: 10 }}>
        <div className="segmented" role="group" aria-label="Qué hacer en el mapa">
          {modes.map((m) => (
            <button key={m.value} type="button" aria-pressed={mode === m.value} onClick={() => choose(m.value)}>
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <p className="muted small" style={{ marginBottom: 10 }}>{MODE_HINTS[mode]}</p>
      {action.error && <Message tone="error">{action.error}</Message>}
      {action.message && mode === "view" && <Message tone="success">{action.message}</Message>}

      <CampusMap geofences={geofences} points={points} mode={mode} draft={draft} probe={probe} onMapClick={onMapClick} />

      {mode === "test" && (
        <div className="map-controls">
          <label>
            Precisión del GPS en metros
            <input
              type="number"
              min={0}
              max={200}
              value={accuracy}
              onChange={(e) => setAccuracy(Number(e.target.value))}
              style={{ width: 120 }}
            />
          </label>
          {verdict && (
            <div className="verdict" role="status">
              <StatusBadge status={verdict.verdict} />
              <strong>{statusLabel(verdict.geofence_result)} de la geocerca</strong>
              {verdict.distance_m !== null && verdict.distance_m > 0 && (
                <span className="muted">a {Math.round(verdict.distance_m)} m del borde</span>
              )}
              {verdict.reasons.length > 0 && <span className="muted">{verdict.reasons.map(reasonLabel).join(". ")}</span>}
            </div>
          )}
        </div>
      )}

      {(mode === "polygon" || mode === "circle") && (
        <div className="map-controls">
          {mode === "polygon" ? (
            <>
              <span className="muted num">
                {draft.polygon.length} {draft.polygon.length === 1 ? "punto" : "puntos"}
              </span>
              <button
                type="button"
                className="secondary small"
                disabled={draft.polygon.length === 0}
                onClick={() => setDraft((d) => ({ ...d, polygon: d.polygon.slice(0, -1) }))}
              >
                Deshacer punto
              </button>
              <button
                type="button"
                className="ghost small"
                disabled={draft.polygon.length === 0}
                onClick={() => setDraft(EMPTY_DRAFT)}
              >
                Empezar de nuevo
              </button>
            </>
          ) : (
            <label style={{ flex: "1 1 260px" }}>
              Radio: <span className="num">{draft.circle.radius} m</span>
              <input
                type="range"
                min={20}
                max={500}
                step={5}
                value={draft.circle.radius}
                onChange={(e) => setDraft((d) => ({ ...d, circle: { ...d.circle, radius: Number(e.target.value) } }))}
                style={{ padding: 0, minHeight: 0, border: 0, boxShadow: "none" }}
              />
            </label>
          )}
          <label>
            Nombre
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <button type="button" disabled={!canSave || action.busy} onClick={save}>
            Guardar geocerca
          </button>
          <button type="button" className="ghost" onClick={() => choose("view")}>
            Cancelar
          </button>
        </div>
      )}
    </div>
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
      {geofences.data && (
        <GeofenceMapPanel campus={campus} geofences={geofences.data} onCreated={geofences.reload} />
      )}
      {geofences.data && geofences.data.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 18 }}>
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
      <details className="manual">
        <summary>Ingresar coordenadas a mano</summary>
        <AdminOnly>
          <h3 className="subhead">Nueva geocerca</h3>
          <GeofenceForm campus={campus} onCreated={geofences.reload} />
        </AdminOnly>
        <h3 className="subhead">Probar una ubicación</h3>
        <LocationTester campus={campus} />
      </details>
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
