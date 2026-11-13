"""Isolated native GX load check: never creates a GX context or signs in."""

import argparse
import ctypes
from ctypes import wintypes
import json
import multiprocessing
import os
from pathlib import Path
import struct
import sys

DOTNET6_URL = "https://dotnet.microsoft.com/en-us/download/dotnet/6.0"


def clean_environment(root, environment=None):
    """Exclude installed vendor programs and their discovery variables."""
    env = dict(os.environ if environment is None else environment)
    for key in list(env):
        if key.upper().startswith(("GEOSOFT", "GX_", "TERRAWORKBENCH_GX")):
            env.pop(key)
    windows = Path(env.get("SystemRoot", "C:/Windows"))
    env["PATH"] = os.pathsep.join(map(str, (Path(root) / "bin", Path(sys.executable).parent,
                                           windows / "System32", windows)))
    env["TERRAWORKBENCH_GX_REDIST"] = str(Path(root).resolve())
    if __package__:
        from .gx_runtime_setup import dotnet_environment
    else:
        from gx_runtime_setup import dotnet_environment

    target = next((parent for parent in Path(root).parents if parent.name == "_gx_runtime"), None)
    if target is not None:
        env.update(dotnet_environment(target, env))
    env["DOTNET_DISABLE_GUI_ERRORS"] = "1"
    return env


def loaded_modules():
    """Obtain actual mapped module paths, not a guessed DLL search result."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE),
                                        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    array = (wintypes.HMODULE * 2048)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcessModules(kernel.GetCurrentProcess(), array, ctypes.sizeof(array), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    result = []
    for handle in array[:min(len(array), needed.value // ctypes.sizeof(wintypes.HMODULE))]:
        buffer = ctypes.create_unicode_buffer(32768)
        if kernel.GetModuleFileNameW(handle, buffer, len(buffer)):
            result.append(buffer.value)
    return result


def pe_imports(path):
    """Read regular PE import names without adding a Python dependency."""
    data = Path(path).read_bytes()
    if len(data) < 64 or data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 60)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return []
    sections = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    directories = optional + (112 if magic == 0x20B else 96)
    imports_rva = struct.unpack_from("<I", data, directories + 8)[0]
    section_table = optional + optional_size

    def offset(rva):
        for index in range(sections):
            pos = section_table + index * 40
            size, start, raw_size, raw = struct.unpack_from("<IIII", data, pos + 8)
            if start <= rva < start + max(size, raw_size):
                return raw + rva - start
        return rva

    if not imports_rva:
        return []
    pos, result = offset(imports_rva), []
    while pos + 20 <= len(data):
        entry = struct.unpack_from("<IIIII", data, pos)
        if not any(entry):
            break
        start = offset(entry[3])
        end = data.find(b"\0", start, start + 1024)
        if end < 0:
            break
        result.append(data[start:end].decode("ascii", errors="replace"))
        pos += 20
    return result


def missing_imports(root):
    folder = Path(root) / "bin"
    local = {p.name.casefold(): p for p in folder.iterdir() if p.is_file()}
    system = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
    pending, seen, missing = ["geodist.dll"], set(), set()
    while pending:
        name = pending.pop().casefold()
        if name in seen:
            continue
        seen.add(name)
        if name not in local:
            if not name.startswith(("api-ms-", "ext-ms-")) and not (system / name).is_file():
                missing.add(name)
            continue
        pending.extend(pe_imports(local[name]))
    return sorted(missing)


def missing_frameworks(root):
    required = set()
    for config in (Path(root) / "bin").glob("*.runtimeconfig.json"):
        options = json.loads(config.read_text(encoding="utf-8-sig")).get("runtimeOptions", {})
        for item in options.get("frameworks", []) + ([options["framework"]] if "framework" in options else []):
            required.add((item["name"], item["version"].split(".")[0]))
    dotnet_roots = [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "dotnet"]
    for key in ("DOTNET_ROOT", "DOTNET_ROOT_X64"):
        if os.environ.get(key):
            dotnet_roots.insert(0, Path(os.environ[key]))
    return [{"name": name, "major": major} for name, major in sorted(required)
            if not any(any((base / "shared" / name).glob(major + ".*")) for base in dotnet_roots)]


def check_runtime(root):
    """Load the absolute managed DLL and report its mapped path, without GXpy."""
    root = Path(root).resolve()
    result = {"ok": False, "dll": str(root / "bin/geodist.dll"), "loaded_path": None,
              "missing_dlls": [], "missing_frameworks": []}
    try:
        if __package__:
            from .gx_runtime_setup import validate_runtime_configuration
        else:
            from gx_runtime_setup import validate_runtime_configuration
        result["configuration"] = validate_runtime_configuration(root)
    except (OSError, ValueError, UnicodeError) as error:
        result.update(error_code="invalid_redist_configuration", error=str(error))
        return result
    result["missing_frameworks"] = missing_frameworks(root)
    if sys.platform != "win32":
        result["error"] = "Windows is required"
        return result
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    try:
        with os.add_dll_directory(str(root / "bin")):
            library = ctypes.WinDLL(result["dll"], winmode=0x1100)
            modules = loaded_modules()
            actual = next((p for p in modules if Path(p).name.casefold() == "geodist.dll"), None)
            result.update(loaded_path=actual, modules=modules)
            if actual is None or Path(actual).resolve() != Path(result["dll"]).resolve():
                raise OSError("A different geodist.dll was loaded")
            outsiders = [p for p in modules if "geosoft" in p.casefold() and "desktop applications" in p.casefold()]
            if outsiders:
                result["unexpected_vendor_modules"] = outsiders
                raise OSError("Installed Oasis montaj modules were loaded")
            result["ok"] = bool(library._handle)
    except (OSError, ValueError) as error:
        result.update(error=str(error), missing_dlls=missing_imports(root))
    return result


def _check_worker(root, connection):
    environment = clean_environment(root)
    os.environ.clear()
    os.environ.update(environment)
    try:
        connection.send(check_runtime(root))
    finally:
        connection.close()


def check_in_subprocess(root):
    """Keep loader errors and native failures out of the QGIS process."""
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_check_worker, args=(str(root), send))
    process.start()
    send.close()
    try:
        if not receive.poll(90):
            raise TimeoutError("GX load check timed out")
        result = receive.recv()
    except (EOFError, OSError, TimeoutError) as error:
        result = {"ok": False, "error": str(error) or "GX load check did not return a result",
                  "missing_dlls": missing_imports(root), "missing_frameworks": missing_frameworks(root)}
    finally:
        receive.close()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join()
    result["exit_code"] = process.exitcode
    result["ok"] = result["ok"] and process.exitcode == 0
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    arguments = parser.parse_args()
    report = check_runtime(arguments.root)
    print(json.dumps(report), flush=True)
    raise SystemExit(0 if report["ok"] else 2)
