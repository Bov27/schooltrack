import { describe, expect, it } from "vitest";

import type { SecureStorage } from "./api";
import type { AttendanceEventRequest, SubjectState } from "./attendance";
import { MAX_QUEUE, OfflineQueue, QueueFullError, predictState, refusedMessages, settledKeys } from "./offline";

class MemoryStorage implements SecureStorage {
  data = new Map<string, string>();
  async get(key: string) {
    return this.data.get(key) ?? null;
  }
  async set(key: string, value: string) {
    this.data.set(key, value);
  }
  async remove(key: string) {
    this.data.delete(key);
  }
}

function request(key: string, eventType: AttendanceEventRequest["event_type"], at: string): AttendanceEventRequest {
  return {
    idempotency_key: key,
    event_type: eventType,
    campus_id: "campus",
    occurred_at: at,
    latitude: 2.44,
    longitude: -76.6,
    accuracy_m: 8,
    location_captured_at: at,
  };
}

const OUTSIDE: SubjectState = { subject: "STUDENT", subject_id: "s", state: "OUTSIDE", allowed_events: ["CHECK_IN"] };

describe("OfflineQueue", () => {
  it("stores events durably and lists them oldest first", async () => {
    const storage = new MemoryStorage();
    const queue = new OfflineQueue(storage);
    await queue.enqueue(request("b", "CHECK_OUT", "2027-02-01T12:00:00Z"));
    await queue.enqueue(request("a", "CHECK_IN", "2027-02-01T07:00:00Z"));
    // A new queue instance (app restart) sees the same items.
    const listed = await new OfflineQueue(storage).list();
    expect(listed.map((r) => r.idempotency_key)).toEqual(["a", "b"]);
  });

  it("ignores a duplicate enqueue of the same action", async () => {
    const queue = new OfflineQueue(new MemoryStorage());
    await queue.enqueue(request("a", "CHECK_IN", "2027-02-01T07:00:00Z"));
    await queue.enqueue(request("a", "CHECK_IN", "2027-02-01T07:00:00Z"));
    expect(await queue.keys()).toEqual(["a"]);
  });

  it("removes settled items and their data", async () => {
    const storage = new MemoryStorage();
    const queue = new OfflineQueue(storage);
    await queue.enqueue(request("a", "CHECK_IN", "2027-02-01T07:00:00Z"));
    await queue.enqueue(request("b", "CHECK_OUT", "2027-02-01T12:00:00Z"));
    await queue.remove(["a"]);
    expect(await queue.keys()).toEqual(["b"]);
    expect([...storage.data.keys()].some((k) => k.endsWith(".a"))).toBe(false);
  });

  it("refuses to grow beyond the batch limit", async () => {
    const queue = new OfflineQueue(new MemoryStorage());
    for (let i = 0; i < MAX_QUEUE; i++) await queue.enqueue(request(`k${i}`, "CHECK_IN", "2027-02-01T07:00:00Z"));
    await expect(queue.enqueue(request("extra", "CHECK_IN", "2027-02-01T07:00:00Z"))).rejects.toBeInstanceOf(
      QueueFullError,
    );
  });

  it("survives a corrupted index", async () => {
    const storage = new MemoryStorage();
    storage.data.set("schooltrack.offline.index", "{not json");
    expect(await new OfflineQueue(storage).keys()).toEqual([]);
  });
});

describe("predictState", () => {
  it("applies queued events to the last known server state", () => {
    const predicted = predictState(OUTSIDE, [
      request("a", "CHECK_IN", "2027-02-01T07:00:00Z"),
      request("b", "TEMPORARY_CHECK_OUT", "2027-02-01T10:00:00Z"),
    ]);
    expect(predicted.state).toBe("TEMPORARY_EXIT");
    expect(predicted.allowed_events).toEqual(["RETURN"]);
  });

  it("stops at an event the server would refuse", () => {
    const predicted = predictState(OUTSIDE, [request("a", "CHECK_OUT", "2027-02-01T07:00:00Z")]);
    expect(predicted.state).toBe("OUTSIDE");
  });
});

describe("sync results", () => {
  const results = [
    { idempotency_key: "a", outcome: "created" as const, status_code: 201 },
    { idempotency_key: "b", outcome: "replayed" as const, status_code: 200 },
    { idempotency_key: "c", outcome: "error" as const, status_code: 409, error: "out of order" },
    { idempotency_key: "d", outcome: "error" as const, status_code: 503, error: "busy" },
  ];

  it("keeps only items worth retrying", () => {
    expect(settledKeys(results)).toEqual(["a", "b", "c"]);
  });

  it("reports refusals to the user", () => {
    expect(refusedMessages(results)).toEqual(["out of order", "busy"]);
  });
});
