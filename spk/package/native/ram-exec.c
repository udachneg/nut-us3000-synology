/* LOCAL PROTOTYPE: fixed native executor, partially bound to RAM bridge. */
#include "ram-exec.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <poll.h>
#include <pwd.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

struct shared_result { int status; struct nutram_exec_result result; };
static volatile sig_atomic_t cancelled;
static void cancel(int sig) { (void)sig; cancelled=1; }
static int is_query(enum nutram_operation op) {
    return op==NUTRAM_QUERY_LOCAL || op==NUTRAM_QUERY_ALIAS;
}
static long long now_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) return -1;
    return (long long)t.tv_sec*1000+t.tv_nsec/1000000;
}

/* The worker must not inherit flock descriptors, caller pipes or secret FDs.
 * Guardian deliberately retains them until its direct child has been reaped.
 */
static int close_extra_fds(void) {
    DIR *d=opendir("/proc/self/fd"); struct dirent *e;
    if (!d) return -1;
    int keep=dirfd(d);
    while ((e=readdir(d))) {
        char *end; long fd=strtol(e->d_name,&end,10);
        if (*end || end==e->d_name || fd<3 || fd==keep) continue;
        if (close((int)fd) && errno!=EBADF) { closedir(d); return -1; }
    }
    return closedir(d);
}

static void worker(enum nutram_operation op, uid_t uid, gid_t gid,
                   int out, int err) {
    struct sigaction sa; memset(&sa,0,sizeof(sa)); sa.sa_handler=SIG_DFL;
    sigemptyset(&sa.sa_mask);
    sigset_t empty; sigemptyset(&empty);
    if (sigaction(SIGTERM,&sa,NULL) || sigaction(SIGINT,&sa,NULL) ||
        sigaction(SIGHUP,&sa,NULL) || sigaction(SIGPIPE,&sa,NULL) ||
        sigprocmask(SIG_SETMASK,&empty,NULL) || setpgid(0,0)) _exit(126);
    int input=open("/dev/null",O_RDONLY|O_CLOEXEC);
    if (input<0 || dup2(input,0)<0 || dup2(out,1)<0 || dup2(err,2)<0 ||
        close_extra_fds() || chdir("/")) _exit(126);
    umask(077);
    if (setgroups(0,NULL) || setresgid(gid,gid,gid) || setresuid(uid,uid,uid) ||
        getuid()!=uid || geteuid()!=uid || getgid()!=gid || getegid()!=gid ||
        prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)) _exit(126);
    /* envp applies to the dynamic loader only AFTER credentials are dropped. */
    char *sysenv[]={"PATH=/usr/bin:/bin","LC_ALL=C","SYSTEMD_COLORS=0",NULL};
    char *nutenv[]={"PATH=/usr/bin:/bin","LC_ALL=C",
        "LD_LIBRARY_PATH=/run/nut-us3000-ram/lib",NULL};
    char *unit=(op==NUTRAM_START_DRIVER || op==NUTRAM_STOP_DRIVER || op==NUTRAM_SHOW_DRIVER)
        ? "nut-us3000-ram-driver.service" : "nut-us3000-ram-server.service";
    char *action=op<=NUTRAM_START_SERVER?"start":"stop";
    char *simple[]={"/usr/bin/systemctl","--system","--no-pager","--no-ask-password",action,unit,NULL};
    char *show[]={"/usr/bin/systemctl","--system","--no-pager","--no-ask-password","show",
        "-p","Id","-p","LoadState","-p","ActiveState","-p","SubState",
        "-p","MainPID","-p","ControlPID","-p","ControlGroup",unit,NULL};
    char *query[]={"/run/nut-us3000-ram/bin/upsc",
        op==NUTRAM_QUERY_LOCAL?"ups@127.0.0.1:3493":"ups@10.255.255.1:3493",NULL};
    /* Bridge has authenticated these embedded bytes before entering a phase.
     * Never source the package-writable copy or accept a caller script path. */
    char *kernel[]={"/bin/sh","-c",
        ". /run/nut-us3000-control/ram-lifecycle.sh; nutram_kernel_quiescent",NULL};
    char *reload[]={"/usr/bin/systemctl","--system","--no-pager","--no-ask-password","daemon-reload",NULL};
    char *loaded[]={"/usr/bin/systemctl","--system","--no-pager","--no-ask-password","show",
        "-p","Id","-p","LoadState","-p","FragmentPath","-p","DropInPaths",
        op==NUTRAM_LOAD_DRIVER?"nut-us3000-ram-driver.service":
        op==NUTRAM_LOAD_SERVER?"nut-us3000-ram-server.service":"nutus3000_ram.slice",NULL};
    char *drain[]={"/bin/sh","-c",
        "SYNOPKG_PKGDEST=/var/packages/nut-us3000/target; "
        "SYNOPKG_PKGVAR=/var/packages/nut-us3000/var; export SYNOPKG_PKGDEST SYNOPKG_PKGVAR; "
        "lib=$SYNOPKG_PKGDEST/share/nut-us3000/lib.sh; "
        "[ -f \"$lib\" ] && [ ! -L \"$lib\" ] || exit 1; "
        ". \"$lib\" || exit 1; nutus3000_controller_stop",NULL};
    char *queue[]={"/bin/sh","/run/nut-us3000-control/queue-reader.sh",NULL};
    if (op==NUTRAM_CORE_INVENTORY)
        kernel[2]=". /run/nut-us3000-control/ram-lifecycle.sh; nutram_core_inventory";
    if (op==NUTRAM_DAEMON_RELOAD) execve(reload[0],reload,sysenv);
    else if (op>=NUTRAM_LOAD_DRIVER && op<=NUTRAM_LOAD_SLICE) execve(loaded[0],loaded,sysenv);
    else if (op==NUTRAM_DRAIN_CONTROLLER) execve(drain[0],drain,sysenv);
    else if (op==NUTRAM_READ_SAFE_QUEUE) execve(queue[0],queue,sysenv);
    else if (op==NUTRAM_KERNEL_QUIESCENT || op==NUTRAM_CORE_INVENTORY) execve(kernel[0],kernel,sysenv);
    else if (is_query(op)) execve(query[0],query,nutenv);
    else if (op>=NUTRAM_SHOW_DRIVER) execve(show[0],show,sysenv);
    else execve(simple[0],simple,sysenv);
    _exit(127);
}

static int drain(int fd, char *buf, size_t *size, int *eof) {
    char block[4096]; ssize_t n=read(fd,block,sizeof(block));
    if (n<0) return (errno==EINTR || errno==EAGAIN)?0:-1;
    if (!n) { *eof=1; return 0; }
    if ((size_t)n>NUTRAM_CAPTURE_MAX-*size) return 1;
    memcpy(buf+*size,block,(size_t)n); *size+=(size_t)n; buf[*size]=0;
    return 0;
}

static void supervise(enum nutram_operation op, uid_t uid, gid_t gid,
                      pid_t parent, long long until, struct shared_result *s) {
    struct sigaction sa; memset(&sa,0,sizeof(sa)); sa.sa_handler=cancel;
    sigemptyset(&sa.sa_mask); cancelled=0;
    sigset_t empty; sigemptyset(&empty);
    if (sigaction(SIGTERM,&sa,NULL) || sigaction(SIGINT,&sa,NULL) ||
        sigaction(SIGHUP,&sa,NULL) || prctl(PR_SET_PDEATHSIG,SIGTERM) ||
        sigprocmask(SIG_SETMASK,&empty,NULL) || getppid()!=parent || cancelled) _exit(1);
    sa.sa_handler=SIG_DFL;
    if (sigaction(SIGCHLD,&sa,NULL)) _exit(1);
    int out[2],err[2];
    if (pipe2(out,O_CLOEXEC)) _exit(1);
    if (pipe2(err,O_CLOEXEC)) { close(out[0]); close(out[1]); _exit(1); }
    long long start=now_ms();
    if (start<0 || fcntl(out[0],F_SETFL,O_NONBLOCK) || fcntl(err[0],F_SETFL,O_NONBLOCK)) _exit(1);
    pid_t child=fork();
    if (child<0) _exit(1);
    if (!child) worker(op,uid,gid,out[1],err[1]);
    close(out[1]); close(err[1]);
    /* Both sides set the group; no signal can hit an unrelated process group. */
    if (setpgid(child,child) && errno!=EACCES && errno!=ESRCH) cancelled=1;
    int done=0,status=0,eof[2]={0,0},why=NUTRAM_EXEC_SETUP;
    siginfo_t info; memset(&info,0,sizeof(info));
    long long deadline=start+((op>=NUTRAM_SHOW_DRIVER && op<=NUTRAM_QUERY_ALIAS)?3000:15000);
    if (op==NUTRAM_DRAIN_CONTROLLER) deadline=start+45000;
    if (until && until<deadline) deadline=until;
    for (;;) {
        long long now=now_ms();
        if (cancelled || now<0) break;
        if (now>=deadline) { why=NUTRAM_EXEC_TIMEOUT; break; }
        struct pollfd fds[2]={{eof[0]?-1:out[0],POLLIN,0},{eof[1]?-1:err[0],POLLIN,0}};
        int rc=poll(fds,2,20);
        if (rc<0 && errno!=EINTR) break;
        for (int i=0;i<2;i++) if (!eof[i] && fds[i].revents) {
            int r=drain(i?err[0]:out[0],i?s->result.err:s->result.out,
                        i?&s->result.err_size:&s->result.out_size,&eof[i]);
            if (r) { why=r>0?NUTRAM_EXEC_LIMIT:NUTRAM_EXEC_SETUP; goto finish; }
        }
        if (!done) {
            /* Keep leader PID reserved until the final group signal: reaping
             * here could let its number become an unrelated process/group. */
            int w=waitid(P_PID,(id_t)child,&info,WEXITED|WNOHANG|WNOWAIT);
            if (!w && info.si_pid==child) done=1;
            else if (w<0 && errno!=EINTR) break;
        }
        if (done && eof[0] && eof[1]) {
            why=info.si_code==CLD_EXITED?NUTRAM_EXEC_OK:NUTRAM_EXEC_SIGNAL;
            if (why==NUTRAM_EXEC_OK) s->result.exit_code=info.si_status;
            break;
        }
    }
finish:
    /* Kill remaining same-group descendants even if the direct client exited.
     * Not a sandbox for hostile executables that escape their process group.
     * SIGKILL cannot promise immediate completion of uninterruptible kernel I/O.
     */
    kill(-child,SIGKILL);
    if (!done) kill(child,SIGKILL);
    while (waitpid(child,&status,0)<0 && errno==EINTR) {}
    close(out[0]); close(err[0]); s->status=why;
    _exit(0);
}

static int execute(enum nutram_operation op, long long until, struct nutram_exec_result *result) {
    if (!result) return NUTRAM_EXEC_SETUP;
    memset(result,0,sizeof(*result)); result->exit_code=-1;
    if (op<NUTRAM_START_DRIVER || op>NUTRAM_READ_SAFE_QUEUE || getuid()!=0 || geteuid()!=0)
        return NUTRAM_EXEC_SETUP;
    if (until) {
        long long now=now_ms();
        if (!is_query(op) || until<0 || now<0) return NUTRAM_EXEC_SETUP;
        if (now>=until) return NUTRAM_EXEC_TIMEOUT;
    }
    uid_t uid=0; gid_t gid=0;
    if (is_query(op) || op==NUTRAM_DRAIN_CONTROLLER) {
        struct passwd *p=getpwnam("nutus3000");
        if (!p || !p->pw_uid || !p->pw_gid) return NUTRAM_EXEC_SETUP;
        uid=p->pw_uid; gid=p->pw_gid;
    }
    struct shared_result *s=mmap(NULL,sizeof(*s),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
    if (s==MAP_FAILED) return NUTRAM_EXEC_SETUP;
    memset(s,0,sizeof(*s)); s->status=NUTRAM_EXEC_SETUP; s->result.exit_code=-1;
    sigset_t block,old; sigemptyset(&block);
    sigaddset(&block,SIGTERM); sigaddset(&block,SIGINT); sigaddset(&block,SIGHUP);
    if (sigprocmask(SIG_BLOCK,&block,&old)) { munmap(s,sizeof(*s)); return NUTRAM_EXEC_SETUP; }
    pid_t parent=getpid(),child=fork();
    if (!child) supervise(op,uid,gid,parent,until,s);
    sigprocmask(SIG_SETMASK,&old,NULL);
    int status=0; pid_t w=-1;
    if (child>0) do { w=waitpid(child,&status,0); } while (w<0 && errno==EINTR);
    int rc=NUTRAM_EXEC_SETUP;
    if (w==child && child>0 && WIFEXITED(status) && WEXITSTATUS(status)==0) {
        *result=s->result; rc=s->status;
    }
    munmap(s,sizeof(*s)); return rc;
}

int nutram_exec(enum nutram_operation op, struct nutram_exec_result *result) {
    return execute(op,0,result);
}

int nutram_query_until(enum nutram_operation op, long long deadline_ms,
                       struct nutram_exec_result *result) {
    if (deadline_ms<=0 || !is_query(op)) {
        if (result) { memset(result,0,sizeof(*result)); result->exit_code=-1; }
        return NUTRAM_EXEC_SETUP;
    }
    return execute(op,deadline_ms,result);
}
