/**
 * Platform-wide virtual controller vocabulary.
 *
 * Every adapter maps these to its own input model, so a future remapping UI
 * only ever talks about virtual buttons. Phase 1 exposes the default GBA
 * keyboard layout (EmulatorJS handles the actual key/gamepad reading).
 */
export enum VirtualButton {
  UP = "UP",
  DOWN = "DOWN",
  LEFT = "LEFT",
  RIGHT = "RIGHT",
  A = "A",
  B = "B",
  X = "X",
  Y = "Y",
  L = "L",
  R = "R",
  L2 = "L2",
  R2 = "R2",
  START = "START",
  SELECT = "SELECT",
  LEFT_STICK = "LEFT_STICK",
  RIGHT_STICK = "RIGHT_STICK",
}

export interface InputBinding {
  button: VirtualButton;
  keyboard: string;
  /** Standard Gamepad API button index (Xbox / PlayStation share it). */
  gamepad?: number;
}

/** EmulatorJS defaults for the libretro "RetroPad", which mGBA uses. */
export const DEFAULT_GBA_BINDINGS: InputBinding[] = [
  { button: VirtualButton.UP, keyboard: "ArrowUp", gamepad: 12 },
  { button: VirtualButton.DOWN, keyboard: "ArrowDown", gamepad: 13 },
  { button: VirtualButton.LEFT, keyboard: "ArrowLeft", gamepad: 14 },
  { button: VirtualButton.RIGHT, keyboard: "ArrowRight", gamepad: 15 },
  // Keys from EmulatorJS `defaultControllers` (libretro ids 8=A, 0=B, 9=X, 1=Y).
  { button: VirtualButton.A, keyboard: "z", gamepad: 0 },
  { button: VirtualButton.B, keyboard: "x", gamepad: 1 },
  { button: VirtualButton.L, keyboard: "q", gamepad: 4 },
  { button: VirtualButton.R, keyboard: "e", gamepad: 5 },
  { button: VirtualButton.START, keyboard: "Enter", gamepad: 9 },
  { button: VirtualButton.SELECT, keyboard: "v", gamepad: 8 },
];
