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

test("gba: resume loads the automatic save state", async ({ page, request }) => {
  const gameId = await findTestGame(request, "gba");
  await playAndQuit(page, gameId);
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await page.goto(`/play/${gameId}?resume=1`);
  await expect(page.getByRole("button", { name: "Pause" })).toBeEnabled({ timeout: 90_000 });
  await expect(page.getByText("Resumed where you left off")).toBeVisible({ timeout: 15_000 });
  await quit(page, gameId);
});
