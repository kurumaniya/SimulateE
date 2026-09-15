import { chromium } from "@playwright/test";
const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
for (const system of ["ps1", "n64"]) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  const logs = [];
  page.on("console", (m) => { const t = m.text(); if (!/DevTools|GL Driver|ERR_TUNNEL/.test(t)) logs.push(`[${m.type()}] ${t.slice(0, 300)}`); });
  page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message.slice(0, 300)}`));
  const list = await (await page.request.get(`http://localhost:8000/api/games?system=${system}`)).json();
  const id = list.items[0].id;
  await page.goto(`http://localhost:3000/play/${id}`);
  const started = await page.waitForFunction(() => { const b = document.querySelector('button[aria-label="Pause"]'); return b && !b.disabled; }, null, { timeout: 60000 }).then(() => true).catch(() => false);
  await page.waitForTimeout(3000);
  const info = await page.evaluate(() => {
    const host = document.querySelector(".retroweb-emulator-host > div");
    const emu = host && host.__emulatorjs;
    const out = { hasEmu: !!emu, statusText: document.querySelector("h2")?.textContent, statusDetail: document.querySelector("h2 + p")?.textContent };
    if (emu) {
      out.started = emu.started; out.failedToStart = emu.failedToStart; out.textElem = emu.textElem?.innerText;
      out.coreName = emu.coreName; out.fileName = emu.fileName; out.saveFileExt = emu.saveFileExt; out.extensions = emu.extensions;
      try { const p = emu.gameManager.getSaveFilePath(); out.savePath = p; out.saveExists = emu.gameManager.FS.analyzePath(p).exists; } catch (e) { out.saveErr = String(e); }
      try { const f = emu.gameManager.getSaveFile(); out.saveLen = f ? f.length : null; } catch (e) { out.saveFileErr = String(e); }
      try { out.rootFiles = emu.gameManager.FS.readdir("/"); } catch (e) {}
    }
    return out;
  });
  console.log("=====", system, "started:", started); console.log(JSON.stringify(info, null, 1)); console.log(logs.slice(0, 25).join("\n"));
  await page.screenshot({ path: `${process.env.S}/p3-${system}.png` });
  await page.close();
}
await browser.close();
