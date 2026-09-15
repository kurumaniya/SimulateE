import { expect, test, type Page } from "@playwright/test";

/**
 * Every supported system runs the same homebrew program (scripts/make-test-rom.py):
 * bump a counter in battery RAM on boot. Two play sessions must therefore leave
 * the server-side battery save at 1 and then 2, proving the save round-trip.
 */
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const TEST_TITLE = "RetroWeb Test";

interface SystemCase {
  system: string;
  /** Index of the boot counter inside the battery save file. */
  counterIndex: number;
}

const SYSTEMS: SystemCase[] = [
  { system: "gba", counterIndex: 0 },
  { system: "gb", counterIndex: 0 },
  { system: "gbc", counterIndex: 0 },
  { system: "nes", counterIndex: 0 },
  { system: "snes", counterIndex: 0 },
  { system: "genesis", counterIndex: 1 },
];

/**
 * Systems whose test program does not write its save: the round-trip is
 * checked by injecting bytes into the save the emulator produced and
 * verifying they come back unchanged after another session.
 */
const INJECTION_SYSTEMS: { system: string; probeOffset: number }[] = [
  { system: "ps1", probeOffset: 0x2080 }, // inside memory card block 1
  { system: "n64", probeOffset: 0x100 }, // inside the EEPROM area
];

async function batterySaveByte(request: Page["request"], gameId: string, index: number) {
  const saves = await (await request.get(`${API}/api/games/${gameId}/saves?save_type=battery`)).json();
  if (!Array.isArray(saves) || saves.length === 0) return null;
  const body = await (await request.get(`${API}/api/saves/${saves[0].id}/download`)).body();
  return body[index];
}

/** The toolbar auto-hides while playing; Escape brings it back. */
async function quit(page: Page, gameId: string) {
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Quit game" }).click();
  await page.waitForURL(`**/games/${gameId}`, { timeout: 60_000 });
}

async function playAndQuit(page: Page, gameId: string, resume = false) {
  await page.goto(`/play/${gameId}${resume ? "?resume=1" : ""}`);
  // The toolbar's pause button becomes enabled once the emulator reports "start".
  await expect(page.getByRole("button", { name: "Pause" })).toBeEnabled({ timeout: 90_000 });
  await expect(page.locator("canvas.ejs_canvas")).toBeVisible();
  // Let the homebrew program run its first frames and write battery RAM.
  await page.waitForTimeout(3000);
  await quit(page, gameId);
}

async function findTestGame(request: Page["request"], system: string): Promise<string> {
  const list = await (
    await request.get(`${API}/api/games?q=${encodeURIComponent(TEST_TITLE)}&system=${system}`)
  ).json();
  expect(list.total, `test ROM for ${system} must be scanned`).toBeGreaterThan(0);
  const gameId: string = list.items[0].id;
  const existing = await (await request.get(`${API}/api/games/${gameId}/saves`)).json();
  for (const save of existing) await request.delete(`${API}/api/saves/${save.id}`);
  return gameId;
}

test.beforeAll(async ({ request }) => {
  const scan = await request.post(`${API}/api/games/scan`);
  expect(scan.ok()).toBeTruthy();
});

test("library shows the scanned game and its details", async ({ page, request }) => {
  const gameId = await findTestGame(request, "gba");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recently Added" })).toBeVisible();
  await page.goto(`/games/${gameId}`);
  await expect(page.getByRole("heading", { name: TEST_TITLE })).toBeVisible();
  await expect(page.getByRole("button", { name: /Play/ })).toBeEnabled();
});

for (const { system, counterIndex } of SYSTEMS) {
  test(`${system}: play → save → quit → replay restores the save`, async ({ page, request }) => {
    const gameId = await findTestGame(request, system);
    await page.addInitScript(() => indexedDB.deleteDatabase("retroweb"));

    await playAndQuit(page, gameId);
    expect(await batterySaveByte(request, gameId, counterIndex)).toBe(1);

    const detail = await (await request.get(`${API}/api/games/${gameId}`)).json();
    expect(detail.has_auto_state).toBe(true);
    expect(detail.play_time_seconds).toBeGreaterThan(0);

    await playAndQuit(page, gameId);
    expect(await batterySaveByte(request, gameId, counterIndex)).toBe(2);
  });
}

for (const { system, probeOffset } of INJECTION_SYSTEMS) {
  test(`${system}: boots, and an uploaded save is restored into the emulator`, async ({
    page,
    request,
  }) => {
    const gameId = await findTestGame(request, system);
    await page.addInitScript(() => indexedDB.deleteDatabase("retroweb"));

    // First session: the emulator writes whatever save file the core keeps.
    await playAndQuit(page, gameId);
    const saves = await (await request.get(`${API}/api/games/${gameId}/saves?save_type=battery`)).json();
    expect(saves.length, "core should produce a battery save").toBe(1);
    const original = Buffer.from(await (await request.get(`${API}/api/saves/${saves[0].id}/download`)).body());
    expect(original.length).toBeGreaterThan(probeOffset + 4);

    // Plant a marker on the server and play again: it must survive the trip
    // server → emulator → server.
    const marked = Buffer.from(original);
    marked.writeUInt32BE(0x52574542, probeOffset); // "RWEB"
    const upload = await request.post(`${API}/api/games/${gameId}/saves`, {
      multipart: {
        file: { name: "battery.sav", mimeType: "application/octet-stream", buffer: marked },
        save_type: "battery",
        slot: "0",
        emulator_id: "e2e",
        client_modified_at: new Date(Date.now() + 60_000).toISOString(),
      },
    });
    expect(upload.ok(), await upload.text()).toBeTruthy();

    await playAndQuit(page, gameId);
    const after = Buffer.from(await (await request.get(`${API}/api/saves/${saves[0].id}/download`)).body());
    expect(after.length).toBe(original.length);
    expect(after.readUInt32BE(probeOffset)).toBe(0x52574542);
  });
}

test("gba: resume loads the automatic save state", async ({ page, request }) => {
  const gameId = await findTestGame(request, "gba");
  await playAndQuit(page, gameId);
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await page.goto(`/play/${gameId}?resume=1`);
  await expect(page.getByRole("button", { name: "Pause" })).toBeEnabled({ timeout: 90_000 });
  await expect(page.getByText("Resumed where you left off")).toBeVisible({ timeout: 15_000 });
  await quit(page, gameId);
});
