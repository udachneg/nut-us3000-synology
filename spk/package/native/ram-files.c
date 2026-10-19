/* Private hostctl module: call with bridge lifecycle locks held. No CLI.
 * Package data is opened only AFTER dropping all credentials in a child.
 * No package code is executed by the privileged copier. */
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <unistd.h>
#include <grp.h>
#include <pwd.h>
#include <signal.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>
#include <dirent.h>

#define ROOT "/run/nut-us3000-ram"
#define TARGET "/var/packages/nut-us3000/target"
#define CONFIG "/var/packages/nut-us3000/etc"
#define CONTROL "/run/nut-us3000-control"
#define LIMIT 4194304
static const char *dirs[]={"bin","lib","conf","manager","units","state"};
static const struct file { const char *src,*dst; mode_t mode; int package; } files[]={
    {TARGET "/sbin/upsd","bin/nutus3000-srv",0750,1},
    {TARGET "/libexec/nut/usbhid-ups","bin/nutus3000-hid",0750,1},
    {TARGET "/bin/upsc","bin/upsc",0750,1},
    {TARGET "/lib/libusb-1.0.so.0.5.0","lib/libusb-1.0.so.0.5.0",0640,1},
    {TARGET "/lib/libupsclient.so.7.1.0","lib/libupsclient.so.7.1.0",0640,1},
    {CONFIG "/ups.conf","conf/ups.conf",0640,1},
    {CONFIG "/upsd.conf","conf/upsd.conf",0640,1},
    {CONFIG "/upsd.users","conf/upsd.users",0640,1},
    {CONTROL "/hook-policy.sh","manager/hook-policy.sh",0640,0},
    {CONTROL "/queue-reader.sh","manager/queue-reader.sh",0640,0},
    {CONTROL "/queue-parser.sh","manager/queue-parser.sh",0640,0},
    {CONTROL "/ram-manager.sh","manager/ram-manager.sh",0640,0},
    {CONTROL "/ram-lifecycle.sh","manager/ram-lifecycle.sh",0640,0},
    {CONTROL "/nutus3000_ram.slice.in","units/nutus3000_ram.slice",0640,0},
    {CONTROL "/nut-us3000-ram-driver.service.in","units/nut-us3000-ram-driver.service",0640,0},
    {CONTROL "/nut-us3000-ram-server.service.in","units/nut-us3000-ram-server.service",0640,0}
};
static int write_all(int fd,const void *data,size_t n) {
    const char *p=data;
    while(n) { ssize_t w=write(fd,p,n); if(w<0 && errno==EINTR)continue;
        if(w<=0)return -1;
        p+=w; n-=(size_t)w; }
    return 0;
}
static int copy_data(const struct file *f,int dest) {
    struct stat a,b; char buf[16384]; size_t total=0; int rc=-1;
    int src=open(f->src,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC);
    if(src<0)return -1;
    if(fstat(src,&a) || !S_ISREG(a.st_mode) || a.st_size<=0 || a.st_size>LIMIT)goto done;
    if(!f->package && (a.st_uid || a.st_gid || (a.st_mode&07777)!=0600 || a.st_nlink!=1))goto done;
    for(;;) {
        ssize_t n=read(src,buf,sizeof(buf));
        if(n<0 && errno==EINTR)continue;
        if(n<0)goto done;
        if(!n)break;
        total+=(size_t)n;
        if(total>LIMIT || write_all(dest,buf,(size_t)n))goto done;
    }
    if(fstat(src,&b) || total!=(size_t)a.st_size || b.st_size!=a.st_size ||
       a.st_mtim.tv_sec!=b.st_mtim.tv_sec || a.st_mtim.tv_nsec!=b.st_mtim.tv_nsec ||
       a.st_ctim.tv_sec!=b.st_ctim.tv_sec || a.st_ctim.tv_nsec!=b.st_ctim.tv_nsec)goto done;
    rc=0;
done: close(src); return rc;
}
static int package_copy(const struct file *f,int dest,uid_t uid,gid_t gid) {
    pid_t parent=getpid(),child=fork(); int status; pid_t w;
    if(child<0)return -1;
    if(!child) {
        struct sigaction sa; memset(&sa,0,sizeof(sa)); sa.sa_handler=SIG_DFL;
        sigemptyset(&sa.sa_mask); sigset_t empty; sigemptyset(&empty);
        if(sigaction(SIGALRM,&sa,NULL) || sigprocmask(SIG_SETMASK,&empty,NULL) ||
           prctl(PR_SET_PDEATHSIG,SIGKILL) || getppid()!=parent)_exit(1);
        alarm(3);
        if(setgroups(0,NULL) || setresgid(gid,gid,gid) || setresuid(uid,uid,uid) ||
           prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0))_exit(1);
        /* setresuid can clear PDEATHSIG: re-arm and recheck after the drop. */
        if(prctl(PR_SET_PDEATHSIG,SIGKILL) || getppid()!=parent)_exit(1);
        _exit(copy_data(f,dest)==0?0:1);
    }
    do { w=waitpid(child,&status,0); }while(w<0 && errno==EINTR);
    return w==child && WIFEXITED(status) && WEXITSTATUS(status)==0?0:-1;
}
static int read_config(int dir,const char *path,char *buf,size_t cap) {
    int fd=openat(dir,path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC); struct stat st;
    if(fd<0)return -1;
    if(fstat(fd,&st) || st.st_size<=0 || (size_t)st.st_size>=cap) {close(fd);return -1;}
    ssize_t n=read(fd,buf,cap); close(fd);
    if(n!=st.st_size || memchr(buf,0,(size_t)n))return -1;
    buf[n]=0; return 0;
}
static int configuration(int dir) {
    char buf[8192],normalized[8192]; size_t n=0; int comment=0;
    if(read_config(dir,"conf/ups.conf",buf,sizeof(buf)))return -1;
    for(const unsigned char *p=(unsigned char*)buf;*p;p++) {
        if(*p=='#')comment=1;
        if(*p=='\n')comment=0;
        if(!comment && !isspace(*p))normalized[n++]=(char)*p;
    }
    normalized[n]=0;
    if(strcmp(normalized,"[ups]driver=usbhid-upsport=autovendorid=2b89productid=ffffserial=DC600"
                        "subdriver=\"ArduinoHID0.22\"usb_hid_rep_index=0usb_hid_ep_in=1usb_hid_ep_out=1pollonly"))return -1;
    if(read_config(dir,"conf/upsd.conf",buf,sizeof(buf)))return -1;
    unsigned seen=0; char *save=NULL;
    for(char *line=strtok_r(buf,"\n",&save);line;line=strtok_r(NULL,"\n",&save)) {
        char *hash=strchr(line,'#'); if(hash)*hash=0;
        char a[32],b[64],c[32],extra[2];
        int count=sscanf(line,"%31s %63s %31s %1s",a,b,c,extra);
        if(count==EOF)continue;
        if(count!=3 || strcmp(a,"LISTEN") || strcmp(c,"3493"))return -1;
        unsigned bit=!strcmp(b,"127.0.0.1")?1:!strcmp(b,"10.255.255.1")?2:0;
        if(!bit || (seen&bit))return -1;
        seen|=bit;
    }
    if(seen!=3)return -1;
    /* Canonical fixed selector; credentials are copied unchanged as data. */
    const char config[]="[ups]\n    driver = nutus3000-hid\n    port = auto\n"
        "    vendorid = 2b89\n    productid = ffff\n    serial = DC600\n"
        "    subdriver = \"Arduino HID 0.22\"\n    usb_hid_rep_index = 0\n"
        "    usb_hid_ep_in = 1\n    usb_hid_ep_out = 1\n    pollonly\n";
    int fd=openat(dir,"conf/ups.conf",O_WRONLY|O_TRUNC|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return -1;
    int rc=write_all(fd,config,sizeof(config)-1); if(close(fd))rc=-1; return rc;
}
int nutram_stage_files(void) {
    struct passwd *p=getpwnam("nutus3000"); struct stat st; struct statfs fs;
    if(getuid() || geteuid() || !p || !p->pw_uid || !p->pw_gid)return 1;
    uid_t uid=p->pw_uid; gid_t gid=p->pw_gid;
    int run=open("/run",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC),dir=-1,rc=1;
    char stage[]="/run/nut-us3000-stage"; int created=0;
    if(run<0 || fstat(run,&st) || st.st_uid || st.st_gid || (st.st_mode&07777)!=0755 ||
       fstatfs(run,&fs) || fs.f_type!=0x01021994)goto done;
    if(fstatat(run,"nut-us3000-ram",&st,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT)goto done;
    /* Bridge serializes creators. One fixed slot bounds SIGKILL leftovers;
     * never adopt/delete an unrecognized interrupted stage on the next call. */
    if(mkdir(stage,0700))goto done;
    created=1;
    dir=open(stage,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC); if(dir<0)goto done;
    for(size_t i=0;i<sizeof(dirs)/sizeof(*dirs);i++)if(mkdirat(dir,dirs[i],0700))goto done;
    for(size_t i=0;i<sizeof(files)/sizeof(*files);i++) {
        const struct file *f=&files[i];
        int fd=openat(dir,f->dst,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
        if(fd<0)goto done;
        int fail=f->package?package_copy(f,fd,uid,gid):copy_data(f,fd);
        if(!fail)fail=fchown(fd,0,gid) || fchmod(fd,f->mode);
        if(close(fd))fail=1;
        if(fail)goto done;
    }
    if(configuration(dir) ||
       symlinkat("libusb-1.0.so.0.5.0",dir,"lib/libusb-1.0.so.0") ||
       symlinkat("libupsclient.so.7.1.0",dir,"lib/libupsclient.so.7"))goto done;
    for(size_t i=0;i<sizeof(dirs)/sizeof(*dirs);i++) {
        int sub=openat(dir,dirs[i],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        if(sub<0)goto done;
        int fail=fchmod(sub,0750) || fchown(sub,!strcmp(dirs[i],"state")?uid:0,gid);
        close(sub); if(fail)goto done;
    }
    if(fchown(dir,0,gid) || fchmod(dir,0750))goto done;
    /* /run is root-owned, and bridge lock excludes another authorized publish. */
    if(fstatat(run,"nut-us3000-ram",&st,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT ||
       renameat(run,stage+5,run,"nut-us3000-ram"))goto done;
    created=0; rc=0;
done:
    if(created && dir>=0) {
        /* Only files created by this invocation; never recursive user data removal. */
        for(size_t i=0;i<sizeof(files)/sizeof(*files);i++)(void)unlinkat(dir,files[i].dst,0);
        (void)unlinkat(dir,"lib/libusb-1.0.so.0",0); (void)unlinkat(dir,"lib/libupsclient.so.7",0);
        for(size_t i=0;i<sizeof(dirs)/sizeof(*dirs);i++)(void)unlinkat(dir,dirs[i],AT_REMOVEDIR);
    }
    if(dir>=0)close(dir);
    if(created)(void)rmdir(stage);
    if(run>=0)close(run);
    return rc;
}

static const char *units[]={"nutus3000_ram.slice","nut-us3000-ram-driver.service",
                            "nut-us3000-ram-server.service"};
static const char *unit_dirs[]={"/run/systemd/system","/etc/systemd/system","/usr/lib/systemd/system"};
static int root_dir(const char *path) {
    int fd=open(path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC); struct stat st;
    if(fd<0)return -1;
    if(fstat(fd,&st) || st.st_uid || st.st_gid || (st.st_mode&0022)) {close(fd);return -1;}
    return fd;
}
/* 0 absent, 1 exact root-owned unit, -1 ambiguous. */
static int unit_file(int dir,const char *name,int trusted) {
    int fd=openat(dir,name,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC); struct stat a,b;
    if(fd<0)return errno==ENOENT?0:-1;
    int rc=-1; char x[8192],y[8192];
    if(fstat(fd,&a) || fstat(trusted,&b) || !S_ISREG(a.st_mode) || a.st_uid || a.st_gid ||
       a.st_nlink!=1 || (a.st_mode&07777)!=0644 || a.st_size<=0 ||
       a.st_size>=8192 || a.st_size!=b.st_size || lseek(trusted,0,SEEK_SET)<0)goto done;
    if(read(fd,x,sizeof(x))==a.st_size && read(trusted,y,sizeof(y))==a.st_size &&
       !memcmp(x,y,(size_t)a.st_size))rc=1;
done: close(fd); return rc;
}
/* Files only. Caller must daemon-reload and attest loaded FragmentPath/drop-ins
 * before START; removal is legal only after native quiescence. */
static int units_change(int remove) {
    int dirs_fd[3]={-1,-1,-1},source[3]={-1,-1,-1},created[3]={0},state[3],rc=1;
    if(getuid() || geteuid())return 1;
    for(int i=0;i<3;i++) { dirs_fd[i]=root_dir(unit_dirs[i]); if(dirs_fd[i]<0)goto done; }
    for(int i=0;i<3;i++) {
        char path[256]; struct stat st;
        snprintf(path,sizeof(path),CONTROL "/%s.in",units[i]);
        source[i]=open(path,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC);
        if(source[i]<0 || fstat(source[i],&st) || !S_ISREG(st.st_mode) || st.st_uid ||
           st.st_gid || st.st_nlink!=1 || (st.st_mode&07777)!=0600 || st.st_size<=0 || st.st_size>=8192)goto done;
        for(int j=0;j<3;j++) {
            if(j && (fstatat(dirs_fd[j],units[i],&st,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT))goto done;
            snprintf(path,sizeof(path),"%s.d",units[i]);
            if(fstatat(dirs_fd[j],path,&st,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT)goto done;
        }
        state[i]=unit_file(dirs_fd[0],units[i],source[i]); if(state[i]<0)goto done;
    }
    for(int i=0;i<3;i++) {
        if(remove) { if(state[i] && unlinkat(dirs_fd[0],units[i],0))goto done; }
        else if(!state[i]) {
            int fd=openat(dirs_fd[0],units[i],O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
            if(fd<0)goto done;
            created[i]=1; char buf[8192];
            ssize_t n=read(source[i],buf,sizeof(buf));
            int fail=n<=0 || n>=(ssize_t)sizeof(buf) || write_all(fd,buf,(size_t)n) ||
                fchown(fd,0,0) || fchmod(fd,0644);
            if(close(fd))fail=1;
            if(fail)goto done;
        }
    }
    rc=0;
done:
    if(rc && !remove && dirs_fd[0]>=0)
        for(int i=0;i<3;i++)if(created[i])(void)unlinkat(dirs_fd[0],units[i],0);
    for(int i=0;i<3;i++) { if(source[i]>=0)close(source[i]); if(dirs_fd[i]>=0)close(dirs_fd[i]); }
    return rc;
}
int nutram_install_unit_files(void) { return units_change(0); }
int nutram_remove_unit_files(void) { return units_change(1); }

static int ram_entry(int dir,const char *name,uid_t uid,gid_t gid,mode_t mode,int directory) {
    struct stat st;
    return fstatat(dir,name,&st,AT_SYMLINK_NOFOLLOW) || st.st_uid!=uid || st.st_gid!=gid ||
        (st.st_mode&07777)!=mode || (directory?!S_ISDIR(st.st_mode):!S_ISREG(st.st_mode)) ||
        (!directory && st.st_nlink!=1);
}
static int state_entries(int fd,uid_t uid,int remove) {
    int copy=dup(fd); if(copy<0)return 1;
    DIR *d=fdopendir(copy); if(!d) {close(copy);return 1;}
    rewinddir(d); struct dirent *e; unsigned count=0; int rc=0;
    errno=0;
    while((e=readdir(d))) {
        if(!strcmp(e->d_name,".") || !strcmp(e->d_name,".."))continue;
        struct stat st;
        if(++count>32 || fstatat(fd,e->d_name,&st,AT_SYMLINK_NOFOLLOW) || st.st_uid!=uid ||
           (!S_ISREG(st.st_mode) && !S_ISSOCK(st.st_mode)) || st.st_nlink!=1 ||
           (remove && unlinkat(fd,e->d_name,0))) {rc=1;break;}
        errno=0;
    }
    if(errno)rc=1;
    closedir(d); return rc;
}
int nutram_remove_files(void) {
    struct passwd *p=getpwnam("nutus3000"); struct stat st;
    if(getuid() || geteuid() || !p || !p->pw_uid || !p->pw_gid)return 1;
    int run=root_dir("/run"),dir=-1,state=-1,rc=1;
    if(run<0)goto done;
    if(fstatat(run,"nut-us3000-ram",&st,AT_SYMLINK_NOFOLLOW)) {
        if(errno==ENOENT)rc=0;
        goto done;
    }
    if(ram_entry(run,"nut-us3000-ram",0,p->pw_gid,0750,1))goto done;
    dir=openat(run,"nut-us3000-ram",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(dir<0)goto done;
    for(size_t i=0;i<sizeof(dirs)/sizeof(*dirs);i++)
        if(ram_entry(dir,dirs[i],!strcmp(dirs[i],"state")?p->pw_uid:0,p->pw_gid,0750,1))goto done;
    for(size_t i=0;i<sizeof(files)/sizeof(*files);i++)
        if(ram_entry(dir,files[i].dst,0,p->pw_gid,files[i].mode,0))goto done;
    const char *links[]={"lib/libusb-1.0.so.0","lib/libupsclient.so.7"};
    const char *targets[]={"libusb-1.0.so.0.5.0","libupsclient.so.7.1.0"};
    for(int i=0;i<2;i++) {
        char buf[128]; ssize_t n=readlinkat(dir,links[i],buf,sizeof(buf));
        if(n!=(ssize_t)strlen(targets[i]) || memcmp(buf,targets[i],(size_t)n))goto done;
    }
    state=openat(dir,"state",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(state<0 || state_entries(state,p->pw_uid,0) || state_entries(state,p->pw_uid,1))goto done;
    for(size_t i=0;i<sizeof(files)/sizeof(*files);i++)if(unlinkat(dir,files[i].dst,0))goto done;
    for(int i=0;i<2;i++)if(unlinkat(dir,links[i],0))goto done;
    for(size_t i=0;i<sizeof(dirs)/sizeof(*dirs);i++)if(unlinkat(dir,dirs[i],AT_REMOVEDIR))goto done;
    if(unlinkat(run,"nut-us3000-ram",AT_REMOVEDIR))goto done;
    rc=0;
done:
    if(state>=0)close(state);
    if(dir>=0)close(dir);
    if(run>=0)close(run);
    return rc;
}
