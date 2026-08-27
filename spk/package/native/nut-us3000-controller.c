/*
 * Copyright (C) 2026 Hevtech
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include <errno.h>
#include <signal.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef NUT_US3000_STEP_PATH
#define NUT_US3000_STEP_PATH "/var/packages/nut-us3000/target/share/nut-us3000/retry-step.sh"
#endif

#ifndef NUT_US3000_PKGDEST
#define NUT_US3000_PKGDEST "/var/packages/nut-us3000/target"
#endif

#ifndef NUT_US3000_PKGVAR
#define NUT_US3000_PKGVAR "/var/packages/nut-us3000/var"
#endif

#ifndef NUT_US3000_INTERVAL_SECONDS
#define NUT_US3000_INTERVAL_SECONDS 300
#endif

static volatile sig_atomic_t stop_requested = 0;

static void request_stop(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static int parse_delay(const char *text, unsigned int *delay)
{
    unsigned long value;
    char *end = NULL;
    const char *cursor;

    if (text == NULL || *text == '\0') {
        return -1;
    }
    for (cursor = text; *cursor != '\0'; ++cursor) {
        if (*cursor < '0' || *cursor > '9') {
            return -1;
        }
    }
    errno = 0;
    value = strtoul(text, &end, 10);
    if (errno != 0 || end == NULL || *end != '\0' || value > 600UL) {
        return -1;
    }
    *delay = (unsigned int)value;
    return 0;
}

static int validate_identity_and_step(void)
{
    struct stat metadata;
    uid_t real_uid = getuid();
    uid_t effective_uid = geteuid();
    gid_t real_gid = getgid();
    gid_t effective_gid = getegid();

    if (real_uid == 0 || effective_uid == 0 || real_uid != effective_uid ||
        real_gid != effective_gid) {
        return -1;
    }
    if (lstat(NUT_US3000_STEP_PATH, &metadata) != 0 ||
        !S_ISREG(metadata.st_mode) || metadata.st_uid != real_uid ||
        metadata.st_gid != real_gid ||
        (metadata.st_mode & 07777) != 0755) {
        return -1;
    }
    return 0;
}

static int wait_seconds(unsigned int seconds)
{
    struct timespec request;
    struct timespec remainder;

    request.tv_sec = (time_t)seconds;
    request.tv_nsec = 0;
    while (!stop_requested && nanosleep(&request, &remainder) != 0) {
        if (errno != EINTR) {
            return -1;
        }
        request = remainder;
    }
    return stop_requested ? 1 : 0;
}

static int run_step(void)
{
    pid_t child;
    pid_t waited;
    int status;
    char *const argv[] = {(char *)NUT_US3000_STEP_PATH, NULL};
    char *const environment[] = {
        (char *)"PATH=/bin:/usr/bin",
        (char *)"SYNOPKG_PKGDEST=" NUT_US3000_PKGDEST,
        (char *)"SYNOPKG_PKGVAR=" NUT_US3000_PKGVAR,
        NULL,
    };

    child = fork();
    if (child < 0) {
        return -1;
    }
    if (child == 0) {
        struct sigaction action;
        (void)memset(&action, 0, sizeof(action));
        action.sa_handler = SIG_DFL;
        (void)sigemptyset(&action.sa_mask);
        (void)sigaction(SIGTERM, &action, NULL);
        (void)sigaction(SIGINT, &action, NULL);
        (void)execve(NUT_US3000_STEP_PATH, argv, environment);
        _exit(127);
    }

    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    if (waited != child || !WIFEXITED(status)) {
        return -1;
    }
    if (WEXITSTATUS(status) == 0 || WEXITSTATUS(status) == 75) {
        return 0;
    }
    return -1;
}

int main(int argc, char **argv)
{
    struct sigaction action;
    unsigned int first_delay;
    int wait_result;

    if (argc != 3 || strcmp(argv[1], "--first-delay") != 0 ||
        parse_delay(argv[2], &first_delay) != 0) {
        return 64;
    }
    if (validate_identity_and_step() != 0) {
        return 77;
    }

    (void)memset(&action, 0, sizeof(action));
    action.sa_handler = request_stop;
    (void)sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) != 0 ||
        sigaction(SIGINT, &action, NULL) != 0) {
        return 1;
    }

    wait_result = wait_seconds(first_delay);
    if (wait_result < 0) {
        return 1;
    }
    if (wait_result > 0) {
        return 0;
    }

    for (;;) {
        if (run_step() != 0) {
            return 1;
        }
        if (stop_requested) {
            return 0;
        }
        wait_result = wait_seconds(NUT_US3000_INTERVAL_SECONDS);
        if (wait_result < 0) {
            return 1;
        }
        if (wait_result > 0) {
            return 0;
        }
    }
}
