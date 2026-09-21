#!/usr/bin/env node
/**
 * Download the pinned EmulatorJS runtime and cores from the npm registry and
 * lay them out under apps/web/public/emulatorjs the way EmulatorJS expects.
 *
 * Nothing here touches game ROMs or BIOS files: these packages are the
 * emulator software only (GPL-3.0 and core-specific licenses).
 */
import { createWriteStream } from "node:fs";
import { mkdir, readFile, rm, writeFile, cp, stat } from "node:fs/promises";
import { pipeline } from "node:stream/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const VERSION = "4.2.3";
const CORES = ["mgba", "gambatte", "fceumm", "snes9x", "genesis_plus_gx", "pcsx_rearmed", "mupen64plus_next", "parallel_n64", "melonds", "desmume2015", "ppsspp", "yabause", "fbneo"];
const REGISTRY = process.env.NPM_REGISTRY ?? "https://registry.npmjs.org";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const target = path.join(root, "apps", "web", "public", "emulatorjs");
const work = path.join(root, "node_modules", ".cache", "emulatorjs-fetch");

async function download(url, dest) {
  const response = await fetch(url);
  if (!response.ok || !response.body) {
    throw new Error(`Download failed (${response.status}): ${url}`);
  }
  await mkdir(path.dirname(dest), { recursive: true });
  await pipeline(response.body, createWriteStream(dest));
}

function extract(tarball, into) {
  // Relative paths from a shared cwd: GNU tar (Git Bash on Windows) would read
  // an absolute `C:\...` as a remote host name.
  const cwd = path.dirname(tarball);
  return new Promise((resolve, reject) => {
    const child = spawn(
      "tar",
      ["-xzf", path.basename(tarball), "-C", path.relative(cwd, into) || "."],
      { stdio: "inherit", cwd },
    );
    child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`tar exited ${code}`))));
    child.on("error", reject);
  });
}

async function fetchPackage(name, version) {
  const bare = name.replace("@emulatorjs/", "");
  const url = `${REGISTRY}/${name}/-/${bare}-${version}.tgz`;
  const tarball = path.join(work, `${bare}-${version}.tgz`);
  const dir = path.join(work, `${bare}-${version}`);
  await rm(dir, { recursive: true, force: true });
  await mkdir(dir, { recursive: true });
  console.log(`Downloading ${name}@${version}`);
  await download(url, tarball);
  await extract(tarball, dir);
  return path.join(dir, "package");
}

async function main() {
  const marker = path.join(target, "retroweb-manifest.json");
  try {
    const existing = JSON.parse(await readFile(marker, "utf8"));
    if (existing.version === VERSION && CORES.every((c) => existing.cores.includes(c))) {
      console.log(`EmulatorJS ${VERSION} with cores [${CORES}] already installed.`);
      return;
    }
  } catch {
    // not installed yet
  }

  await rm(target, { recursive: true, force: true });
  await mkdir(target, { recursive: true });

  const runtime = await fetchPackage("@emulatorjs/emulatorjs", VERSION);
  const data = path.join(runtime, "data");
  for (const entry of ["loader.js", "emulator.css", "version.json", "src", "localization", "compression"]) {
    await cp(path.join(data, entry), path.join(target, entry), { recursive: true });
  }
  await writeFile(path.join(target, "LICENSE"), await readFile(path.join(runtime, "LICENSE")));

  await mkdir(path.join(target, "cores", "reports"), { recursive: true });
  for (const core of CORES) {
    const pkg = await fetchPackage(`@emulatorjs/core-${core}`, VERSION);
    for (const suffix of ["-wasm.data", "-legacy-wasm.data", "-thread-wasm.data", "-thread-legacy-wasm.data"]) {
      const file = `${core}${suffix}`;
      try {
        await stat(path.join(pkg, file));
      } catch {
        continue;
      }
      await cp(path.join(pkg, file), path.join(target, "cores", file));
    }
    await cp(path.join(pkg, "reports", `${core}.json`), path.join(target, "cores", "reports", `${core}.json`));
    // PPSSPP ships its runtime assets (flash0, compat.ini, fonts) as a zip the
    // runtime fetches from cores/ppsspp-assets.zip.
    const assets = `${core}-assets.zip`;
    try {
      await stat(path.join(pkg, assets));
      await cp(path.join(pkg, assets), path.join(target, "cores", assets));
    } catch {
      // core has no asset bundle
    }
  }

  await writeFile(marker, JSON.stringify({ version: VERSION, cores: CORES, fetchedAt: new Date().toISOString() }, null, 2));
  console.log(`Installed EmulatorJS ${VERSION} into ${path.relative(root, target)}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
