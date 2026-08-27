/*
 * Copyright (C) 2026 Hevtech
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
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
    if (safe_path(path, sizeof(path), directory, name) != 0 ||
        read_attribute(path, value, sizeof(value)) != 0) {
        return -1;
    }
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

static int restore_usb(void)
{
    DIR *directory = opendir(NUT_US3000_SYSFS_DEVICES);
    struct dirent *entry;
    char device_name[NAME_MAX + 1] = "";
    char device_path[PATH_MAX];
    char interface_name[NAME_MAX + 1] = "";
    char interface_path[PATH_MAX];
    int matching_devices = 0;
    int matching_interfaces = 0;
    int result = -1;

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
        return 0;
    }
    if (matching_devices != 1 ||
        safe_path(device_path, sizeof(device_path), NUT_US3000_SYSFS_DEVICES, device_name) != 0 ||
        exact_attribute(device_path, "serial", TARGET_SERIAL) != 0) {
        return -1;
    }

    directory = opendir(NUT_US3000_SYSFS_DEVICES);
    if (directory == NULL) {
        return -1;
    }
    while ((entry = readdir(directory)) != NULL) {
        char number_path[PATH_MAX];
        char number[128];
        size_t prefix = strlen(device_name);
        if (strncmp(entry->d_name, device_name, prefix) != 0 || entry->d_name[prefix] != ':' ||
            safe_path(interface_path, sizeof(interface_path), NUT_US3000_SYSFS_DEVICES, entry->d_name) != 0 ||
            safe_path(number_path, sizeof(number_path), interface_path, "bInterfaceNumber") != 0) {
            continue;
        }
        if (read_attribute(number_path, number, sizeof(number)) != 0) {
            goto finish;
        }
        ++matching_interfaces;
        if (strcmp(number, TARGET_INTERFACE_NUMBER) != 0) {
            goto finish;
        }
        (void)strncpy(interface_name, entry->d_name, sizeof(interface_name) - 1);
        interface_name[sizeof(interface_name) - 1] = '\0';
    }
    (void)closedir(directory);
    directory = NULL;
    if (matching_interfaces != 1 || interface_name[0] == '\0' ||
        safe_path(interface_path, sizeof(interface_path), NUT_US3000_SYSFS_DEVICES, interface_name) != 0) {
        return -1;
    }
    result = driver_state(interface_path);
    if (result == 1) {
        return 0;
    }
    if (result != 0) {
        return -1;
    }
    {
        int descriptor = open(NUT_US3000_USBHID_BIND, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
        size_t length = strlen(interface_name);
        if (descriptor < 0 || write(descriptor, interface_name, length) != (ssize_t)length) {
            if (descriptor >= 0) {
                (void)close(descriptor);
            }
            return -1;
        }
        (void)close(descriptor);
    }
    for (int attempt = 0; attempt < 30; ++attempt) {
        struct timespec pause = {0, 100000000L};
        result = driver_state(interface_path);
        if (result == 1) {
            return 0;
        }
        if (result < 0) {
            return -1;
        }
        (void)nanosleep(&pause, NULL);
    }
    return -1;

finish:
    if (directory != NULL) {
        (void)closedir(directory);
    }
    return -1;
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
    if (guard_remove() != 0) {
        failed = 1;
    }
    if (alias_remove() != 0) {
        failed = 1;
    }
    return failed ? -1 : 0;
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
