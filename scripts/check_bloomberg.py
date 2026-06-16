from __future__ import annotations

import socket
from dataclasses import dataclass


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def check_import() -> Check:
    try:
        import blpapi  # type: ignore  # noqa: F401
    except ImportError:
        return Check(
            "Python blpapi package",
            False,
            "Not installed in .venv. Install Bloomberg's Python BLPAPI package before using live data.",
        )
    return Check("Python blpapi package", True, "Installed.")


def check_port(host: str = "127.0.0.1", port: int = 8194) -> Check:
    with socket.socket() as sock:
        sock.settimeout(2)
        open_port = sock.connect_ex((host, port)) == 0
    if not open_port:
        return Check(
            "Bloomberg Desktop API port",
            False,
            f"{host}:{port} is not reachable. Open Bloomberg Terminal on this machine and confirm Desktop API access.",
        )
    return Check("Bloomberg Desktop API port", True, f"{host}:{port} is reachable.")


def check_session(host: str = "localhost", port: int = 8194) -> Check:
    try:
        import blpapi  # type: ignore
    except ImportError:
        return Check("Bloomberg API session", False, "Skipped because blpapi is not installed.")

    options = blpapi.SessionOptions()
    options.setServerHost(host)
    options.setServerPort(port)
    session = blpapi.Session(options)
    try:
        if not session.start():
            return Check("Bloomberg API session", False, "Session did not start.")
        if not session.openService("//blp/refdata"):
            return Check("Bloomberg API session", False, "Could not open //blp/refdata.")
    except Exception as exc:
        return Check("Bloomberg API session", False, str(exc))
    finally:
        try:
            session.stop()
        except Exception:
            pass
    return Check("Bloomberg API session", True, "Connected and opened //blp/refdata.")


def main() -> None:
    checks = [check_import(), check_port(), check_session()]
    for item in checks:
        status = "OK" if item.ok else "MISSING"
        print(f"[{status}] {item.name}: {item.detail}")

    if all(item.ok for item in checks):
        print("\nBloomberg is ready. Set VRW_DATA_SOURCE=bloomberg and restart the dev server.")
    else:
        print("\nBloomberg is not ready yet. Fix the missing items above, then rerun this check.")


if __name__ == "__main__":
    main()
