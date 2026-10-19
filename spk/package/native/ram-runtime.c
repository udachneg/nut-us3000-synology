/* LOCAL partial native binding. No installed API, units or package changes. */
#include "ram-runtime.h"
#include "ram-exec.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* Require complete bounded text. Executor supplies byte count, not strlen;
 * reject NUL/control bytes and a partial trailing line before any parsing. */
static int text_complete(const char *s, size_t n) {
    if (!n || n>NUTRAM_CAPTURE_MAX || s[n-1]!='\n') return 0;
    for (size_t i=0;i<n;i++) {
        unsigned char c=(unsigned char)s[i];
        if (c!='\n' && c!='\t' && (c<32 || c>126)) return 0;
    }
    return 1;
}

static int power_status(char *s) {
    int online=0,battery=0,unavailable=0; char *save=NULL;
    for (char *token=strtok_r(s," \t",&save);token;token=strtok_r(NULL," \t",&save)) {
        if (!strcmp(token,"OL")) online=1;
        if (!strcmp(token,"OB")) battery=1;
        if (!strcmp(token,"STALE") || !strcmp(token,"NOCOMM")) unavailable=1;
    }
    if (online && battery) return 2;
    return unavailable || (!online && !battery) ? 1 : 0;
}

static int nut_data(struct nutram_exec_result *r) {
    static const char *keys[]={"driver.name","device.mfr","device.model",
        "ups.vendorid","ups.productid","ups.status"};
    static const char *expected[]={"nutus3000-hid","UGREEN","US3000","2b89","ffff"};
    char *values[6]={0},*line=r->out;
    if (!text_complete(r->out,r->out_size)) return 2;
    while (*line) {
        char *end=strchr(line,'\n'); *end=0;
        char *sep=strstr(line,": ");
        if (!sep || sep==line) return 2;
        *sep=0;
        for (unsigned i=0;i<6;i++) if (!strcmp(line,keys[i])) {
            if (values[i]) return 2;
            values[i]=sep+2;
        }
        line=end+1;
    }
    for (unsigned i=0;i<6;i++) if (!values[i]) return 2;
    for (unsigned i=0;i<5;i++) if (strcmp(values[i],expected[i])) return 2;
    return power_status(values[5]);
}

static int known_unavailable(const struct nutram_exec_result *r) {
    const char *s=r->err;
    const char *prefix="Init SSL without certificate database\n";
    if (r->out_size || !text_complete(s,r->err_size)) return 0;
    if (!strncmp(s,prefix,strlen(prefix))) s+=strlen(prefix);
    return !strcmp(s,"Error: Data stale\n") || !strcmp(s,"Error: Driver not connected\n");
}

static int health_until(long long deadline) {
    int unavailable=0,starting=0;
    for (int op=NUTRAM_QUERY_LOCAL;op<=NUTRAM_QUERY_ALIAS;op++) {
        struct nutram_exec_result r;
        int transport=deadline?nutram_query_until(op,deadline,&r):nutram_exec(op,&r),rc;
        /* Unknown transport/loader/protocol errors must not trigger destructive
         * recovery as though they proved a disconnected physical device. */
        if (transport!=NUTRAM_EXEC_OK) return 2;
        if (r.exit_code==0) rc=nut_data(&r);
        else if (r.exit_code==1 && known_unavailable(&r)) rc=1;
        else if (deadline && r.exit_code==1 && !r.out_size &&
                 r.err_size==sizeof("Error: Connection failure: Connection refused\n")-1 &&
                 !memcmp(r.err,"Error: Connection failure: Connection refused\n",r.err_size)) rc=3;
        else return 2;
        if (rc==2) return 2;
        if (rc==1) unavailable=1;
        if (rc==3) starting=1;
    }
    return starting?3:unavailable;
}

static int health(void) { return health_until(0); }

struct unit_state { int kind; unsigned long pid; }; /* 0 dead, 1 running, 2 failed/zero, 3 missing */
static int unit_read(enum nutram_operation op, struct unit_state *state) {
    const char *unit=op==NUTRAM_SHOW_SERVER?"nut-us3000-ram-server.service":"nut-us3000-ram-driver.service";
    const char *group=op==NUTRAM_SHOW_SERVER?
        "/nutus3000_ram.slice/nut-us3000-ram-server.service":
        "/nutus3000_ram.slice/nut-us3000-ram-driver.service";
    static const char *keys[]={"Id","LoadState","ActiveState","SubState","MainPID","ControlPID","ControlGroup"};
    char *values[7]={0}; struct nutram_exec_result r;
    if (nutram_exec(op,&r)!=NUTRAM_EXEC_OK || r.exit_code!=0 ||
        r.err_size || !text_complete(r.out,r.out_size)) return 1;
    char *line=r.out;
    while (*line) {
        char *end=strchr(line,'\n'); *end=0;
        char *sep=strchr(line,'=');
        if (!sep || strchr(sep+1,'=')) return 1;
        *sep=0; unsigned i;
        for (i=0;i<7;i++) if (!strcmp(line,keys[i])) break;
        if (i==7 || values[i]) return 1;
        values[i]=sep+1; line=end+1;
    }
    for (unsigned i=0;i<7;i++) if (!values[i]) return 1;
    if (strcmp(values[0],unit) || strcmp(values[5],"0") ||
        (*values[6] && strcmp(values[6],group))) return 1;
    if(!strcmp(values[1],"not-found")) {
        if(strcmp(values[2],"inactive") || strcmp(values[3],"dead") ||
           strcmp(values[4],"0") || *values[6])return 1;
        state->kind=3; state->pid=0;
        return 0;
    }
    if(strcmp(values[1],"loaded"))return 1;
    if (!strcmp(values[4],"0")) {
        state->pid=0;
        if (!strcmp(values[2],"inactive") && !strcmp(values[3],"dead")) state->kind=0;
        else if (!strcmp(values[2],"failed") && !strcmp(values[3],"failed")) state->kind=2;
        else return 1;
        return 0;
    }
    if (strcmp(values[2],"active") || strcmp(values[3],"running") || strcmp(values[6],group) ||
        *values[4]<'1' || *values[4]>'9' || strspn(values[4],"0123456789")!=strlen(values[4])) return 1;
    char *end; errno=0; state->pid=strtoul(values[4],&end,10);
    if (errno || *end || state->pid>INT_MAX) return 1;
    state->kind=1;
    return 0;
}

static int unit_dead(enum nutram_operation op) {
    struct unit_state state;
    return unit_read(op,&state) || (state.kind!=0 && state.kind!=3);
}

static int runtime_stop(void) {
    for (int op=NUTRAM_STOP_SERVER;op<=NUTRAM_STOP_DRIVER;op++) {
        struct nutram_exec_result r;
        struct unit_state before;
        enum nutram_operation show=op==NUTRAM_STOP_SERVER?NUTRAM_SHOW_SERVER:NUTRAM_SHOW_DRIVER;
        /* Refuse an ambiguous/foreign active unit before sending any stop.
         * A complete missing-unit snapshot means there is no job to submit. */
        if(unit_read(show,&before))return 1;
        if(before.kind==3)continue;
        if (nutram_exec(op,&r)!=NUTRAM_EXEC_OK) return 1;
        if(r.exit_code!=0) {
            /* A never-installed unit has no stop job. Do not infer absence
             * from rc/stderr: require its full exact missing-unit snapshot.
             * Caller still proves kernel quiescence before release/cleanup. */
            struct unit_state state;
            if(unit_read(show,&state) ||
               state.kind!=3)return 1;
        }
    }
    return 0;
}

static int quiescent(void) {
    struct nutram_exec_result r;
    if (unit_dead(NUTRAM_SHOW_SERVER) || unit_dead(NUTRAM_SHOW_DRIVER)) return 1;
    return nutram_exec(NUTRAM_KERNEL_QUIESCENT,&r)!=NUTRAM_EXEC_OK ||
        r.exit_code!=0 || r.out_size!=0 || r.err_size!=0;
}

static int core(void) {
    struct unit_state server,driver,after_server,after_driver;
    struct nutram_exec_result r;
    if (unit_read(NUTRAM_SHOW_SERVER,&server) || unit_read(NUTRAM_SHOW_DRIVER,&driver)) return 2;
    if(server.kind==3 || driver.kind==3)return 2; /* absence never authorizes START */
    if (server.pid && !driver.pid) return 2; /* Never take over an orphan server. */
    if (!driver.pid) {
        /* Loaded dead OR failed units with zero main/control PIDs are not by
         * themselves absence. Kernel quiescence must also be proven. */
        if (nutram_exec(NUTRAM_KERNEL_QUIESCENT,&r)!=NUTRAM_EXEC_OK || r.exit_code ||
            r.out_size || r.err_size) return 2;
    } else {
        char expected[96];
        int n=snprintf(expected,sizeof(expected),"server=%lu\ndriver=%lu\n",server.pid,driver.pid);
        if (n<0 || (size_t)n>=sizeof(expected) ||
            nutram_exec(NUTRAM_CORE_INVENTORY,&r)!=NUTRAM_EXEC_OK || r.exit_code || r.err_size ||
            r.out_size!=(size_t)n || memcmp(r.out,expected,(size_t)n)) return 2;
    }
    /* Detect a unit transition while /proc was being inspected. This is a
     * conservative observation, not an atomic promise of future process life. */
    if (unit_read(NUTRAM_SHOW_SERVER,&after_server) || unit_read(NUTRAM_SHOW_DRIVER,&after_driver) ||
        server.kind!=after_server.kind || server.pid!=after_server.pid ||
        driver.kind!=after_driver.kind || driver.pid!=after_driver.pid) return 2;
    return server.pid?0:driver.pid?76:75;
}

static long long monotonic_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) return -1;
    return (long long)t.tv_sec*1000+t.tv_nsec/1000000;
}

static int wait_ready(void) {
    long long now=monotonic_ms();
    if (now<0) return 1;
    const long long deadline=now+20000;
    int observed_unavailable=0;
    for (;;) {
        now=monotonic_ms();
        if (now<0) return 1;
        if (now>=deadline) return observed_unavailable?75:1;
        int rc=health_until(deadline);
        if (rc==0) return 0;
        if (rc!=1 && rc!=3) return 1; /* identity/permission/unknown errors are fatal */
        if(rc==1)observed_unavailable=1;
        now=monotonic_ms();
        if (now<0) return 1;
        if (now>=deadline) return observed_unavailable?75:1;
        long long pause=deadline-now;
        if (pause>1000) pause=1000;
        struct timespec delay={0,pause*1000000};
        if (delay.tv_nsec==1000000000) { delay.tv_sec=1; delay.tv_nsec=0; }
        /* Interrupted wait is not permission to publish readiness. */
        if (nanosleep(&delay,NULL)) return 1;
    }
}

static int runtime_start(int (*remaining)(enum nutram_phase)) {
    /* PREPARE must authenticate/load exact units; bridge has already audited
     * host integration. Never take over an already running/unknown runtime. */
    if (core()!=75) return 1;
    if(!remaining)return 1;
    int usb=remaining(NUTRAM_USB_PRESENT);
    if(usb!=0)return usb==75?75:1;
    int rc=1;
    for (int op=NUTRAM_START_DRIVER;op<=NUTRAM_START_SERVER;op++) {
        struct nutram_exec_result r;
        if (nutram_exec(op,&r)!=NUTRAM_EXEC_OK || r.exit_code) goto unwind;
    }
    /* Type=simple start completion precedes exec. Only this just-started pair
     * gets a short convergence window; the strict preflight above is unchanged.
     * Every observation remains bounded and nothing becomes ready on timeout. */
    long long begun=monotonic_ms();
    if(begun<0)goto unwind;
    while(core()!=0) {
        long long now=monotonic_ms();
        if(now<0 || now-begun>=3000)goto unwind;
        struct timespec pause={0,50000000};
        if(nanosleep(&pause,NULL))goto unwind;
    }
    rc=wait_ready();
    if (!rc) return 0;
unwind:
    /* Even a failed/timed-out client may have submitted a systemd job. Stop
     * both fixed units and prove quiescence before returning a retryable75.
     * Keep RAM/host integration; release/erase is not this phase's authority. */
    if (runtime_stop() || quiescent()) return 1;
    return rc;
}

int nutram_runtime_phase(enum nutram_phase phase, int (*remaining)(enum nutram_phase)) {
    if (phase==NUTRAM_HEALTH) return health();
    if (phase==NUTRAM_RUNTIME_STOP) return runtime_stop();
    if (phase==NUTRAM_QUIESCENT) return quiescent();
    if (phase==NUTRAM_CORE) return core();
    if (phase==NUTRAM_START) return runtime_start(remaining);
    if (phase<NUTRAM_PREPARE || phase>NUTRAM_USB_PRESENT || !remaining) return 2;
    return remaining(phase);
}
