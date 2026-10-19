/*
 * Copyright (C) 2026 Hevtech
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/types.h>
#ifdef __linux__
#include <sys/sysmacros.h>
#endif
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#if defined(NUT_US3000_TESTING) && !defined(O_NOFOLLOW)
#define O_NOFOLLOW 0
#endif

#ifndef NUT_US3000_SYSFS_DEVICES
#define NUT_US3000_SYSFS_DEVICES "/sys/bus/usb/devices"
#endif
#ifndef NUT_US3000_USBHID_BIND
#define NUT_US3000_USBHID_BIND "/sys/bus/usb/drivers/usbhid/bind"
#endif
#ifndef NUT_US3000_USB_DEVICES
#define NUT_US3000_USB_DEVICES "/dev/bus/usb"
#endif
#ifndef NUT_US3000_IP
#define NUT_US3000_IP "/usr/sbin/ip"
#endif
#ifndef NUT_US3000_IPTABLES
#define NUT_US3000_IPTABLES "/sbin/iptables"
#endif
#ifndef NUT_US3000_LEGACY_SERVICE
#define NUT_US3000_LEGACY_SERVICE "/usr/local/etc/services.d/nut-us3000.sc"
#endif
#ifndef NUT_US3000_SYNOFIREWALL
#define NUT_US3000_SYNOFIREWALL "/usr/syno/bin/synofirewall"
#endif
#ifndef NUT_US3000_SERVICE_DIR_OWNER
#define NUT_US3000_SERVICE_DIR_OWNER 0
#endif

#define TARGET_VENDOR "2b89"
#define TARGET_PRODUCT "ffff"
#define TARGET_SERIAL "DC600"
#define TARGET_INTERFACE_NUMBER "00"
#define LOCAL_ALIAS "10.255.255.1/32"
#define LOCAL_LABEL "lo:nutus3000"
#define NUT_PORT "3493"
#define OUTPUT_LIMIT 8192

static const char legacy_port_config[] =
    "[nut-us3000]\n"
    "title=\"NUT US3000 (host-local)\"\n"
    "desc=\"Local DSM UPS integration endpoint\"\n"
    "port_forward=\"no\"\n"
    "dst.ports=\"3493/tcp\"\n";

static char *const safe_environment[] = {
    (char *)"PATH=/usr/sbin:/usr/bin:/sbin:/bin",
    (char *)"LC_ALL=C",
    NULL
};

static void error_message(const char *message)
{
    (void)fprintf(stderr, "ERROR: %s\n", message);
}

static int safe_path(char *buffer, size_t size, const char *left, const char *right)
{
    int written = snprintf(buffer, size, "%s/%s", left, right);
    return written >= 0 && (size_t)written < size ? 0 : -1;
}

static int normalize_root_identity(void)
{
#ifdef NUT_US3000_TESTING
#ifdef NUT_US3000_TEST_DENY_ROOT
    return -1;
#else
    return 0;
#endif
#else
    if (geteuid() != 0 || setuid(0) != 0 || getuid() != 0 || geteuid() != 0) {
        return -1;
    }
    (void)umask(077);
    return 0;
#endif
}

static int run_network_tool(const char *path, char *const argv[], char *output, size_t output_size)
{
    int descriptors[2];
    pid_t child;
    size_t used = 0;
    int status;

    if (output_size == 0 || pipe(descriptors) != 0) {
        return -1;
    }
    child = fork();
    if (child < 0) {
        (void)close(descriptors[0]);
        (void)close(descriptors[1]);
        return -1;
    }
    if (child == 0) {
        (void)close(descriptors[0]);
        if (dup2(descriptors[1], STDOUT_FILENO) < 0) {
            _exit(125);
        }
        (void)close(descriptors[1]);
        execve(path, argv, safe_environment);
        _exit(127);
    }

    (void)close(descriptors[1]);
    while (used + 1 < output_size) {
        ssize_t count = read(descriptors[0], output + used, output_size - used - 1);
        if (count > 0) {
            used += (size_t)count;
            continue;
        }
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0) {
            (void)close(descriptors[0]);
            (void)waitpid(child, &status, 0);
            return -1;
        }
        break;
    }
    if (used + 1 == output_size) {
        char extra;
        if (read(descriptors[0], &extra, 1) > 0) {
            (void)close(descriptors[0]);
            (void)waitpid(child, &status, 0);
            return -1;
        }
    }
    output[used] = '\0';
    (void)close(descriptors[0]);
    do {
        status = 0;
    } while (waitpid(child, &status, 0) < 0 && errno == EINTR);
    if (!WIFEXITED(status)) {
        return -1;
    }
    return WEXITSTATUS(status);
}

static int alias_state(void)
{
    char output[OUTPUT_LIMIT];
    char copy[OUTPUT_LIMIT];
    char *save = NULL;
    char *token;
    const char *tokens[64];
    size_t count = 0;
    int found_scope = 0;
    int found_label = 0;
    char *const argv[] = {
        (char *)NUT_US3000_IP, (char *)"-4", (char *)"-o", (char *)"address",
        (char *)"show", (char *)"to", (char *)LOCAL_ALIAS, NULL
    };
    int result = run_network_tool(NUT_US3000_IP, argv, output, sizeof(output));
    if (result != 0) {
        return -1;
    }
    if (output[0] == '\0') {
        return 0;
    }
    if (strchr(output, '\n') != NULL && strchr(output, '\n') + 1 < output + strlen(output)) {
        return -1;
    }
    if (strlen(output) >= sizeof(copy)) {
        return -1;
    }
    (void)strcpy(copy, output);
    token = strtok_r(copy, " \t\r\n", &save);
    while (token != NULL && count < sizeof(tokens) / sizeof(tokens[0])) {
        tokens[count++] = token;
        token = strtok_r(NULL, " \t\r\n", &save);
    }
    if (token != NULL || count < 6 || strcmp(tokens[1], "lo") != 0 ||
        strcmp(tokens[2], "inet") != 0 || strcmp(tokens[3], LOCAL_ALIAS) != 0) {
        return -1;
    }
    for (size_t index = 4; index < count; ++index) {
        if (index + 1 < count && strcmp(tokens[index], "scope") == 0 &&
            strcmp(tokens[index + 1], "host") == 0) {
            found_scope = 1;
        }
        size_t label_length = strlen(LOCAL_LABEL);
        if (strcmp(tokens[index], LOCAL_LABEL) == 0 ||
            (strncmp(tokens[index], LOCAL_LABEL, label_length) == 0 &&
             tokens[index][label_length] == '\\' &&
             tokens[index][label_length + 1] == '\0')) {
            found_label = 1;
        }
    }
    return found_scope && found_label ? 1 : -1;
}

static int reload_firewall(void)
{
    char output[OUTPUT_LIMIT];
    char *const argv[] = {
        (char *)NUT_US3000_SYNOFIREWALL, (char *)"--reload", NULL
    };
    return run_network_tool(NUT_US3000_SYNOFIREWALL, argv, output, sizeof(output)) == 0 ? 0 : -1;
}

static int retire_port_config(void)
{
    char parent[PATH_MAX];
    const char *name = strrchr(NUT_US3000_LEGACY_SERVICE, '/');
    size_t parent_length;
    int directory_descriptor;
    int file_descriptor;
    struct stat directory_metadata;
    struct stat file_metadata;
    struct stat path_metadata;
    char content[sizeof(legacy_port_config)];
    size_t used = 0;

    if (name == NULL || name[1] == '\0') {
        return -1;
    }
    parent_length = (size_t)(name - NUT_US3000_LEGACY_SERVICE);
    if (parent_length == 0 || parent_length >= sizeof(parent)) {
        return -1;
    }
    (void)memcpy(parent, NUT_US3000_LEGACY_SERVICE, parent_length);
    parent[parent_length] = '\0';
    ++name;

    directory_descriptor = open(parent, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory_descriptor < 0 ||
        fstat(directory_descriptor, &directory_metadata) != 0 ||
        !S_ISDIR(directory_metadata.st_mode) ||
        directory_metadata.st_uid != (uid_t)NUT_US3000_SERVICE_DIR_OWNER ||
        (directory_metadata.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        if (directory_descriptor >= 0) {
            (void)close(directory_descriptor);
        }
        return -1;
    }

    file_descriptor = openat(directory_descriptor, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (file_descriptor < 0) {
        int saved_errno = errno;
        (void)close(directory_descriptor);
        return saved_errno == ENOENT ? 0 : -1;
    }
    if (fstat(file_descriptor, &file_metadata) != 0 ||
        !S_ISREG(file_metadata.st_mode) ||
        file_metadata.st_size != (off_t)(sizeof(legacy_port_config) - 1)) {
        (void)close(file_descriptor);
        (void)close(directory_descriptor);
        return -1;
    }
    while (used < sizeof(legacy_port_config) - 1) {
        ssize_t count = read(
            file_descriptor,
            content + used,
            sizeof(legacy_port_config) - 1 - used
        );
        if (count > 0) {
            used += (size_t)count;
            continue;
        }
        if (count < 0 && errno == EINTR) {
            continue;
        }
        (void)close(file_descriptor);
        (void)close(directory_descriptor);
        return -1;
    }
    {
        char extra;
        ssize_t count;
        do {
            count = read(file_descriptor, &extra, 1);
        } while (count < 0 && errno == EINTR);
        if (count != 0 || memcmp(content, legacy_port_config, sizeof(legacy_port_config) - 1) != 0) {
            (void)close(file_descriptor);
            (void)close(directory_descriptor);
            return -1;
        }
    }
    if (fstatat(directory_descriptor, name, &path_metadata, AT_SYMLINK_NOFOLLOW) != 0 ||
        !S_ISREG(path_metadata.st_mode) ||
        path_metadata.st_dev != file_metadata.st_dev ||
        path_metadata.st_ino != file_metadata.st_ino ||
        unlinkat(directory_descriptor, name, 0) != 0) {
        (void)close(file_descriptor);
        (void)close(directory_descriptor);
        return -1;
    }
    (void)close(file_descriptor);
    if (fstatat(directory_descriptor, name, &path_metadata, AT_SYMLINK_NOFOLLOW) == 0 ||
        errno != ENOENT) {
        (void)close(directory_descriptor);
        return -1;
    }
    (void)close(directory_descriptor);
    return reload_firewall();
}

static int alias_add(void)
{
    char output[OUTPUT_LIMIT];
    char *const argv[] = {
        (char *)NUT_US3000_IP, (char *)"address", (char *)"add", (char *)LOCAL_ALIAS,
        (char *)"dev", (char *)"lo", (char *)"label", (char *)LOCAL_LABEL,
        (char *)"scope", (char *)"host", NULL
    };
    return run_network_tool(NUT_US3000_IP, argv, output, sizeof(output)) == 0 ? 0 : -1;
}

static int alias_delete_exact(void)
{
    char output[OUTPUT_LIMIT];
    char *const argv[] = {
        (char *)NUT_US3000_IP, (char *)"address", (char *)"del", (char *)LOCAL_ALIAS,
        (char *)"dev", (char *)"lo", NULL
    };
    return run_network_tool(NUT_US3000_IP, argv, output, sizeof(output)) == 0 ? 0 : -1;
}

static int alias_remove(void)
{
    int state = alias_state();
    if (state == 0) {
        return 0;
    }
    if (state != 1 || alias_delete_exact() != 0) {
        return -1;
    }
    return alias_state() == 0 ? 0 : -1;
}

static int transient_guard_state(void)
{
    char output[OUTPUT_LIMIT];
    char *const argv[] = {
        (char *)NUT_US3000_IPTABLES, (char *)"-C", (char *)"INPUT", (char *)"!",
        (char *)"-i", (char *)"lo", (char *)"-d", (char *)LOCAL_ALIAS,
        (char *)"-p", (char *)"tcp", (char *)"--dport", (char *)NUT_PORT,
        (char *)"-j", (char *)"DROP", NULL
    };
    int result = run_network_tool(NUT_US3000_IPTABLES, argv, output, sizeof(output));
    if (result == 0) {
        return 1;
    }
    return result == 1 ? 0 : -1;
}

static int dsm_guard_state(void)
{
    char output[OUTPUT_LIMIT];
    char *const argv[] = {
        (char *)NUT_US3000_IPTABLES, (char *)"-C", (char *)"INPUT_FIREWALL",
        (char *)"-p", (char *)"tcp", (char *)"--dport", (char *)NUT_PORT,
        (char *)"-j", (char *)"DROP", NULL
    };
    int result = run_network_tool(NUT_US3000_IPTABLES, argv, output, sizeof(output));
    if (result == 0) {
        return 1;
    }
    return result == 1 ? 0 : -1;
}

static int effective_guard_state(void)
{
    int state = transient_guard_state();
    if (state != 0) {
        return state;
    }
    return dsm_guard_state();
}

static int guard_change(const char *operation, int position)
{
    char output[OUTPUT_LIMIT];
    char *const insert_argv[] = {
        (char *)NUT_US3000_IPTABLES, (char *)operation, (char *)"INPUT", (char *)"1",
        (char *)"!", (char *)"-i", (char *)"lo", (char *)"-d", (char *)LOCAL_ALIAS,
        (char *)"-p", (char *)"tcp", (char *)"--dport", (char *)NUT_PORT,
        (char *)"-j", (char *)"DROP", NULL
    };
    char *const delete_argv[] = {
        (char *)NUT_US3000_IPTABLES, (char *)operation, (char *)"INPUT", (char *)"!",
        (char *)"-i", (char *)"lo", (char *)"-d", (char *)LOCAL_ALIAS,
        (char *)"-p", (char *)"tcp", (char *)"--dport", (char *)NUT_PORT,
        (char *)"-j", (char *)"DROP", NULL
    };
    char *const *argv = position ? insert_argv : delete_argv;
    return run_network_tool(NUT_US3000_IPTABLES, (char *const *)argv, output, sizeof(output)) == 0 ? 0 : -1;
}

static int guard_remove(void)
{
    int state = transient_guard_state();
    if (state == 0) {
        return 0;
    }
    if (state != 1 || guard_change("-D", 0) != 0) {
        return -1;
    }
    return transient_guard_state() == 0 ? 0 : -1;
}

static int ensure_network(void)
{
    int alias = alias_state();
    int guard;
    int alias_created = 0;
    int guard_created = 0;

    if (alias < 0) {
        return -1;
    }
    if (alias == 0) {
        if (alias_add() != 0) {
            return -1;
        }
        alias_created = 1;
        if (alias_state() != 1) {
            (void)alias_delete_exact();
            return -1;
        }
    }
    guard = transient_guard_state();
    if (guard < 0) {
        if (alias_created) {
            (void)alias_remove();
        }
        return -1;
    }
    if (guard == 0) {
        if (guard_change("-I", 1) != 0) {
            if (alias_created) {
                (void)alias_remove();
            }
            return -1;
        }
        guard_created = 1;
    }
    if (alias_state() != 1 || transient_guard_state() != 1) {
        if (guard_created) {
            (void)guard_remove();
        }
        if (alias_created) {
            (void)alias_remove();
        }
        return -1;
    }
    return 0;
}

static int read_attribute(const char *path, char *buffer, size_t size)
{
    int descriptor;
    ssize_t count;
    struct stat metadata;

    if (size < 2) {
        return -1;
    }
    descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor < 0) {
        return errno == ENOENT ? 1 : -1;
    }
    if (fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode)) {
        (void)close(descriptor);
        return -1;
    }
    count = read(descriptor, buffer, size - 1);
    if (count <= 0) {
        (void)close(descriptor);
        return -1;
    }
    buffer[count] = '\0';
    if (read(descriptor, buffer + size - 1, 1) > 0) {
        (void)close(descriptor);
        return -1;
    }
    (void)close(descriptor);
    while (count > 0 && (buffer[count - 1] == '\n' || buffer[count - 1] == '\r')) {
        buffer[--count] = '\0';
    }
    return count > 0 ? 0 : -1;
}

static int exact_attribute(const char *directory, const char *name, const char *expected)
{
    char path[PATH_MAX];
    char value[128];
    int result;
    if (safe_path(path, sizeof(path), directory, name) != 0) return -1;
    result = read_attribute(path, value, sizeof(value));
    if (result != 0) return result;
    return strcmp(value, expected) == 0 ? 0 : -1;
}

static int driver_state(const char *interface_path)
{
    char path[PATH_MAX];
    char target[PATH_MAX];
    ssize_t count;
    const char *base;

    if (safe_path(path, sizeof(path), interface_path, "driver") != 0) {
        return -1;
    }
    count = readlink(path, target, sizeof(target) - 1);
    if (count < 0) {
        return errno == ENOENT ? 0 : -1;
    }
    target[count] = '\0';
    base = strrchr(target, '/');
    base = base == NULL ? target : base + 1;
    return strcmp(base, "usbhid") == 0 ? 1 : -1;
}

struct usb_target {
    char device[PATH_MAX];
    char interface[PATH_MAX];
    char interface_name[NAME_MAX + 1];
};

/* 0: exact target, 1: unplugged, 2: still enumerating, -1: unsafe/ambiguous. */
static int find_usb_target(struct usb_target *target)
{
    DIR *directory = opendir(NUT_US3000_SYSFS_DEVICES);
    struct dirent *entry;
    char device_name[NAME_MAX + 1] = "";
    char device_path[PATH_MAX];
    char interface_name[NAME_MAX + 1] = "";
    char interface_path[PATH_MAX];
    int matching_devices = 0;
    int matching_interfaces = 0;
    int incomplete = 0;

    if (directory == NULL) {
        return -1;
    }
    while ((entry = readdir(directory)) != NULL) {
        char vendor_path[PATH_MAX];
        char vendor[128];
        char product[128];
        int read_result;
        if (entry->d_name[0] == '.' || strchr(entry->d_name, ':') != NULL ||
            safe_path(device_path, sizeof(device_path), NUT_US3000_SYSFS_DEVICES, entry->d_name) != 0 ||
            safe_path(vendor_path, sizeof(vendor_path), device_path, "idVendor") != 0) {
            continue;
        }
        read_result = read_attribute(vendor_path, vendor, sizeof(vendor));
        if (read_result == 1) {
            continue;
        }
        if (read_result != 0 ||
            safe_path(vendor_path, sizeof(vendor_path), device_path, "idProduct") != 0 ||
            read_attribute(vendor_path, product, sizeof(product)) != 0) {
            goto finish;
        }
        if (strcmp(vendor, TARGET_VENDOR) == 0 && strcmp(product, TARGET_PRODUCT) == 0) {
            ++matching_devices;
            if (matching_devices == 1) {
                (void)strncpy(device_name, entry->d_name, sizeof(device_name) - 1);
                device_name[sizeof(device_name) - 1] = '\0';
            }
        }
    }
    (void)closedir(directory);
    directory = NULL;
    if (matching_devices == 0) {
        return 1;
    }
    if (matching_devices != 1 ||
        safe_path(device_path, sizeof(device_path), NUT_US3000_SYSFS_DEVICES, device_name) != 0) {
        return -1;
    }
    {
        int serial_result = exact_attribute(device_path, "serial", TARGET_SERIAL);
        if (serial_result == 1) incomplete = 1;
        else if (serial_result != 0) return -1;
    }

    directory = opendir(NUT_US3000_SYSFS_DEVICES);
    if (directory == NULL) {
        return -1;
    }
    while ((entry = readdir(directory)) != NULL) {
        char number_path[PATH_MAX];
        char number[128];
        int number_result;
        size_t prefix = strlen(device_name);
        if (strncmp(entry->d_name, device_name, prefix) != 0 || entry->d_name[prefix] != ':' ||
            safe_path(interface_path, sizeof(interface_path), NUT_US3000_SYSFS_DEVICES, entry->d_name) != 0 ||
            safe_path(number_path, sizeof(number_path), interface_path, "bInterfaceNumber") != 0) {
            continue;
        }
        ++matching_interfaces;
        number_result = read_attribute(number_path, number, sizeof(number));
        if (number_result == 1) {
            incomplete = 1;
            continue;
        }
        if (number_result != 0) {
            goto finish;
        }
        if (strcmp(number, TARGET_INTERFACE_NUMBER) != 0) {
            goto finish;
        }
        (void)strncpy(interface_name, entry->d_name, sizeof(interface_name) - 1);
        interface_name[sizeof(interface_name) - 1] = '\0';
    }
    (void)closedir(directory);
    directory = NULL;
    if (matching_interfaces > 1) return -1;
    if (matching_interfaces == 0 || incomplete) return 2;
    if (matching_interfaces != 1 || interface_name[0] == '\0' ||
        safe_path(interface_path, sizeof(interface_path), NUT_US3000_SYSFS_DEVICES, interface_name) != 0) {
        return -1;
    }
    (void)strcpy(target->device, device_path);
    (void)strcpy(target->interface, interface_path);
    (void)strcpy(target->interface_name, interface_name);
    return 0;

finish:
    if (directory != NULL) {
        (void)closedir(directory);
    }
    return -1;
}

static int restore_usb(void)
{
    struct usb_target target;
    int result = find_usb_target(&target);
    if (result != 0) return result == 1 ? 0 : -1;
    result = driver_state(target.interface);
    if (result == 1) {
        return 0;
    }
    if (result != 0) {
        return -1;
    }
    {
        int descriptor = open(NUT_US3000_USBHID_BIND, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
        size_t length = strlen(target.interface_name);
        if (descriptor < 0 || write(descriptor, target.interface_name, length) != (ssize_t)length) {
            if (descriptor >= 0) {
                (void)close(descriptor);
            }
            return -1;
        }
        (void)close(descriptor);
    }
    for (int attempt = 0; attempt < 30; ++attempt) {
        struct timespec pause = {0, 100000000L};
        result = driver_state(target.interface);
        if (result == 1) {
            return 0;
        }
        if (result < 0) {
            return -1;
        }
        (void)nanosleep(&pause, NULL);
    }
    return -1;
}

static int usb_number(const char *directory, const char *name, unsigned limit, unsigned *value)
{
    char path[PATH_MAX], text[32];
    unsigned number = 0;
    int result;
    if (safe_path(path, sizeof(path), directory, name) != 0) return -1;
    result = read_attribute(path, text, sizeof(text));
    if (result != 0) return result;
    for (size_t i = 0; text[i] != '\0'; ++i) {
        if (text[i] < '0' || text[i] > '9' || number > limit / 10) return -1;
        number = number * 10 + (unsigned)(text[i] - '0');
        if (number > limit) return -1;
    }
    if (number == 0) return -1;
    *value = number;
    return 0;
}

static int trusted_usb_directory(int fd)
{
    struct stat st;
    return fd >= 0 && fstat(fd, &st) == 0 && S_ISDIR(st.st_mode) &&
        st.st_uid == 0 && (st.st_mode & 0022) == 0;
}

/* No caller-supplied paths or IDs. Open once, validate usbfs major/minor,
 * then change metadata through that descriptor, never through a raced path.
 * Unplugged devices are handled by the existing UNAVAILABLE retry policy.
 */
static int usb_access(int grant)
{
    struct usb_target target;
    struct stat st;
    struct group *group;
    unsigned bus, device, checked_bus, checked_device;
    char bus_name[4], device_name[4], dev_id[32];
    int root_fd = -1, bus_fd = -1, fd = -1, result;
    gid_t package_gid;
    mode_t mode;

    result = find_usb_target(&target);
    if (result != 0) return result == 1 || (grant && result == 2) ? 0 : -1;
    group = getgrnam("nutus3000");
    if (group == NULL || group->gr_gid == 0) return -1;
    package_gid = group->gr_gid;
    result = usb_number(target.device, "busnum", 999, &bus);
    if (result != 0) return grant && result == 1 ? 0 : -1;
    result = usb_number(target.device, "devnum", 127, &device);
    if (result != 0) return grant && result == 1 ? 0 : -1;
    (void)snprintf(bus_name, sizeof(bus_name), "%03u", bus);
    (void)snprintf(device_name, sizeof(device_name), "%03u", device);
    (void)snprintf(dev_id, sizeof(dev_id), "189:%u", (bus - 1) * 128 + device - 1);
    result = exact_attribute(target.device, "dev", dev_id);
    if (result != 0) return grant && result == 1 ? 0 : -1;

    result = -1;
    root_fd = open(NUT_US3000_USB_DEVICES, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (!trusted_usb_directory(root_fd)) goto finish;
    bus_fd = openat(root_fd, bus_name, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (bus_fd < 0 && errno == ENOENT) { result = 0; goto finish; }
    if (!trusted_usb_directory(bus_fd)) goto finish;
    fd = openat(bus_fd, device_name, O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        /* Device removal can race an ordinary polling attempt. */
        if (errno == ENOENT || errno == ENODEV) result = 0;
        goto finish;
    }
    if (fstat(fd, &st) != 0 || !S_ISCHR(st.st_mode) || st.st_uid != 0 || st.st_nlink != 1 ||
        major(st.st_rdev) != 189 || (unsigned)minor(st.st_rdev) != (bus - 1) * 128 + device - 1 ||
        exact_attribute(target.device, "idVendor", TARGET_VENDOR) != 0 ||
        exact_attribute(target.device, "idProduct", TARGET_PRODUCT) != 0 ||
        exact_attribute(target.device, "serial", TARGET_SERIAL) != 0 ||
        usb_number(target.device, "busnum", 999, &checked_bus) != 0 || checked_bus != bus ||
        usb_number(target.device, "devnum", 127, &checked_device) != 0 || checked_device != device) goto finish;
    mode = st.st_mode & 07777;
    if (grant) {
        if (!((st.st_gid == 0 && (mode == 0664 || mode == 0660 || mode == 0600)) ||
              (st.st_gid == package_gid && mode == 0660))) goto finish;
        if (st.st_gid == package_gid) { result = 0; goto finish; }
        /* Restrict first; a failed chown cannot expose a writable device. */
        if (fchmod(fd, 0600) != 0 || fchown(fd, 0, package_gid) != 0 || fchmod(fd, 0660) != 0) {
            (void)fchmod(fd, 0600);
            (void)fchown(fd, 0, 0);
            goto finish;
        }
        result = fstat(fd, &st) == 0 && st.st_uid == 0 && st.st_gid == package_gid &&
            (st.st_mode & 07777) == 0660 ? 0 : -1;
    } else {
        /* Only revoke the exact package grant, not administrator-owned settings.
         * Leave root-only access; usbfs recreates its defaults on reconnect.
         */
        if (st.st_gid != package_gid) { result = 0; goto finish; }
        if (mode != 0660 && mode != 0600) goto finish;
        if (fchmod(fd, 0600) != 0 || fchown(fd, 0, 0) != 0) goto finish;
        result = fstat(fd, &st) == 0 && st.st_uid == 0 && st.st_gid == 0 &&
            (st.st_mode & 07777) == 0600 ? 0 : -1;
    }
finish:
    if (fd >= 0) (void)close(fd);
    if (bus_fd >= 0) (void)close(bus_fd);
    if (root_fd >= 0) (void)close(root_fd);
    if (result != 0) error_message("exact UPS USB access validation or permission update failed");
    return result;
}

static int audit_network(void)
{
    return alias_state() == 1 && effective_guard_state() == 1 ? 0 : -1;
}

static int release_host(void)
{
    int failed = 0;
    if (restore_usb() != 0) {
        failed = 1;
    }
    if (usb_access(0) != 0) {
        failed = 1;
    }
    if (guard_remove() != 0) {
        failed = 1;
    }
    if (alias_remove() != 0) {
        failed = 1;
    }
    return failed ? -1 : 0;
}

/* INFO is presentation only. Never accept text, paths, or shell from the caller. */
#ifdef NUT_US3000_TESTING
#ifndef NUT_US3000_INFO_ROOT
#define NUT_US3000_INFO_ROOT "/var"
#endif
#ifndef NUT_US3000_INFO_OWNER
#define NUT_US3000_INFO_OWNER 0
#endif
#else
#define NUT_US3000_INFO_ROOT "/var"
#define NUT_US3000_INFO_OWNER 0
#endif
#define INFO_LIMIT 65536

/* Optional presentation readers, not recovery prerequisites. Paths are fixed in
   production; test builds redirect only the OS boundary. */
#ifndef NUT_US3000_TESTING
#undef NUT_US3000_SETTINGS_ROOT
#undef NUT_US3000_SETTINGS_JQ
#undef NUT_US3000_SETTINGS_SAVE
#endif
#ifndef NUT_US3000_SETTINGS_ROOT
#define NUT_US3000_SETTINGS_ROOT "/usr/syno/etc"
#endif
#ifndef NUT_US3000_SETTINGS_JQ
#define NUT_US3000_SETTINGS_JQ "/bin/jq"
#endif
#ifndef NUT_US3000_SETTINGS_SAVE
#define NUT_US3000_SETTINGS_SAVE "/sbin/iptables-save"
#endif
enum setting_result { SETTING_RED, SETTING_GREEN, SETTING_UNKNOWN, SETTING_DELAY };
static const char *const setting_en[] = {
    "🔴 settings do not match", "🟢 settings checked", "🟡 could not verify",
    "🔴 delay differs from the selected 5 minutes"
};
static const char *const setting_ru[] = {
    "🔴 настройки не соответствуют", "🟢 настройки проверены", "🟡 не удалось проверить",
    "🔴 задержка отличается от выбранных 5 минут"
};

static const struct {
    const char *command, *english, *russian;
} description_states[] = {
    {"description-pending", "🟡 check not completed yet", "🟡 проверка ещё не завершена"},
    {"description-waiting", "🟡 waiting until 10 minutes of system uptime", "🟡 ожидание после загрузки: до 10 минут uptime"},
    {"description-healthy", "🟢 UPS communication confirmed", "🟢 связь с ИБП подтверждена"},
    {"description-degraded", "🔴 communication problem", "🔴 проблема связи"},
    {"description-unavailable", "🔴 UPS unavailable; retry pending", "🔴 ИБП недоступен; ожидается повтор"},
    {"description-error", "🟡 check failed; state unconfirmed", "🟡 ошибка проверки; состояние не подтверждено"},
    {"description-stopped", "⚪ package stopped", "⚪ пакет остановлен"}
};

static int info_safe_dir(int fd)
{
    struct stat st;
    return fd >= 0 && fstat(fd, &st) == 0 && S_ISDIR(st.st_mode) &&
        st.st_uid == NUT_US3000_INFO_OWNER && !(st.st_mode & 0022);
}

static int info_read(int fd, char *data, struct stat *st)
{
    size_t used = 0;
    ssize_t n;
    if (fd < 0 || fstat(fd, st) != 0 || !S_ISREG(st->st_mode) || st->st_nlink != 1 ||
        st->st_uid != NUT_US3000_INFO_OWNER || (st->st_mode & 0022) ||
        (st->st_mode & 07000) || st->st_size <= 0 || st->st_size > INFO_LIMIT) return -1;
    while (used <= INFO_LIMIT) {
        n = read(fd, data + used, INFO_LIMIT + 1 - used);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) return -1;
        if (n == 0) break;
        used += (size_t)n;
    }
    if (used != (size_t)st->st_size || used > INFO_LIMIT || memchr(data, 0, used)) return -1;
    data[used] = 0;
    return 0;
}

static int settings_unchanged(int dir, const char *name, int fd,
                              const char *original, const struct stat *before)
{
    struct stat after, entry;
    char current[INFO_LIMIT + 2];
    return lseek(fd, 0, SEEK_SET) == 0 && info_read(fd, current, &after) == 0 &&
        fstatat(dir, name, &entry, AT_SYMLINK_NOFOLLOW) == 0 &&
        entry.st_dev == before->st_dev && entry.st_ino == before->st_ino &&
        entry.st_mode == before->st_mode && entry.st_uid == before->st_uid &&
        after.st_size == before->st_size && !strcmp(current, original);
}

static int settings_dir_unchanged(int parent, const char *name, int dir)
{
    struct stat held, entry;
    return info_safe_dir(dir) && fstat(dir, &held) == 0 &&
        fstatat(parent, name, &entry, AT_SYMLINK_NOFOLLOW) == 0 &&
        held.st_dev == entry.st_dev && held.st_ino == entry.st_ino &&
        held.st_mode == entry.st_mode && held.st_uid == entry.st_uid;
}

static enum setting_result ups_settings(int root)
{
    const char *keys[] = {"upsslave_enabled", "ups_mode", "upsslave_server", "ups_wait_time"};
    const char *wanted[] = {"yes", "slave", "10.255.255.1", "300"};
    char original[INFO_LIMIT + 2], parsed[INFO_LIMIT + 2];
    int dir = -1, fd = -1, seen[4] = {0}, differs[4] = {0};
    struct stat before;
    enum setting_result result = SETTING_UNKNOWN;
    dir = openat(root, "ups", O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (!info_safe_dir(dir)) goto done;
    fd = openat(dir, "synoups.conf", O_RDONLY | O_NONBLOCK | O_NOFOLLOW);
    if (info_read(fd, original, &before) != 0) goto done;
    strcpy(parsed, original);
    char *save = NULL;
    for (char *line = strtok_r(parsed, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        while (*line == ' ' || *line == '\t') line++;
        for (size_t k = 0; k < 4; k++) {
            size_t len = strlen(keys[k]);
            if (strncmp(line, keys[k], len) ||
                (line[len] != '=' && line[len] != ' ' && line[len] != '\t')) continue;
            char *value = line + len;
            if (seen[k]++ || *value++ != '=' || *value++ != '"') goto done;
            char *end = strchr(value, '"');
            if (!end || end[1] != 0 || end == value) goto done;
            *end = 0;
            if (strspn(value, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.:-_") != strlen(value)) goto done;
            if (k == 0 && strcmp(value, "yes") && strcmp(value, "no")) goto done;
            if (k == 1 && strcmp(value, "slave") && strcmp(value, "master") &&
                strcmp(value, "usb") && strcmp(value, "snmp")) goto done;
            if (k == 3 && strspn(value, "0123456789") != strlen(value)) goto done;
            differs[k] = strcmp(value, wanted[k]) != 0;
        }
    }
    for (size_t k = 0; k < 4; k++) if (seen[k] != 1) goto done;
    if (!settings_unchanged(dir, "synoups.conf", fd, original, &before) ||
        !settings_dir_unchanged(root, "ups", dir)) goto done;
    result = differs[0] || differs[1] || differs[2] ? SETTING_RED :
        differs[3] ? SETTING_DELAY : SETTING_GREEN;
done:
    if (fd >= 0) close(fd);
    if (dir >= 0) close(dir);
    return result;
}

/* Validate the resolved executable and every parent. DSM uses symlinks for
   system tools; their link mode is not the executable's permission mode. */
static int settings_tool_safe(const char *path)
{
    char resolved[PATH_MAX];
    struct stat st;
    if (!realpath(path, resolved) || stat(resolved, &st) != 0 || !S_ISREG(st.st_mode) ||
        st.st_uid != NUT_US3000_INFO_OWNER || (st.st_mode & 0022) || !(st.st_mode & 0111)) return 0;
#ifdef NUT_US3000_TESTING
    return 1; /* Fixture parent /private/tmp is intentionally shared. */
#else
    for (char *slash = strrchr(resolved, '/'); slash; slash = strrchr(resolved, '/')) {
        *slash = 0;
        if (stat(*resolved ? resolved : "/", &st) != 0 || !S_ISDIR(st.st_mode) ||
            st.st_uid != 0 || (st.st_mode & 0022)) return 0;
    }
    return 1;
#endif
}

static long long settings_millis(void)
{
    struct timespec t;
    return clock_gettime(CLOCK_MONOTONIC, &t) == 0 ?
        (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000 : -1;
}

/* Independent 600 ms budget per optional tool, including output and wait.
   Kill and reap on every incomplete/oversized result. No shell or caller args. */
static int settings_tool(const char *path, char *const args[], char *output, size_t size)
{
    int pipes[2], status = 0, result = -1, reaped = 0;
    size_t used = 0;
    long long start = settings_millis();
    if (start < 0 || !settings_tool_safe(path) || pipe(pipes) != 0) return -1;
    pid_t child = fork();
    if (child < 0) { close(pipes[0]); close(pipes[1]); return -1; }
    if (child == 0) {
        close(pipes[0]);
        int nullfd = open("/dev/null", O_RDWR);
        if (nullfd < 0 || dup2(nullfd, STDIN_FILENO) < 0 ||
            dup2(nullfd, STDERR_FILENO) < 0 || dup2(pipes[1], STDOUT_FILENO) < 0) _exit(125);
        close(nullfd); close(pipes[1]);
        execve(path, args, safe_environment);
        _exit(127);
    }
    close(pipes[1]);
    if (fcntl(pipes[0], F_SETFL, O_NONBLOCK) < 0) goto done;
    int eof = 0;
    while (1) {
        long long now = settings_millis();
        if (now < 0 || now - start >= 600) break;
        ssize_t n = read(pipes[0], output + used, size - 1 - used);
        if (n > 0) {
            if (memchr(output + used, 0, (size_t)n)) break;
            used += (size_t)n;
            if (used == size - 1) break;
        } else if (n == 0) eof = 1;
        else if (errno != EAGAIN && errno != EINTR) break;
        if (!reaped) {
            pid_t got = waitpid(child, &status, WNOHANG);
            if (got == child) reaped = 1;
            else if (got < 0 && errno != EINTR) break;
        }
        if (eof && reaped) {
            output[used] = 0;
            result = WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : -1;
            break;
        }
        struct pollfd pfd = {pipes[0], POLLIN, 0};
        if (eof) (void)poll(NULL, 0, 5);
        else (void)poll(&pfd, 1, 5);
    }
done:
    close(pipes[0]);
    if (!reaped) {
        (void)kill(child, SIGKILL);
        while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
    }
    return result;
}

/* Deliberately recognize only the DSM topology observed on the target NAS.
   Established connections and loopback precede deny; no external probe implied. */
static enum setting_result firewall_effective(void)
{
    char data[INFO_LIMIT + 2], *save = NULL;
    char *const args[] = {(char *)NUT_US3000_SETTINGS_SAVE, "-t", "filter", NULL};
    const char *input[] = {"-A INPUT -j DOS_PROTECT", "-A INPUT -j INPUT_FIREWALL", "-A INPUT -j DEFAULT_INPUT"};
    const char *rules[] = {"-A INPUT_FIREWALL -i lo -j ACCEPT",
        "-A INPUT_FIREWALL -m state --state RELATED,ESTABLISHED -j ACCEPT",
        "-A INPUT_FIREWALL -p tcp -m tcp --dport 3493 -j DROP"};
    int table = 0, commit = 0, inputs = 0, firewall = 0, mismatch = 0, declarations = 0;
    if (settings_tool(NUT_US3000_SETTINGS_SAVE, args, data, sizeof(data)) != 0) return SETTING_UNKNOWN;
    for (char *line = strtok_r(data, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        if (*line == '#') continue;
        if (!strcmp(line, "*filter") && !table && !commit) { table = 1; continue; }
        if (!strcmp(line, "COMMIT") && table && !commit) { commit = 1; continue; }
        if (!table || commit) return SETTING_UNKNOWN;
        if (!strncmp(line, ":INPUT ", 7)) declarations |= 1;
        if (!strncmp(line, ":INPUT_FIREWALL ", 16)) declarations |= 2;
        if (!strncmp(line, ":DOS_PROTECT ", 13)) declarations |= 4;
        if (!strncmp(line, "-A INPUT ", 9)) {
            if (inputs >= 3 || strcmp(line, input[inputs++])) return SETTING_UNKNOWN;
        } else if (!strncmp(line, "-A DOS_PROTECT ", 15)) {
            char *jump = strstr(line, " -j ");
            if (!jump || (strcmp(jump, " -j RETURN") && strcmp(jump, " -j DROP")) ||
                strstr(line, " -g ")) return SETTING_UNKNOWN;
        } else if (!strncmp(line, "-A INPUT_FIREWALL ", 18)) {
            if (firewall < 3 && strcmp(line, rules[firewall])) mismatch = 1;
            firewall++;
        } else if (*line != ':' && strncmp(line, "-A ", 3)) return SETTING_UNKNOWN;
    }
    if (!commit || inputs != 3 || declarations != 7) return SETTING_UNKNOWN;
    return firewall < 3 || mismatch ? SETTING_RED : SETTING_GREEN;
}

#define SETTINGS_PROFILES 16
static enum setting_result firewall_settings(int root)
{
    /* jq handles JSON, never shell. All filenames are numeric directory entries;
       pre-opened safe descriptors prevent symlink/path substitution by JSON. */
    static const char filter[] =
        "def unknown: 2; $ARGS.named | to_entries | sort_by(.key) | map(.value|fromjson) | .[0] as $s | "
        "if ($s|type)!=\"object\" or ($s.status|type)!=\"boolean\" or ($s.profile|type)!=\"string\" then unknown "
        "elif $s.status==false then 0 else "
        "[.[1:][] | select(.name==$s.profile)] as $p | "
        "if ($p|length)!=1 then unknown else $p[0] | "
        "if (.rules|type)!=\"object\" or (.rules|keys)!=[\"global\"] or "
        "(.rules.global|type)!=\"array\" or .adapterPolicyMap!={\"global\":2} then unknown else "
        "if any(.rules.global[]; (.enable|type)!=\"boolean\") then unknown else "
        "[.rules.global[] | select(.enable)] | if length==0 then 0 else .[0] | "
        "if (keys)!=([\"adapterDirect\",\"blLog\",\"chainList\",\"enable\",\"ipDirect\",\"ipGroup\",\"ipList\",\"ipType\","
        "\"labelList\",\"name\",\"policy\",\"portDirect\",\"portGroup\",\"portList\",\"protocol\",\"ruleIndex\",\"table\"]|sort) or "
        "(.blLog|type)!=\"boolean\" or .labelList!=[] or (.name|type)!=\"string\" or (.ruleIndex|type)!=\"number\" or "
        ".adapterDirect!=1 or .chainList!=[\"FORWARD_FIREWALL\",\"INPUT_FIREWALL\"] or "
        ".ipDirect!=1 or .ipGroup!=5 or .ipList!=[] or .ipType!=2 or "
        ".portDirect!=0 or .portGroup!=1 or .protocol!=1 or .table!=\"filter\" or "
        "(.policy!=0 and .policy!=1) or (.portList|type)!=\"array\" then unknown "
        "elif .policy==1 and .portList==[\"3493\"] then 1 else 0 end end end end end end";
    int dir = -1, count = 0, fds[SETTINGS_PROFILES + 1];
    char names[SETTINGS_PROFILES + 1][NAME_MAX + 1], refs[SETTINGS_PROFILES + 1][32];
    char variables[SETTINGS_PROFILES + 1][8];
    char *snapshots[SETTINGS_PROFILES + 1] = {0};
    struct stat stats[SETTINGS_PROFILES + 1];
    char *args[3 * (SETTINGS_PROFILES + 1) + 4];
    char output[32];
    DIR *listing = NULL;
    enum setting_result result = SETTING_UNKNOWN;
    dir = openat(root, "firewall.d", O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (!info_safe_dir(dir)) goto done;
    listing = fdopendir(dup(dir));
    if (!listing) goto done;
    strcpy(names[count++], "firewall_settings.json");
    struct dirent *entry;
    errno = 0;
    while ((entry = readdir(listing)) != NULL) {
        size_t digits = strspn(entry->d_name, "0123456789");
        if (!digits || strcmp(entry->d_name + digits, ".json")) continue;
        if (count == SETTINGS_PROFILES + 1) goto done;
        strcpy(names[count++], entry->d_name);
    }
    if (errno) goto done;
    args[0] = (char *)NUT_US3000_SETTINGS_JQ; args[1] = "-n"; args[2] = (char *)filter;
    for (int i = 0; i < count; i++) fds[i] = -1;
    for (int i = 0; i < count; i++) {
        snapshots[i] = malloc(INFO_LIMIT + 2);
        if (!snapshots[i]) goto close_files;
        fds[i] = openat(dir, names[i], O_RDONLY | O_NONBLOCK | O_NOFOLLOW);
        if (info_read(fds[i], snapshots[i], &stats[i]) != 0 || lseek(fds[i], 0, SEEK_SET) != 0) goto close_files;
        snprintf(refs[i], sizeof(refs[i]), "/dev/fd/%d", fds[i]);
        snprintf(variables[i], sizeof(variables[i]), "f%02d", i);
        args[3 + 3*i] = "--rawfile";
        args[4 + 3*i] = variables[i];
        args[5 + 3*i] = refs[i];
    }
    args[3 + 3*count] = NULL;
    if (settings_tool(NUT_US3000_SETTINGS_JQ, args, output, sizeof(output)) != 0) goto close_files;
    if (!strcmp(output, "0\n")) result = SETTING_RED;
    else if (!strcmp(output, "1\n")) result = firewall_effective();
    for (int i = 0; i < count; i++) {
        if (!settings_unchanged(dir, names[i], fds[i], snapshots[i], &stats[i])) result = SETTING_UNKNOWN;
    }
    /* A new/deleted profile can make the active-name match ambiguous. */
    rewinddir(listing);
    int profiles = 0;
    errno = 0;
    while ((entry = readdir(listing)) != NULL) {
        size_t digits = strspn(entry->d_name, "0123456789");
        if (digits && !strcmp(entry->d_name + digits, ".json")) profiles++;
    }
    if (errno || profiles != count - 1 || !settings_dir_unchanged(root, "firewall.d", dir)) result = SETTING_UNKNOWN;
close_files:
    for (int i = 0; i < count; i++) {
        if (fds[i] >= 0) close(fds[i]);
        free(snapshots[i]);
    }
done:
    if (listing) closedir(listing);
    if (dir >= 0) close(dir);
    return result;
}

static int publish_description(size_t state)
{
    int root = -1, packages = -1, dir = -1, source = -1, check = -1, out = -1;
    int result = -1, temp_created = 0, signals_blocked = 0;
    char original[INFO_LIMIT + 2], current[INFO_LIMIT + 2], timestamp[32];
    const char *tmp = ".INFO-nut-us3000-status.tmp";
    struct stat before, after, dir_before, dir_after;
    size_t begin[2] = {0, 0}, end[2] = {0, 0}, counts[2] = {0, 0};
    int package_count = 0;
    FILE *stream = NULL;
    time_t now = time(NULL);
    struct tm utc;
    sigset_t signals, previous_signals;
    enum setting_result ups = SETTING_UNKNOWN, firewall = SETTING_UNKNOWN;

    root = open(NUT_US3000_INFO_ROOT, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (!info_safe_dir(root)) goto done;
    packages = openat(root, "packages", O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (!info_safe_dir(packages)) goto done;
    dir = openat(packages, "nut-us3000", O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (!info_safe_dir(dir) || flock(dir, LOCK_EX | LOCK_NB) != 0 ||
        fstat(dir, &dir_before) != 0) goto done;
    source = openat(dir, "INFO", O_RDONLY | O_NONBLOCK | O_NOFOLLOW);
    if (info_read(source, original, &before) != 0) goto done;
    /* Line-oriented DSM format, not shell. Reject ambiguous description fields. */
    for (size_t pos = 0; pos < (size_t)before.st_size;) {
        char *nl = strchr(original + pos, '\n');
        size_t stop = nl ? (size_t)(nl - original) : (size_t)before.st_size;
        const char *line = original + pos, *trimmed = line;
        while (*trimmed == ' ' || *trimmed == '\t') trimmed++;
        if (!strncmp(trimmed, "package=", 8)) {
            if (trimmed != line || stop - pos != 20 ||
                memcmp(line, "package=\"nut-us3000\"", 20) != 0) goto done;
            package_count++;
        }
        const char *keys[] = {"description=", "description_rus="};
        for (size_t i = 0; i < 2; i++) {
            size_t keylen = strlen(keys[i]);
            if (strncmp(trimmed, keys[i], keylen) != 0) continue;
            if (trimmed != line || stop - pos < keylen + 2 || line[keylen] != '"' ||
                original[stop - 1] != '"' || memchr(line, '\r', stop - pos)) goto done;
            begin[i] = pos;
            end[i] = stop;
            counts[i]++;
        }
        pos = stop + (nl != NULL);
    }
    if (package_count != 1 || counts[0] != 1 || counts[1] != 1 ||
        now == (time_t)-1 || !gmtime_r(&now, &utc) ||
        !strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S UTC", &utc)) goto done;

    int settings = open(NUT_US3000_SETTINGS_ROOT, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (info_safe_dir(settings)) {
        ups = ups_settings(settings);
        firewall = firewall_settings(settings);
    }
    if (settings >= 0) close(settings);

    /* Defer normal termination only over the bounded regular-file transaction.
       SIGKILL/crash can leave one fixed temp file: refuse it, never truncate it. */
    sigemptyset(&signals);
    sigaddset(&signals, SIGTERM); sigaddset(&signals, SIGINT); sigaddset(&signals, SIGHUP);
    if (sigprocmask(SIG_BLOCK, &signals, &previous_signals) != 0) goto done;
    signals_blocked = 1;
    out = openat(dir, tmp, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (out < 0) goto done;
    temp_created = 1;
    stream = fdopen(out, "w");
    if (!stream) goto done;
    for (size_t pos = 0; pos < (size_t)before.st_size;) {
        if (pos == begin[0]) {
            if (fprintf(stream, "description=\"◆ STATUS: %s · Checked: %s ◆ NOTE: if older than 10 minutes, state is unconfirmed. Running means controller active, not confirmed protection. ◆ DSM SETUP: %s · Synology UPS server · IP 10.255.255.1 · Delay 5 minutes ◆ FIREWALL: %s · deny external TCP 3493 before allow rules · persistent profile and applied order; no external connection test ◆ HELP: NUT US3000 in DSM main menu\"",
                        description_states[state].english, timestamp, setting_en[ups], setting_en[firewall]) < 0) goto done;
            pos = end[0];
        } else if (pos == begin[1]) {
            if (fprintf(stream, "description_rus=\"◆ СОСТОЯНИЕ: %s · Проверено: %s ◆ ВАЖНО: если проверка старше 10 минут, состояние не подтверждено. Выполняется — контроллер активен, не гарантия защиты. ◆ НАСТРОЙКА DSM: %s · Сервер ИБП Synology · IP 10.255.255.1 · Задержка 5 минут ◆ БРАНДМАУЭР: %s · запретить внешний TCP 3493 выше разрешающих правил · постоянный профиль и применённый порядок; без внешнего теста подключения ◆ СПРАВКА: NUT US3000 в главном меню DSM\"",
                        description_states[state].russian, timestamp, setting_ru[ups], setting_ru[firewall]) < 0) goto done;
            pos = end[1];
        } else {
            if (fputc((unsigned char)original[pos++], stream) == EOF) goto done;
        }
    }
    if (fflush(stream) != 0 || fchown(out, before.st_uid, before.st_gid) != 0 ||
        fchmod(out, before.st_mode & 0777) != 0 || fsync(out) != 0) goto done;
    check = openat(dir, "INFO", O_RDONLY | O_NONBLOCK | O_NOFOLLOW);
    if (info_read(check, current, &after) != 0 || after.st_ino != before.st_ino ||
        after.st_dev != before.st_dev || after.st_size != before.st_size ||
        after.st_uid != before.st_uid || after.st_gid != before.st_gid ||
        after.st_mode != before.st_mode || memcmp(original, current, (size_t)before.st_size) ||
        fstatat(packages, "nut-us3000", &dir_after, AT_SYMLINK_NOFOLLOW) != 0 ||
        dir_before.st_ino != dir_after.st_ino || dir_before.st_dev != dir_after.st_dev ||
        !S_ISDIR(dir_after.st_mode)) goto done;
    if (renameat(dir, tmp, dir, "INFO") != 0) goto done;
    temp_created = 0;
    result = 0;
done:
    if (stream) (void)fclose(stream);
    else if (out >= 0) (void)close(out);
    if (temp_created) (void)unlinkat(dir, tmp, 0);
    if (check >= 0) (void)close(check);
    if (source >= 0) (void)close(source);
    if (dir >= 0) (void)close(dir);
    if (packages >= 0) (void)close(packages);
    if (root >= 0) (void)close(root);
    if (signals_blocked) (void)sigprocmask(SIG_SETMASK, &previous_signals, NULL);
    return result;
}

int main(int argc, char **argv)
{
    int result;
    enum {
        COMMAND_PRIVILEGE,
        COMMAND_ENSURE,
        COMMAND_AUDIT,
        COMMAND_RELEASE,
        COMMAND_RETIRE_PORT_CONFIG
    } command;

    if (argc != 2) {
        return 64;
    }
    for (size_t i = 0; i < sizeof(description_states) / sizeof(description_states[0]); i++) {
        if (strcmp(argv[1], description_states[i].command) != 0) continue;
        if (normalize_root_identity() != 0) return 77;
        return publish_description(i) == 0 ? 0 : 1;
    }
    if (strcmp(argv[1], "privilege") == 0) {
        command = COMMAND_PRIVILEGE;
    } else if (strcmp(argv[1], "ensure") == 0) {
        command = COMMAND_ENSURE;
    } else if (strcmp(argv[1], "audit") == 0) {
        command = COMMAND_AUDIT;
    } else if (strcmp(argv[1], "release") == 0) {
        command = COMMAND_RELEASE;
    } else if (strcmp(argv[1], "retire-port-config") == 0) {
        command = COMMAND_RETIRE_PORT_CONFIG;
    } else {
        return 64;
    }
    if (normalize_root_identity() != 0) {
        error_message("native host integration requires the declared root tool privilege");
        return 77;
    }
    if (command == COMMAND_PRIVILEGE) {
        (void)fputs("HOSTCTL_PRIVILEGE_OK\n", stdout);
        return 0;
    }
    if (command == COMMAND_ENSURE) {
        result = ensure_network();
        if (result == 0) result = usb_access(1);
    } else if (command == COMMAND_AUDIT) {
        result = audit_network();
    } else if (command == COMMAND_RETIRE_PORT_CONFIG) {
        result = retire_port_config();
    } else {
        result = release_host();
    }
    if (result != 0) {
        error_message("native host integration failed");
        return 1;
    }
    return 0;
}
