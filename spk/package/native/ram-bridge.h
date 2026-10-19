#ifndef NUTRAM_BRIDGE_H
#define NUTRAM_BRIDGE_H

/* PRIVATE LOCAL PROTOTYPE. Not installed and not a new setuid executable.
 * The future hostctl links this module and supplies a compiled, bounded phase
 * implementation. A caller cannot select a callback, path, unit or shell code.
 * Callbacks run synchronously, return, and do not re-enter bridge dispatch.
 */
enum nutram_phase {
    NUTRAM_PREPARE, NUTRAM_ENSURE, NUTRAM_AUDIT, NUTRAM_CORE, NUTRAM_HEALTH,
    NUTRAM_START, NUTRAM_CONTROLLER_STOP, NUTRAM_RUNTIME_STOP,
    NUTRAM_QUIESCENT, NUTRAM_RELEASE, NUTRAM_CLEANUP, NUTRAM_SAFE_ENTRY,
    NUTRAM_USB_PRESENT
};
/* CORE: 0 exact live pair, 75 none, 76 driver-only, otherwise fatal.
 * HEALTH: 0 ready, 1 unavailable data, otherwise infrastructure error.
 * START: 0 protocol-ready, 75 unavailable USB after confirmed safe unwind,
 *        otherwise fatal. PREPARE must never stop/adopt a foreign runtime.
 * SAFE_ENTRY: 0 only for fresh validated safe-entry; everything else stops.
 * Other phases: 0 success; any other result aborts without later phases.
 * USB_PRESENT: 0 exact device, 75 absent/enumerating, otherwise fatal.
 * CLEANUP excludes the fixed version-independent coordination files. They
 * survive stop/uninstall until reboot; control payload is retired by bridge.
 */
int nutram_bridge_dispatch(int argc, char **argv, int (*phase)(enum nutram_phase));
#endif
