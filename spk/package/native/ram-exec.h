#ifndef NUTRAM_EXEC_H
#define NUTRAM_EXEC_H
#include <stddef.h>

/* Private, synchronous, single-threaded native-helper API. No user-supplied
 * paths, arguments, environment, UID or timeout. Not a standalone executable.
 * Call only after bridge authenticates its control directory and holds locks.
 */
enum nutram_operation {
    NUTRAM_START_DRIVER, NUTRAM_START_SERVER,
    NUTRAM_STOP_SERVER, NUTRAM_STOP_DRIVER,
    NUTRAM_SHOW_DRIVER, NUTRAM_SHOW_SERVER,
    NUTRAM_QUERY_LOCAL, NUTRAM_QUERY_ALIAS, NUTRAM_KERNEL_QUIESCENT,
    NUTRAM_CORE_INVENTORY, NUTRAM_DAEMON_RELOAD,
    NUTRAM_LOAD_DRIVER, NUTRAM_LOAD_SERVER, NUTRAM_LOAD_SLICE,
    NUTRAM_DRAIN_CONTROLLER, NUTRAM_READ_SAFE_QUEUE
};
enum nutram_exec_status {
    NUTRAM_EXEC_OK, NUTRAM_EXEC_TIMEOUT, NUTRAM_EXEC_LIMIT,
    NUTRAM_EXEC_SIGNAL, NUTRAM_EXEC_SETUP
};
#define NUTRAM_CAPTURE_MAX 32768
struct nutram_exec_result {
    int exit_code; /* valid only on EXEC_OK; nonzero is NOT operation success */
    size_t out_size, err_size;
    char out[NUTRAM_CAPTURE_MAX+1], err[NUTRAM_CAPTURE_MAX+1];
};
/* Captures bytes (may contain NUL); parsers must use sizes, not assume text.
 * Deadline/limit failure kills the client's process group, NOT systemd's job.
 * Does not attest unit/process/USB quiescence, protocol readiness or safe mode.
 */
int nutram_exec(enum nutram_operation op, struct nutram_exec_result *result);
/* Internal readiness budget: only QUERY_LOCAL/QUERY_ALIAS. Absolute monotonic
 * milliseconds may shorten, never extend, the fixed 3s query deadline.
 * No installed command accepts this value from a package caller. */
int nutram_query_until(enum nutram_operation op, long long deadline_ms,
                       struct nutram_exec_result *result);
#endif
