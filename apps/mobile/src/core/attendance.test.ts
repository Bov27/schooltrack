import { describe, expect, it } from "vitest";

import {
  type AttendanceEvent,
  buildEventRequest,
  describeOutcome,
  ownHistoryPath,
  reasonMessage,
  withRetries,
} from "./attendance";

const FIX = { latitude: 2.4419, longitude: -76.6063, accuracy: 8, timestamp: Date.UTC(2027, 1, 1, 12) };

describe("buildEventRequest", () => {
  it("maps a location fix to the API request", () => {
    const request = buildEventRequest({
      eventType: "CHECK_IN",
      campusId: "campus-1",
      fix: FIX,
      idempotencyKey: "key-1",
      occurredAt: new Date(Date.UTC(2027, 1, 1, 12, 0, 2)),
    });
    expect(request).toEqual({
      idempotency_key: "key-1",
      event_type: "CHECK_IN",
      campus_id: "campus-1",
      occurred_at: "2027-02-01T12:00:02.000Z",
      latitude: 2.4419,
      longitude: -76.6063,
      accuracy_m: 8,
      location_captured_at: "2027-02-01T12:00:00.000Z",
    });
  });

  it("forwards the OS mock-location flag when present", () => {
    const request = buildEventRequest({
      eventType: "CHECK_OUT",
      campusId: "c",
      fix: { ...FIX, mocked: true },
      idempotencyKey: "k",
      occurredAt: new Date(),
    });
    expect(request.is_mock).toBe(true);
  });

  it("never claims precision it does not have", () => {
    const request = buildEventRequest({
      eventType: "CHECK_IN",
      campusId: "c",
      fix: { ...FIX, accuracy: null },
      idempotencyKey: "k",
      occurredAt: new Date(),
    });
    expect(request.accuracy_m).toBeGreaterThan(1000);
  });
});

describe("describeOutcome", () => {
  const base: AttendanceEvent = {
    id: "e",
    event_type: "CHECK_IN",
    state_after: "PRESENT",
    validation_status: "VALIDATED",
    validation_reasons: [],
    occurred_at: "",
    campus_id: "c",
  };

  it("confirms a validated event", () => {
    expect(describeOutcome(base, false)).toEqual({ tone: "ok", title: "Registrar entrada: listo", details: [] });
  });

  it("explains a rejection in plain language", () => {
    const outcome = describeOutcome({ ...base, validation_status: "REJECTED", validation_reasons: ["OUTSIDE_GEOFENCE"] }, false);
    expect(outcome.tone).toBe("bad");
    expect(outcome.details).toEqual(["Estás fuera del área de la sede."]);
  });

  it("tells the user when a retry was recognised as already recorded", () => {
    expect(describeOutcome(base, true).details[0]).toMatch(/no se duplicó/);
  });

  it("flags review cases", () => {
    expect(describeOutcome({ ...base, validation_status: "FLAGGED_FOR_REVIEW" }, false).tone).toBe("warn");
  });

  it("passes unknown reason codes through", () => {
    expect(reasonMessage("NEW_RULE")).toBe("NEW_RULE");
  });
});

describe("withRetries", () => {
  const noDelay = async () => undefined;

  it("retries network failures and succeeds", async () => {
    let attempts = 0;
    const result = await withRetries(
      async () => {
        attempts++;
        if (attempts < 3) throw new TypeError("Network request failed");
        return "ok";
      },
      (e) => e instanceof TypeError,
      3,
      noDelay,
    );
    expect(result).toBe("ok");
    expect(attempts).toBe(3);
  });

  it("does not retry answers from the server", async () => {
    let attempts = 0;
    await expect(
      withRetries(
        async () => {
          attempts++;
          throw new Error("409 conflict");
        },
        (e) => e instanceof TypeError,
        3,
        noDelay,
      ),
    ).rejects.toThrow("409");
    expect(attempts).toBe(1);
  });

  it("gives up after the last attempt", async () => {
    await expect(
      withRetries(async () => Promise.reject(new TypeError("offline")), () => true, 2, noDelay),
    ).rejects.toThrow("offline");
  });
});

describe("ownHistoryPath", () => {
  it("asks only for the user's own events", () => {
    expect(
      ownHistoryPath({ subject: "STUDENT", subject_id: "s-1", state: "OUTSIDE", allowed_events: ["CHECK_IN"] }),
    ).toBe("attendance/events?limit=15&student_id=s-1");
    expect(
      ownHistoryPath({ subject: "STAFF", subject_id: "t-1", state: "PRESENT", allowed_events: [] }, 5),
    ).toBe("attendance/events?limit=5&staff_id=t-1");
  });

  it("loads no history for an account without a student or staff record", () => {
    expect(ownHistoryPath(null)).toBeNull();
  });
});
