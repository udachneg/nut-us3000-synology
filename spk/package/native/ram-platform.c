/* Fixed preparation/retirement phases. Bridge owns lifecycle serialization. */
#include "ram-bridge.h"
#include "ram-exec.h"
#include <stdio.h>
#include <string.h>

int nutram_stage_files(void);
int nutram_install_unit_files(void);
int nutram_remove_unit_files(void);
int nutram_remove_files(void);

static int quiet_operation(enum nutram_operation op) {
    struct nutram_exec_result r;
    return nutram_exec(op,&r)!=NUTRAM_EXEC_OK || r.exit_code || r.out_size || r.err_size;
}

static int loaded(enum nutram_operation op) {
    const char *unit=op==NUTRAM_LOAD_DRIVER?"nut-us3000-ram-driver.service":
        op==NUTRAM_LOAD_SERVER?"nut-us3000-ram-server.service":"nutus3000_ram.slice";
    const char *keys[]={"Id","LoadState","FragmentPath","DropInPaths"};
    char *values[4]={0}; char expected[128];
    struct nutram_exec_result r;
    if(nutram_exec(op,&r)!=NUTRAM_EXEC_OK || r.exit_code || r.err_size ||
       !r.out_size || r.out_size>NUTRAM_CAPTURE_MAX || r.out[r.out_size-1]!='\n')return 1;
    for(size_t i=0;i<r.out_size;i++)
        if(r.out[i]!='\n' && ((unsigned char)r.out[i]<32 || (unsigned char)r.out[i]>126))return 1;
    for(char *line=r.out;*line;) {
        char *end=strchr(line,'\n'),*sep=strchr(line,'=');
        if(!end || !sep || sep>end)return 1;
        *end=0; *sep=0; unsigned i;
        for(i=0;i<4;i++)if(!strcmp(line,keys[i]))break;
        if(i==4 || values[i])return 1;
        values[i]=sep+1; line=end+1;
    }
    for(unsigned i=0;i<4;i++)if(!values[i])return 1;
    int n=snprintf(expected,sizeof(expected),"/run/systemd/system/%s",unit);
    return n<0 || (size_t)n>=sizeof(expected) || strcmp(values[0],unit) ||
        strcmp(values[1],"loaded") || strcmp(values[2],expected) || *values[3];
}

int nutram_platform_phase(enum nutram_phase phase) {
    if(phase==NUTRAM_PREPARE) {
        /* Do not publish new binaries/config while an old runtime or listener
         * survives. No enable/preset or package path is executed as root. */
        if(quiet_operation(NUTRAM_KERNEL_QUIESCENT) || nutram_stage_files() ||
           nutram_install_unit_files() || quiet_operation(NUTRAM_DAEMON_RELOAD))return 1;
        for(int op=NUTRAM_LOAD_DRIVER;op<=NUTRAM_LOAD_SLICE;op++)
            if(loaded(op))return 1;
        return 0;
    }
    if(phase==NUTRAM_CLEANUP) {
        /* Caller already proved quiescence. Keep code if unload/reload fails. */
        return nutram_remove_unit_files() || quiet_operation(NUTRAM_DAEMON_RELOAD) || nutram_remove_files();
    }
    if(phase==NUTRAM_CONTROLLER_STOP)return quiet_operation(NUTRAM_DRAIN_CONTROLLER);
    if(phase==NUTRAM_SAFE_ENTRY) {
        struct nutram_exec_result r;
        static const char expected[]="SAFE_ENTRY_PENDING\n";
        return nutram_exec(NUTRAM_READ_SAFE_QUEUE,&r)!=NUTRAM_EXEC_OK || r.exit_code ||
            r.err_size || r.out_size!=sizeof(expected)-1 || memcmp(r.out,expected,sizeof(expected)-1);
    }
    return 2;
}
