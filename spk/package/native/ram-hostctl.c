/* Link the RAM lifecycle into the existing native helper, not a second helper.
 * The original translation unit supplies fixed network/USB/description logic. */
#ifdef _GNU_SOURCE
#undef _GNU_SOURCE
#endif
#define main nutram_legacy_main
#include "nut-us3000-hostctl.c"
#undef main
#include "ram-bridge.h"
#include "ram-runtime.h"

int nutram_platform_phase(enum nutram_phase);

static int ram_remaining(enum nutram_phase phase) {
    if(phase==NUTRAM_ENSURE)return ensure_network()!=0 || usb_access(1)!=0;
    if(phase==NUTRAM_AUDIT)return audit_network()!=0;
    if(phase==NUTRAM_RELEASE)return release_host()!=0;
    if(phase==NUTRAM_USB_PRESENT) {
        struct usb_target target;
        int rc=find_usb_target(&target);
        return rc==0?0:(rc==1 || rc==2)?75:1;
    }
    return nutram_platform_phase(phase);
}
static int ram_phase(enum nutram_phase phase) {
    return nutram_runtime_phase(phase,ram_remaining);
}
int main(int argc,char **argv) {
    if(argc==2 && argv && argv[1]) {
        if(!strncmp(argv[1],"ram-",4))return nutram_bridge_dispatch(argc,argv,ram_phase);
        /* Old private verbs must not bypass the new lifecycle locks. */
        if(!strcmp(argv[1],"ensure") || !strcmp(argv[1],"release")) {
            char *args[]={argv[0],!strcmp(argv[1],"ensure")?"ram-start":"ram-stop",NULL};
            return nutram_bridge_dispatch(2,args,ram_phase);
        }
    }
    return nutram_legacy_main(argc,argv);
}
