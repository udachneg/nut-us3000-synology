#!/usr/bin/python3
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import tempfile


HOOKS = ("preinst", "postinst", "preuninst", "postuninst", "preupgrade", "postupgrade")
RUNTIME_RPATH = "/var/packages/nut-us3000/target/lib"
ELF_PATHS = (
    "bin/upsc",
    "lib/libupsclient.so.7.1.0",
    "lib/libusb-1.0.so.0.5.0",
    "libexec/nut/nut-us3000-controller",
    "libexec/nut/nut-us3000-hostctl",
    "libexec/nut/usbhid-ups",
    "sbin/upsd",
    "sbin/upsdrvctl",
)
EXPECTED_NEEDED = {
    "bin/upsc": {"libupsclient.so.7", "libc.so.6"},
    "lib/libupsclient.so.7.1.0": {"libc.so.6"},
    "lib/libusb-1.0.so.0.5.0": {"libc.so.6", "ld-linux-x86-64.so.2"},
    "libexec/nut/nut-us3000-controller": {"libc.so.6"},
    "libexec/nut/nut-us3000-hostctl": {"libc.so.6"},
    "libexec/nut/usbhid-ups": {"libusb-1.0.so.0", "libm.so.6", "libc.so.6"},
    "sbin/upsd": {"libc.so.6"},
    "sbin/upsdrvctl": {"libc.so.6"},
}


class AuditError(Exception):
    pass


def reject(message):
    raise AuditError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical_directory(raw):
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        reject("directory argument is unsafe")
    resolved = path.resolve(strict=True)
    if str(resolved) != str(path):
        reject("directory argument is not canonical")
    return path


def canonical_file(raw, executable=False):
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        reject("file argument is unsafe")
    resolved = path.resolve(strict=True)
    if str(resolved) != str(path):
        reject("file argument is not canonical")
    if executable and not os.access(path, os.X_OK):
        reject("tool is not executable")
    return path


def normalize_member_name(raw):
    if not raw or "\0" in raw or raw.startswith("/"):
        reject("archive member name is unsafe")
    while raw.startswith("./"):
        raw = raw[2:]
    raw = raw.rstrip("/")
    if not raw:
        reject("archive contains an empty root member")
    path = PurePosixPath(raw)
    if any(part in ("", ".", "..") for part in path.parts):
        reject("archive member name is unsafe")
    return str(path)


def read_archive(fileobj, mode, allow_links):
    entries = {}
    try:
        with tarfile.open(fileobj=fileobj, mode=mode) as archive:
            for member in archive.getmembers():
                name = normalize_member_name(member.name)
                if name in entries:
                    reject("archive has duplicate normalized members")
                item = {"mode": member.mode & 0o7777}
                if member.isdir():
                    item["type"] = "dir"
                elif member.isfile():
                    stream = archive.extractfile(member)
                    if stream is None:
                        reject("archive regular file cannot be read")
                    item["type"] = "file"
                    item["data"] = stream.read()
                elif allow_links and member.issym():
                    target = member.linkname
                    if not target or target.startswith("/") or "/" in target or target in (".", ".."):
                        reject("archive symlink target is unsafe")
                    item["type"] = "link"
                    item["target"] = target
                else:
                    reject("archive member type is forbidden")
                entries[name] = item
    except (tarfile.TarError, OSError) as error:
        reject(f"archive cannot be read: {error}")
    return entries


def expected_outer():
    result = {
        "INFO": ("file", 0o644),
        "LICENSE": ("file", 0o644),
        "PACKAGE_ICON.PNG": ("file", 0o644),
        "PACKAGE_ICON_256.PNG": ("file", 0o644),
        "WIZARD_UIFILES": ("dir", 0o755),
        "conf": ("dir", 0o755),
        "conf/privilege": ("file", 0o644),
        "conf/resource": ("file", 0o644),
        "package.tgz": ("file", 0o644),
        "scripts": ("dir", 0o755),
        "scripts/functions": ("file", 0o755),
        "scripts/installer": ("file", 0o755),
        "scripts/service-setup": ("file", 0o644),
        "scripts/start-stop-status": ("file", 0o755),
    }
    for name in (
        "install_uifile", "install_uifile_rus",
        "upgrade_uifile", "upgrade_uifile_rus",
        "uninstall_uifile", "uninstall_uifile_rus",
    ):
        result[f"WIZARD_UIFILES/{name}"] = ("file", 0o644)
    for name in HOOKS:
        result[f"scripts/{name}"] = ("file", 0o755)
    return result


def expected_payload():
    result = {}
    for name in (
        "app", "app/help", "app/help/enu", "app/help/rus", "app/texts",
        "app/texts/enu", "app/texts/rus", "bin", "lib", "libexec",
        "libexec/nut", "sbin", "share",
        "share/nut-us3000", "share/nut-us3000/templates",
    ):
        result[name] = ("dir", 0o755)
    for name in ("bin/upsc", "libexec/nut/usbhid-ups", "sbin/upsd", "sbin/upsdrvctl"):
        result[name] = ("file", 0o755)
    result["libexec/nut/nut-us3000-hostctl"] = ("file", 0o750)
    result["libexec/nut/nut-us3000-controller"] = ("file", 0o750)
    for name in ("lib/libupsclient.so.7.1.0", "lib/libusb-1.0.so.0.5.0"):
        result[name] = ("file", 0o644)
    for name in ("lib/libupsclient.so.7", "lib/libusb-1.0.so.0"):
        result[name] = ("link", 0o777)
    for name in ("share/nut-us3000/templates/ups.conf", "share/nut-us3000/templates/upsd.conf"):
        result[name] = ("file", 0o644)
    for name in (
        "share/nut-us3000/lib.sh",
        "share/nut-us3000/healthcheck.sh",
        "share/nut-us3000/retry-step.sh",
    ):
        result[name] = ("file", 0o755)
    for name in (
        "app/helptoc.conf",
        "app/help/enu/nut-us3000.html",
        "app/help/rus/nut-us3000.html",
        "app/texts/enu/strings",
        "app/texts/rus/strings",
    ):
        result[name] = ("file", 0o644)
    return result


def require_topology(entries, expected, label):
    if set(entries) != set(expected):
        missing = sorted(set(expected) - set(entries))
        extra = sorted(set(entries) - set(expected))
        reject(f"{label} topology mismatch: missing={missing} extra={extra}")
    for name, (kind, mode) in expected.items():
        item = entries[name]
        if item["type"] != kind or item["mode"] != mode:
            reject(f"{label} metadata mismatch: {name}")


def require_bytes(entries, member, source):
    if entries[member]["data"] != source.read_bytes():
        reject(f"packaged bytes differ from canonical source: {member}")


def parse_info(data, package_digest):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        reject("INFO is not UTF-8")
    if not text.endswith("\n"):
        reject("INFO has no final LF")
    fields = {}
    pattern = re.compile(r'^([a-z_]+)="([^"\n]*)"$')
    for line in text.splitlines():
        if not line:
            continue
        match = pattern.fullmatch(line)
        if not match or match.group(1) in fields:
            reject("INFO syntax is malformed")
        fields[match.group(1)] = match.group(2)
    expected = {
        "package": "nut-us3000",
        "version": "2.8.5-0016",
        "description": "Native USB driver and host-local NUT 2.8.5 endpoint for UGREEN US3000.",
        "description_rus": "Нативный USB-драйвер и локальный NUT 2.8.5 для UGREEN US3000.",
        "arch": "epyc7002",
        "maintainer": "Hevtech",
        "maintainer_url": "https://github.com/udachneg/nut-us3000-synology",
        "distributor": "",
        "distributor_url": "",
        "os_min_ver": "7.2.2-72806",
        "helpurl": "https://github.com/udachneg/nut-us3000-synology",
        "displayname": "NUT US3000",
        "dsmuidir": "app",
        "dsmappname": "com.synocommunity.packages.nut-us3000",
        "support_conf_folder": "yes",
        "checksum": package_digest,
    }
    if fields != expected:
        reject("INFO values do not match the exact package contract")
    return fields


def parse_privilege(data):
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        reject("privilege config is not valid JSON")
    expected = {
        "defaults": {"run-as": "package"},
        "username": "nutus3000",
        "groupname": "nutus3000",
        "tool": [
            {
                "relpath": "libexec/nut/usbhid-ups",
                "user": "package",
                "group": "package",
                "permission": "0750",
            },
            {
                "relpath": "libexec/nut/nut-us3000-hostctl",
                "user": "root",
                "group": "package",
                "permission": "6550",
            },
            {
                "relpath": "libexec/nut/nut-us3000-controller",
                "user": "package",
                "group": "package",
                "permission": "0750",
            },
        ],
    }
    if value != expected:
        reject("privilege values do not match the exact package contract")
    return value


def parse_elf(readelf, path, relative):
    completed = subprocess.run(
        [str(readelf), "-h", "-l", "-d", "--", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or completed.stderr:
        reject(f"readelf failed for {relative}")
    output = completed.stdout
    required = (
        (r"^\s*Class:\s+ELF64\s*$", "ELF class"),
        (r"^\s*Data:\s+2's complement, little endian\s*$", "ELF data order"),
        (r"^\s*Machine:\s+Advanced Micro Devices X86-64\s*$", "ELF machine"),
    )
    for pattern, label in required:
        if not re.search(pattern, output, re.MULTILINE):
            reject(f"unexpected {label}: {relative}")
    needed = set(re.findall(r"\(NEEDED\).*Shared library: \[([^]]+)\]", output))
    if needed != EXPECTED_NEEDED[relative]:
        reject(f"unexpected NEEDED set: {relative}")
    rpaths = re.findall(r"\((?:RPATH|RUNPATH)\).*Library (?:rpath|runpath): \[([^]]+)\]", output)
    expected_rpaths = [] if relative in (
        "libexec/nut/nut-us3000-controller",
        "libexec/nut/nut-us3000-hostctl",
    ) else [RUNTIME_RPATH]
    if rpaths != expected_rpaths:
        reject(f"unexpected RPATH/RUNPATH: {relative}")
    interpreter_matches = re.findall(r"Requesting program interpreter: ([^]]+)\]", output)
    if relative.startswith("lib/"):
        if interpreter_matches:
            reject(f"shared library has an interpreter: {relative}")
    elif interpreter_matches != ["/lib64/ld-linux-x86-64.so.2"]:
        reject(f"unexpected ELF interpreter: {relative}")
    sonames = re.findall(r"\(SONAME\).*Library soname: \[([^]]+)\]", output)
    expected_soname = {
        "lib/libupsclient.so.7.1.0": ["libupsclient.so.7"],
        "lib/libusb-1.0.so.0.5.0": ["libusb-1.0.so.0"],
    }.get(relative, [])
    if sonames != expected_soname:
        reject(f"unexpected SONAME: {relative}")
    return sorted(needed)


def build_manifest(outer, payload, info, privilege, elf_metadata):
    lines = [
        "FORMAT=NUT_US3000_SPK_AUDIT_V2",
        "INFO_PACKAGE=" + info["package"],
        "INFO_VERSION=" + info["version"],
        "INFO_ARCH=" + info["arch"],
        "INFO_OS_MIN_VER=" + info["os_min_ver"],
        "INFO_OS_MAX_VER=" + info.get("os_max_ver", "NONE"),
        "INFO_CHECKSUM_VALID=yes",
        "PRIVILEGE_DEFAULT_RUN_AS=" + privilege["defaults"]["run-as"],
        f"CONTROLLER_ARCHIVE_MODE={payload['libexec/nut/nut-us3000-controller']['mode']:04o}",
        "CONTROLLER_INSTALL_USER=" + privilege["tool"][2]["user"],
        "CONTROLLER_INSTALL_GROUP=" + privilege["tool"][2]["group"],
        "CONTROLLER_INSTALL_PERMISSION=" + privilege["tool"][2]["permission"],
        f"HOSTCTL_ARCHIVE_MODE={payload['libexec/nut/nut-us3000-hostctl']['mode']:04o}",
        "HOSTCTL_INSTALL_USER=" + privilege["tool"][1]["user"],
        "HOSTCTL_INSTALL_GROUP=" + privilege["tool"][1]["group"],
        "HOSTCTL_INSTALL_PERMISSION=" + privilege["tool"][1]["permission"],
        "HOSTCTL_CAPABILITIES=NONE",
        "ARDUINO_SUBDRIVER=Arduino HID 0.22",
    ]
    outer_files = sorted(name for name, item in outer.items() if item["type"] == "file" and name not in ("INFO", "package.tgz"))
    lines.append(f"OUTER_NORMALIZED_FILE_COUNT={len(outer_files)}")
    for index, name in enumerate(outer_files):
        lines.append(f"OUTER_{index:03d}_PATH={name}")
        lines.append(f"OUTER_{index:03d}_MODE={outer[name]['mode']:04o}")
        lines.append(f"OUTER_{index:03d}_SHA256={sha256(outer[name]['data'])}")
    leaves = sorted(name for name, item in payload.items() if item["type"] != "dir")
    lines.append(f"PAYLOAD_FILE_COUNT={len(leaves)}")
    for index, name in enumerate(leaves):
        item = payload[name]
        lines.append(f"PAYLOAD_{index:03d}_PATH={name}")
        lines.append(f"PAYLOAD_{index:03d}_TYPE={item['type']}")
        lines.append(f"PAYLOAD_{index:03d}_MODE={item['mode']:04o}")
        if item["type"] == "file":
            lines.append(f"PAYLOAD_{index:03d}_SHA256={sha256(item['data'])}")
        else:
            lines.append(f"PAYLOAD_{index:03d}_TARGET={item['target']}")
    lines.append(f"ELF_COUNT={len(ELF_PATHS)}")
    for index, name in enumerate(ELF_PATHS):
        needed = elf_metadata[name]
        lines.append(f"ELF_{index:03d}_PATH={name}")
        rpath = "NONE" if name in (
            "libexec/nut/nut-us3000-controller",
            "libexec/nut/nut-us3000-hostctl",
        ) else RUNTIME_RPATH
        lines.append(f"ELF_{index:03d}_RPATH={rpath}")
        lines.append(f"ELF_{index:03d}_NEEDED={','.join(needed)}")
    lines.append("END=NUT_US3000_SPK_AUDIT_V2")
    return ("\n".join(lines) + "\n").encode("utf-8")


def main(argv):
    if len(argv) != 5:
        return 64
    project_root = canonical_directory(argv[1])
    spk = canonical_file(argv[2])
    readelf = canonical_file(argv[3], executable=True)
    manifest = Path(argv[4])
    if not manifest.is_absolute() or manifest.exists() or manifest.is_symlink():
        return 64
    parent = canonical_directory(str(manifest.parent))
    if manifest.parent != parent:
        return 64

    with spk.open("rb") as stream:
        outer = read_archive(stream, "r:*", allow_links=False)
    require_topology(outer, expected_outer(), "outer SPK")
    package_bytes = outer["package.tgz"]["data"]
    info = parse_info(outer["INFO"]["data"], hashlib.md5(package_bytes).hexdigest())
    if not outer["PACKAGE_ICON.PNG"]["data"].startswith(b"\x89PNG\r\n\x1a\n"):
        reject("small package icon is not PNG")
    if not outer["PACKAGE_ICON_256.PNG"]["data"].startswith(b"\x89PNG\r\n\x1a\n"):
        reject("large package icon is not PNG")
    for name in (
        "install_uifile", "install_uifile_rus",
        "upgrade_uifile", "upgrade_uifile_rus",
        "uninstall_uifile", "uninstall_uifile_rus",
    ):
        try:
            value = json.loads(outer[f"WIZARD_UIFILES/{name}"]["data"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            reject(f"wizard is not valid JSON: {name}")
        if not isinstance(value, list) or not value:
            reject(f"wizard is empty: {name}")
        require_bytes(outer, f"WIZARD_UIFILES/{name}", project_root / "spk/package/wizard" / name)
    try:
        resource = json.loads(outer["conf/resource"]["data"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        reject("resource config is not valid JSON")
    if resource != {} or outer["conf/resource"]["data"] != b"{}\n":
        reject("resource config must be the exact empty spksrc service object")
    privilege = parse_privilege(outer["conf/privilege"]["data"])
    require_bytes(outer, "conf/privilege", project_root / "spk/package/conf/privilege")
    require_bytes(outer, "LICENSE", project_root / "spk/spksrc-overlay/spk/nut-us3000/src/LICENSE")
    require_bytes(outer, "scripts/start-stop-status", project_root / "spk/package/scripts/start-stop-status")
    for name in HOOKS:
        require_bytes(outer, f"scripts/{name}", project_root / "spk/package/scripts" / name)

    payload = read_archive(io.BytesIO(package_bytes), "r:gz", allow_links=True)
    require_topology(payload, expected_payload(), "package payload")
    if payload["lib/libupsclient.so.7"]["target"] != "libupsclient.so.7.1.0":
        reject("libupsclient runtime link is wrong")
    if payload["lib/libusb-1.0.so.0"]["target"] != "libusb-1.0.so.0.5.0":
        reject("libusb runtime link is wrong")
    for relative in (
        "share/nut-us3000/lib.sh",
        "share/nut-us3000/healthcheck.sh",
        "share/nut-us3000/retry-step.sh",
    ):
        require_bytes(payload, relative, project_root / "spk/package/payload" / relative)
    for name in ("ups.conf", "upsd.conf"):
        require_bytes(payload, f"share/nut-us3000/templates/{name}", project_root / "spk/package/templates" / name)
    for relative in (
        "helptoc.conf",
        "help/enu/nut-us3000.html",
        "help/rus/nut-us3000.html",
        "texts/enu/strings",
        "texts/rus/strings",
    ):
        require_bytes(payload, "app/" + relative, project_root / "spk/package/payload/app" / relative)
    if b"Arduino HID 0.22" not in payload["libexec/nut/usbhid-ups"]["data"]:
        reject("Arduino HID 0.22 is absent from usbhid-ups")

    elf_metadata = {}
    with tempfile.TemporaryDirectory(prefix="nut-us3000-spk-inspect-") as temporary:
        root = Path(temporary)
        for relative in ELF_PATHS:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload[relative]["data"])
            destination.chmod(payload[relative]["mode"])
            if not payload[relative]["data"].startswith(b"\x7fELF"):
                reject(f"runtime candidate is not ELF: {relative}")
            elf_metadata[relative] = parse_elf(readelf, destination, relative)

    manifest_bytes = build_manifest(outer, payload, info, privilege, elf_metadata)
    descriptor = os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(manifest_bytes)
    print("SPK_AUDIT_COMPLETE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except AuditError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
