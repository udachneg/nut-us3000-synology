#ifndef NUTRAM_RUNTIME_H
#define NUTRAM_RUNTIME_H
#include "ram-bridge.h"
/* Private compiled phase binding, not caller-selected callbacks or commands.
 * START, CORE, HEALTH, RUNTIME_STOP and QUIESCENT use the fixed executor. Other
 * phases are the compiled ram-platform/hostctl binding, not caller input.
 * HEALTH: 0 both endpoints ready, 1 known unavailable data, 2 unknown/fatal.
 * CORE: 0 exact pair, 75 proven absent, 76 exact driver only, 2 ambiguous/fatal.
 * Unit snapshots bracket a bounded proc inventory (exe/comm/all UID/GID fields,
 * starttime and cgroup v1); these observations do not guarantee future liveness.
 * RUNTIME_STOP: 0 both stop jobs succeeded. This alone never permits release.
 * QUIESCENT: both units report dead/zero PIDs, then the bounded authenticated
 * kernel checker finds no RAM cgroup members/executables/listeners/UNIX sockets.
 * Exact not-found/inactive/dead/zero/empty-group also permits quiescence after
 * failed first preparation, never CORE/start. Stop-job failure is tolerated only
 * with that independently read missing-unit snapshot, not merely its exit code.
 * START: caller has already prepared/authenticated/loaded units and audited host
 * integration. Requires absent core and USB, starts driver/server, permits a3s
 * Type=simple exec convergence window with bounded observations, then
 * polls both endpoints as package UID within a20s shared readiness budget.
 * Failure after a start attempt stops/proves quiescence, never releases/erases.
 * 75 means absent USB before launch, or observed unavailable data followed by
 * confirmed clean unwind. Connection-refused is transient only during startup;
 * alone it cannot authorize75. Unknown state/unconfirmed unwind is fatal1.
 */
int nutram_runtime_phase(enum nutram_phase phase, int (*remaining)(enum nutram_phase));
#endif
