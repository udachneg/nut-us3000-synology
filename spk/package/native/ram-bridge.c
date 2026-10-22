/* LOCAL native bridge library. No main/setuid installation or product changes.
 * Runtime effects remain a compiled callback boundary until DSM binding passes.
 */
#include "ram-bridge.h"
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/vfs.h>
#include <fcntl.h>
#include <unistd.h>
#include <grp.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <limits.h>
#include <stdio.h>
#include "ram-payload.h"

#define NUTRAM_TMPFS_MAGIC 0x01021994
#ifndef NUTRAM_LOCK_TIMEOUT_MS
#define NUTRAM_LOCK_TIMEOUT_MS 120000
#endif

enum command { CMD_START, CMD_RETRY, CMD_STOP, CMD_HOOK_STOP };
static long long milliseconds(void);
static int (*diagnostic_binding)(enum nutram_phase);
static const char *diagnostic_stage;
static long long diagnostic_begun;
static void bridge_diagnostic(const char *event,int rc) {
    int saved=errno;
    long long now=milliseconds();
    (void)fprintf(stderr,"NUT_START_DIAG layer=bridge stage=%s event=%s rc=%d elapsed_ms=%lld\n",
        diagnostic_stage,event,rc,now>=0 && diagnostic_begun>=0?now-diagnostic_begun:-1);
    errno=saved;
}
/* Private synchronous callback only; no caller-selected code or new operation. */
static int diagnostic_phase(enum nutram_phase phase) {
    static const char *names[]={"prepare","ensure","audit","core","health","start",
        "controller_stop","runtime_stop","quiescent","release","cleanup","safe_entry","usb_present"};
    diagnostic_stage=(unsigned)phase<sizeof(names)/sizeof(names[0])?names[phase]:"unknown_phase";
    bridge_diagnostic("begin",0);
    int rc=diagnostic_binding(phase);
    bridge_diagnostic("result",rc);
    return rc;
}
static int exact_file(int fd, mode_t mode)
{
    struct stat st;
    return fstat(fd, &st) == 0 && S_ISREG(st.st_mode) && st.st_uid == 0 &&
        st.st_gid == 0 && st.st_nlink == 1 && (st.st_mode & 07777) == mode;
}

static int exact_dir(int fd, mode_t mode)
{
    struct stat st;
    return fstat(fd, &st) == 0 && S_ISDIR(st.st_mode) && st.st_uid == 0 &&
        st.st_gid == 0 && (st.st_mode & 07777) == mode;
}

static long long milliseconds(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return -1;
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static int lock_fd(int fd)
{
    long long start = milliseconds();
    if (start < 0) return -1;
    for (;;) {
        if (flock(fd, LOCK_EX | LOCK_NB) == 0) return 0;
        if (errno != EWOULDBLOCK && errno != EINTR) return -1;
        long long now = milliseconds();
        if (now < 0 || now - start >= NUTRAM_LOCK_TIMEOUT_MS) return -1;
        struct timespec pause = {0, 10000000};
        (void)nanosleep(&pause, NULL);
    }
}

static int open_lock(int dir, const char *name)
{
    int fd = openat(dir, name, O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK, 0600);
    if (fd < 0) return -1;
    if (!exact_file(fd, 0600)) { close(fd); return -1; }
    return fd;
}

static int matches(int dir, const struct nutram_blob *blob)
{
    unsigned char buf[4096]; size_t offset = 0; struct stat st;
    int fd = openat(dir, blob->name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) return 0;
    if (!exact_file(fd, 0600) || fstat(fd, &st) != 0 ||
        st.st_size != (off_t)blob->length) { close(fd); return 0; }
    while (offset < blob->length) {
        size_t count = blob->length - offset;
        if (count > sizeof(buf)) count = sizeof(buf);
        ssize_t n = read(fd, buf, count);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0 || memcmp(buf, blob->bytes + offset, (size_t)n) != 0) {
            close(fd); return 0;
        }
        offset += (size_t)n;
    }
    return close(fd) == 0;
}

static int materialize(int dir, const struct nutram_blob *blob)
{
    size_t offset = 0;
    int fd = openat(dir, blob->name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) return -1;
    while (offset < blob->length) {
        ssize_t n = write(fd, blob->bytes + offset, blob->length - offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { close(fd); return -1; }
        offset += (size_t)n;
    }
    return close(fd);
}

static int state_write(int dir, char state);

/* Version-independent coordination survives stop/uninstall until reboot.
 * Payload authentication is deliberately deferred until runtime.lock is held:
 * a waiter must never authenticate one generation and execute another. */
static int bootstrap(void)
{
    int run = -1, dir = -1, lock = -1, ok = 0, fresh = 0;
    struct statfs fs;
    run = open("/run", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (run < 0 || !exact_dir(run, 0755) || fstatfs(run, &fs) != 0 ||
        fs.f_type != NUTRAM_TMPFS_MAGIC) goto done;
    if (mkdirat(run, "nut-us3000-control", 0700) == 0) fresh = 1;
    else if (errno != EEXIST) goto done;
    dir = openat(run, "nut-us3000-control", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dir < 0 || !exact_dir(dir, 0700)) goto done;
    /* Do not even create a lock inside a pre-existing unrecognized directory. */
    if (!fresh && !matches(dir, &nutram_payload[0])) goto done;
    lock = open_lock(dir, "bootstrap.lock");
    if (lock < 0 || lock_fd(lock) != 0) goto done;
    /* Only the creator initializes. Incomplete/unknown roots fail closed. */
    if (fresh) {
        if (state_write(dir, 'T') != 0) goto done;
        if (materialize(dir, &nutram_payload[0]) != 0) goto done;
    }
    ok = 1;
done:
    if (lock >= 0) close(lock);
    if (run >= 0) close(run);
    if (!ok && dir >= 0) { close(dir); dir = -1; }
    /* Partial roots are retained fail-closed, never recursively removed. */
    return dir;
}

static int state_read(int dir, char *state)
{
    char buf[2]; ssize_t n;
    int fd = openat(dir, "state", O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) return -1;
    if (!exact_file(fd, 0600)) { close(fd); return -1; }
    do { n = read(fd, buf, sizeof(buf)); } while (n < 0 && errno == EINTR);
    close(fd);
    if (n != 1 || !strchr("TPXRDU", buf[0]) || buf[0] == '\0') return -1;
    *state = buf[0]; return 0;
}

static int state_write(int dir, char state)
{
    int fd = openat(dir, "state", O_WRONLY | O_CREAT | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK, 0600);
    if (fd < 0) return -1;
    if (!exact_file(fd, 0600) || pwrite(fd, &state, 1, 0) != 1 || ftruncate(fd, 1) != 0) {
        close(fd); return -1;
    }
    return close(fd);
}

static int payload_check(int dir)
{
    for (size_t i = 1; i < sizeof(nutram_payload)/sizeof(nutram_payload[0]); i++)
        if (!matches(dir, &nutram_payload[i])) return -1;
    return 0;
}

static int payload_create(int dir)
{
    struct stat st;
    /* A partial previous generation is not authorization to overwrite it. */
    for (size_t i = 1; i < sizeof(nutram_payload)/sizeof(nutram_payload[0]); i++) {
        if (fstatat(dir, nutram_payload[i].name, &st, AT_SYMLINK_NOFOLLOW) == 0 ||
            errno != ENOENT) return -1;
    }
    for (size_t i = 1; i < sizeof(nutram_payload)/sizeof(nutram_payload[0]); i++)
        if (materialize(dir, &nutram_payload[i]) != 0) return -1;
    return state_write(dir, 'X');
}

static int payload_retire(int dir)
{
    if (payload_check(dir) != 0) return -1;
    for (size_t i = 1; i < sizeof(nutram_payload)/sizeof(nutram_payload[0]); i++)
        if (unlinkat(dir, nutram_payload[i].name, 0) != 0) return -1;
    /* Commit retired only after all code was removed. No lock inode is removed. */
    return state_write(dir, 'T');
}

static int start_result(int dir, int rc)
{
    if (rc != 0 && rc != 75) return 1;
    if (state_write(dir, rc == 0 ? 'R' : 'U') != 0) return 1;
    return rc;
}

static int recover(int dir, char previous, int (*phase)(enum nutram_phase))
{
    int core, health;
    if (phase(NUTRAM_ENSURE) != 0 || phase(NUTRAM_AUDIT) != 0) return 1;
    core = phase(NUTRAM_CORE);
    if (core == 0) {
        health = phase(NUTRAM_HEALTH);
        if (health == 0) return start_result(dir, 0);
        if (health != 1) return 1;
        if (previous != 'D') return state_write(dir, 'D') == 0 ? 0 : 1;
    } else if (core != 75 && core != 76) return 1;
    if (core == 0 || core == 76) {
        if (phase(NUTRAM_RUNTIME_STOP) != 0 || phase(NUTRAM_QUIESCENT) != 0 ||
            phase(NUTRAM_RELEASE) != 0 || phase(NUTRAM_ENSURE) != 0 ||
            phase(NUTRAM_AUDIT) != 0) return 1;
    }
    return start_result(dir, phase(NUTRAM_START));
}

int nutram_bridge_dispatch(int argc, char **argv, int (*phase)(enum nutram_phase))
{
    enum command command; char state;
    int dir = -1, hook = -1, runtime = -1, rc = 1;
    if (argc != 2 || !argv || !argv[1]) return 64;
    if (strcmp(argv[1], "ram-start") == 0) command = CMD_START;
    else if (strcmp(argv[1], "ram-retry") == 0) command = CMD_RETRY;
    else if (strcmp(argv[1], "ram-stop") == 0) command = CMD_STOP;
    else if (strcmp(argv[1], "ram-hook-stop") == 0) command = CMD_HOOK_STOP;
    else return 64;
    if(command==CMD_START) {
        int saved=errno;
        diagnostic_begun=milliseconds();diagnostic_stage="binding";errno=saved;
        diagnostic_binding=phase;
    }
    if (!phase) goto done;
    if(command==CMD_START) {phase=diagnostic_phase;diagnostic_stage="credentials";}
    if (geteuid() != 0 || setgroups(0, NULL) != 0 || setgid(0) != 0 ||
        setuid(0) != 0 || getuid() != 0 || getgid() != 0) {rc=77;goto done;}
    if(command==CMD_START)diagnostic_stage="environment";
    if (clearenv() != 0 || setenv("PATH", "/usr/sbin:/usr/bin:/sbin:/bin", 1) != 0 ||
        setenv("LC_ALL", "C", 1) != 0 || chdir("/") != 0) goto done;
    umask(077);
    if(command==CMD_START)diagnostic_stage="bootstrap";
    dir = bootstrap();
    if (dir < 0) goto done;
    if (command != CMD_RETRY) {
        if(command==CMD_START)diagnostic_stage="hook_lock";
        hook = open_lock(dir, "hooks.lock");
        if (hook < 0 || lock_fd(hook) != 0) goto done;
    }
    if(command==CMD_START)diagnostic_stage="runtime_lock";
    runtime = open_lock(dir, "runtime.lock");
    if (runtime < 0 || lock_fd(runtime) != 0) goto done;
    if(command==CMD_START)diagnostic_stage="state_read";
    if (state_read(dir, &state) != 0) goto done;
    if (state == 'T') {
        if (command != CMD_START) { rc = 0; goto done; }
        diagnostic_stage="payload_create";
        if (payload_create(dir) != 0) goto done;
        state = 'X';
    }
    /* A disabled retry must not resurrect retired code or act during stop drain. */
    if (command == CMD_RETRY && (state == 'X' || state == 'P')) { rc = 0; goto done; }
    if(command==CMD_START)diagnostic_stage="payload_check";
    if (payload_check(dir) != 0) goto done;
    if (command == CMD_RETRY) {
        rc = state == 'X' ? 0 : recover(dir, state, phase);
    } else if (command == CMD_START) {
        if (state != 'X') { rc = recover(dir, state, phase); goto done; }
        if (phase(NUTRAM_PREPARE) != 0 || phase(NUTRAM_ENSURE) != 0 ||
            phase(NUTRAM_AUDIT) != 0) goto done;
        rc = start_result(dir, phase(NUTRAM_START));
    } else {
        if (state_write(dir, 'X') != 0 || flock(runtime, LOCK_UN) != 0) goto done;
        /* Never wait for controller while holding the lock its step needs.
         * hooks.lock remains held: explicit start cannot reopen the gate. */
        if (phase(NUTRAM_CONTROLLER_STOP) != 0 || lock_fd(runtime) != 0) goto done;
        if (command == CMD_HOOK_STOP && phase(NUTRAM_SAFE_ENTRY) == 0) {
            rc = state_write(dir, 'P') == 0 ? 0 : 1; goto done;
        }
        if (phase(NUTRAM_RUNTIME_STOP) != 0 || phase(NUTRAM_QUIESCENT) != 0 ||
            phase(NUTRAM_RELEASE) != 0 || phase(NUTRAM_CLEANUP) != 0) goto done;
        if (payload_retire(dir) != 0) goto done;
        rc = 0;
    }
done:
    if ((rc == 0 || rc == 75) && dir >= 0 && state_read(dir, &state) == 0) {
        const char *label=state=='R'?"HEALTHY":state=='D'?"DEGRADED":
            state=='U'?"UNAVAILABLE":state=='P'?"PRESERVED":"DISABLED";
        if (printf("RAM_STATE=%s\n",label)<0) rc=1;
    }
    if (runtime >= 0) close(runtime);
    if (hook >= 0) close(hook);
    if (dir >= 0) close(dir);
    if(command==CMD_START)bridge_diagnostic("complete",rc);
    return rc;
}
