/**
 * Directory-tree saves for cores that keep a virtual memory stick (PPSSPP)
 * instead of one SRAM file. The tree is moved as an uncompressed POSIX
 * ustar archive so the server-side "battery save" stays one opaque blob and
 * the file can be inspected with any tar tool.
 */
import type { EjsFileSystem } from "./types";

const BLOCK = 512;
const encoder = new TextEncoder();
const decoder = new TextDecoder();

interface Entry {
  /** Path relative to the packed root, "/"-separated. */
  path: string;
  data: Uint8Array;
  mtimeSeconds: number;
}

function listFiles(fs: EjsFileSystem, root: string, prefix = ""): Entry[] {
  const entries: Entry[] = [];
  for (const name of fs.readdir(root)) {
    if (name === "." || name === "..") continue;
    const full = `${root}/${name}`;
    const stat = fs.stat(full);
    const relative = prefix ? `${prefix}/${name}` : name;
    if (fs.isDir(stat.mode)) {
      entries.push(...listFiles(fs, full, relative));
    } else {
      entries.push({
        path: relative,
        data: fs.readFile(full),
        mtimeSeconds: Math.floor(stat.mtime.getTime() / 1000),
      });
    }
  }
  return entries;
}

function writeField(header: Uint8Array, offset: number, length: number, value: string): void {
  const bytes = encoder.encode(value);
  header.set(bytes.subarray(0, length), offset);
}

function octal(value: number, length: number): string {
  return value.toString(8).padStart(length - 1, "0");
}

function splitName(path: string): { name: string; prefix: string } {
  if (encoder.encode(path).length <= 100) return { name: path, prefix: "" };
  const slash = path.lastIndexOf("/", 100);
  if (slash <= 0 || encoder.encode(path.slice(slash + 1)).length > 100) {
    throw new Error(`Path too long for a tar entry: ${path}`);
  }
  return { name: path.slice(slash + 1), prefix: path.slice(0, slash) };
}

function header(entry: Entry): Uint8Array {
  const block = new Uint8Array(BLOCK);
  const { name, prefix } = splitName(entry.path);
  writeField(block, 0, 100, name);
  writeField(block, 100, 8, octal(0o644, 8));
  writeField(block, 108, 8, octal(0, 8));
  writeField(block, 116, 8, octal(0, 8));
  writeField(block, 124, 12, octal(entry.data.length, 12));
  writeField(block, 136, 12, octal(Math.max(0, entry.mtimeSeconds), 12));
  block.fill(0x20, 148, 156); // checksum field counts as spaces
  block[156] = 0x30; // '0': regular file
  writeField(block, 257, 6, "ustar\0");
  writeField(block, 263, 2, "00");
  writeField(block, 345, 155, prefix);
  let sum = 0;
  for (const byte of block) sum += byte;
  writeField(block, 148, 8, `${octal(sum, 7)}\0`);
  return block;
}

/** Pack every file below `root` (recursively). Returns null when empty. */
export function packTree(fs: EjsFileSystem, root: string): Uint8Array | null {
  if (!fs.analyzePath(root).exists) return null;
  const entries = listFiles(fs, root);
  if (entries.length === 0) return null;
  const chunks: Uint8Array[] = [];
  for (const entry of entries) {
    chunks.push(header(entry));
    chunks.push(entry.data);
    const padding = (BLOCK - (entry.data.length % BLOCK)) % BLOCK;
    if (padding) chunks.push(new Uint8Array(padding));
  }
  chunks.push(new Uint8Array(BLOCK * 2));
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

function readField(block: Uint8Array, offset: number, length: number): string {
  const slice = block.subarray(offset, offset + length);
  const end = slice.indexOf(0);
  return decoder.decode(end === -1 ? slice : slice.subarray(0, end));
}

/** Directories are implicit: every parent of a file path is created. */
export function ensureDirectory(fs: EjsFileSystem, path: string): void {
  const parts = path.split("/").filter(Boolean);
  let current = "";
  for (const part of parts) {
    current += `/${part}`;
    if (!fs.analyzePath(current).exists) fs.mkdir(current);
  }
}

/** Unpack an archive produced by `packTree` below `root` (which is created). */
export function unpackTree(fs: EjsFileSystem, root: string, archive: Uint8Array): void {
  ensureDirectory(fs, root);
  let offset = 0;
  while (offset + BLOCK <= archive.length) {
    const block = archive.subarray(offset, offset + BLOCK);
    offset += BLOCK;
    if (block.every((byte) => byte === 0)) break;
    const name = readField(block, 0, 100);
    const prefix = readField(block, 345, 155);
    const size = parseInt(readField(block, 124, 12).trim() || "0", 8);
    const type = block[156];
    const relative = (prefix ? `${prefix}/${name}` : name).replace(/^\/+/, "");
    const data = archive.subarray(offset, offset + size);
    offset += Math.ceil(size / BLOCK) * BLOCK;
    if (type !== 0x30 && type !== 0) continue; // only regular files are stored
    if (relative.split("/").some((part) => part === "..")) {
      throw new Error(`Refusing tar entry that escapes the save directory: ${relative}`);
    }
    const target = `${root}/${relative}`;
    ensureDirectory(fs, target.slice(0, target.lastIndexOf("/")));
    if (fs.analyzePath(target).exists) fs.unlink(target);
    fs.writeFile(target, new Uint8Array(data));
  }
}

/** Delete everything below `root`, keeping `root` itself. */
export function clearTree(fs: EjsFileSystem, root: string): void {
  if (!fs.analyzePath(root).exists) return;
  for (const name of fs.readdir(root)) {
    if (name === "." || name === "..") continue;
    const full = `${root}/${name}`;
    if (fs.isDir(fs.stat(full).mode)) {
      clearTree(fs, full);
      fs.rmdir(full);
    } else {
      fs.unlink(full);
    }
  }
}
