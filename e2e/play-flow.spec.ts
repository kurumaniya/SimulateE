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
  /** How long to let the program run before quitting (default 3 s). */
  settleMs?: number;
  /** Reads the counter out of the save blob when it is not a flat byte array. */
  extract?: (save: Buffer) => number;
}

/**
 * PSP saves travel as an uncompressed tar of the memory stick's PSP/SAVEDATA
 * tree; the test program keeps its counter in RWEB00001/COUNTER.BIN.
 */
function counterFromMemstickTar(save: Buffer): number {
  let offset = 0;
  while (offset + 512 <= save.length) {
    const name = save.subarray(offset, offset + 100).toString("utf8").replace(/\0.*$/, "");
    if (!name) break;
    const size = parseInt(save.subarray(offset + 124, offset + 136).toString("utf8").trim(), 8);
    if (name === "RWEB00001/COUNTER.BIN") return save[offset + 512];
    offset += 512 + Math.ceil(size / 512) * 512;
  }
  throw new Error("RWEB00001/COUNTER.BIN not found in the PSP save archive");
}

const SYSTEMS: SystemCase[] = [
  { system: "gba", counterIndex: 0 },
  { system: "gb", counterIndex: 0 },
  { system: "gbc", counterIndex: 0 },
  { system: "nes", counterIndex: 0 },
  { system: "snes", counterIndex: 0 },
  { system: "genesis", counterIndex: 1 },
  // melonDS writes the cart save to disk about three seconds after the last EEPROM write.
  { system: "nds", counterIndex: 0, settleMs: 6000 },
  { system: "psp", counterIndex: 0, extract: counterFromMemstickTar },
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

async function waitForRunning(page: Page) {
  // The toolbar's pause button becomes enabled once the emulator reports "start".
  await expect(page.getByRole("button", { name: "Pause" })).toBeEnabled({ timeout: 90_000 });
  await expect(page.locator("canvas.ejs_canvas")).toBeVisible();
}

async function playAndQuit(page: Page, gameId: string, resume = false, settleMs = 3000) {
  await page.goto(`/play/${gameId}${resume ? "?resume=1" : ""}`);
  await waitForRunning(page);
  // Let the homebrew program run its first frames and write battery RAM.
  await page.waitForTimeout(settleMs);
  await quit(page, gameId);
}

async function batterySave(request: Page["request"], gameId: string): Promise<Buffer> {
  const saves = await (await request.get(`${API}/api/games/${gameId}/saves?save_type=battery`)).json();
  expect(saves.length, "core should produce a battery save").toBe(1);
  return Buffer.from(await (await request.get(`${API}/api/saves/${saves[0].id}/download`)).body());
}

/**
 * Centre of the DS bottom screen in page coordinates. melonDS letterboxes its
 * framebuffer inside the canvas: in a landscape window the vertical layout
 * fills the height and the side-by-side layout fills the width.
 */
async function bottomScreenCentre(page: Page, layout: "top-bottom" | "left-right") {
  const box = await page.locator("canvas.ejs_canvas").boundingBox();
  expect(box).not.toBeNull();
  const { x, y, width, height } = box!;
  return layout === "top-bottom"
    ? { x: x + width / 2, y: y + height * 0.75 }
    : { x: x + width * 0.75, y: y + height / 2 };
}

/**
 * Press and hold for a few frames: the core samples the pointer once per
 * emulated frame, so a zero-length click can fall between two samples.
 */
async function holdMouse(page: Page, point: { x: number; y: number }) {
  await page.mouse.move(point.x, point.y);
  await page.mouse.down();
  await page.waitForTimeout(150);
  await page.mouse.up();
}

/** Same for a finger: Playwright's `tap` has no duration, so drive CDP directly. */
async function holdFinger(page: Page, point: { x: number; y: number }) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point] });
  await page.waitForTimeout(150);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await cdp.detach();
}

/** The NDS test program logs each touch to EEPROM 0x10 as 'T', count, x, y. */
function expectTouchLog(save: Buffer, touches: number) {
  expect(save[0x10]).toBe(0x54);
  expect(save[0x11]).toBe(touches);
  // Screen centre is (128, 96); allow for letterbox rounding.
  expect(Math.abs(save[0x12] - 128)).toBeLessThan(24);
  expect(Math.abs(save[0x13] - 96)).toBeLessThan(24);
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

for (const { system, counterIndex, settleMs, extract } of SYSTEMS) {
  test(`${system}: play → save → quit → replay restores the save`, async ({ page, request }) => {
    const gameId = await findTestGame(request, system);
    await page.addInitScript(() => indexedDB.deleteDatabase("retroweb"));
    const counter = async () =>
      extract ? extract(await batterySave(request, gameId)) : batterySaveByte(request, gameId, counterIndex);

    await playAndQuit(page, gameId, false, settleMs);
    expect(await counter()).toBe(1);

    const detail = await (await request.get(`${API}/api/games/${gameId}`)).json();
    expect(detail.has_auto_state).toBe(true);
    expect(detail.play_time_seconds).toBeGreaterThan(0);

    await playAndQuit(page, gameId, false, settleMs);
    expect(await counter()).toBe(2);
  });
}

test("nds: mouse touches and screen layouts reach the core", async ({ page, request }) => {
  const gameId = await findTestGame(request, "nds");
  await page.addInitScript(() => indexedDB.deleteDatabase("retroweb"));
  await page.goto(`/play/${gameId}`);
  await waitForRunning(page);
  const layoutPicker = page.getByLabel("Screen layout");
  await expect(layoutPicker).toHaveValue("top-bottom");
  await page.waitForTimeout(1500);

  // Touch mode must not lock the pointer on click, or the second click would never land.
  await holdMouse(page, await bottomScreenCentre(page, "top-bottom"));
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => document.pointerLockElement)).toBeNull();

  await page.keyboard.press("Escape");
  await layoutPicker.selectOption("left-right");
  await page.waitForTimeout(1500);
  await holdMouse(page, await bottomScreenCentre(page, "left-right"));
  await page.waitForTimeout(6000);
  await quit(page, gameId);

  expectTouchLog(await batterySave(request, gameId), 2);
});

test.describe("touch screen", () => {
  test.use({ hasTouch: true });

  test("nds: finger taps reach the core", async ({ page, request }) => {
    const gameId = await findTestGame(request, "nds");
    await page.addInitScript(() => indexedDB.deleteDatabase("retroweb"));
    await page.goto(`/play/${gameId}`);
    await waitForRunning(page);
    await page.waitForTimeout(1500);
    await holdFinger(page, await bottomScreenCentre(page, "top-bottom"));
    await page.waitForTimeout(6000);
    await quit(page, gameId);
    expectTouchLog(await batterySave(request, gameId), 1);
  });
});

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
