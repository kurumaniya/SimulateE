import { expect, test, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const TEST_TITLE = "RetroWeb Test";

async function batterySaveByte0(request: Page["request"], gameId: string): Promise<number | null> {
  const saves = await (await request.get(`${API}/api/games/${gameId}/saves?save_type=battery`)).json();
  if (!Array.isArray(saves) || saves.length === 0) return null;
  const body = await (await request.get(`${API}/api/saves/${saves[0].id}/download`)).body();
  return body[0];
}

async function playAndQuit(page: Page, gameId: string, resume: boolean) {
  await page.goto(`/play/${gameId}${resume ? "?resume=1" : ""}`);
  // The toolbar's pause button becomes enabled once the emulator reports "start".
  const pause = page.getByRole("button", { name: "Pause" });
  await expect(pause).toBeEnabled({ timeout: 90_000 });
  await expect(page.locator("canvas.ejs_canvas")).toBeVisible();
  // Let the homebrew program run its first frames and write SRAM.
  await page.waitForTimeout(3000);
  await quit(page, gameId);
}

/** The toolbar auto-hides while playing; Escape brings it back. */
async function quit(page: Page, gameId: string) {
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Quit game" }).click();
  await page.waitForURL(`**/games/${gameId}`, { timeout: 60_000 });
}

test("scan → library → play → save → quit → resume", async ({ page, request }) => {
  // Fresh state for this game: remove any saves left by a previous run.
  const scan = await request.post(`${API}/api/games/scan`);
  expect(scan.ok()).toBeTruthy();
  const list = await (await request.get(`${API}/api/games?q=${encodeURIComponent(TEST_TITLE)}`)).json();
  expect(list.total).toBeGreaterThan(0);
  const gameId: string = list.items[0].id;
  const existing = await (await request.get(`${API}/api/games/${gameId}/saves`)).json();
  for (const save of existing) await request.delete(`${API}/api/saves/${save.id}`);
  await page.addInitScript(() => indexedDB.deleteDatabase("retroweb"));

  // Library shows the scanned game.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recently Added" })).toBeVisible();
  await page.getByRole("link", { name: TEST_TITLE }).first().click();
  await expect(page.getByRole("heading", { name: TEST_TITLE })).toBeVisible();
  await expect(page.getByRole("button", { name: /Play/ })).toBeEnabled();

  // First play: the program writes counter=1 into SRAM.
  await playAndQuit(page, gameId, false);
  expect(await batterySaveByte0(request, gameId)).toBe(1);

  // A resume point (auto state) and play time were recorded.
  const detail = await (await request.get(`${API}/api/games/${gameId}`)).json();
  expect(detail.has_auto_state).toBe(true);
  expect(detail.play_time_seconds).toBeGreaterThan(0);
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();

  // Second play restores the save from the server: counter becomes 2.
  await playAndQuit(page, gameId, false);
  expect(await batterySaveByte0(request, gameId)).toBe(2);

  // Resume loads the auto state without errors.
  await page.goto(`/play/${gameId}?resume=1`);
  await expect(page.getByRole("button", { name: "Pause" })).toBeEnabled({ timeout: 90_000 });
  await expect(page.getByText("Resumed where you left off")).toBeVisible({ timeout: 15_000 });
  await quit(page, gameId);
});
