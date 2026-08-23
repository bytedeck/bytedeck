#!/usr/bin/env python3
"""Assert the production compose overlay upholds its deployment invariants.

`docker compose config` renders the merged production configuration without a
Docker daemon, so this runs anywhere and in seconds. It guards the properties
that no other check covers: CI only ever renders the development overlay, so a
production-only regression (an app port published straight to the host, say)
would otherwise reach a deploy unnoticed.
"""
import re
import subprocess
import sys

import yaml

APP_SERVICES = ("web", "celery", "celery-beat")
REQUIRED_SERVICES = APP_SERVICES + ("redis", "nginx")

# A json-file `max-size`: a number with an optional unit, e.g. "10m". Docker
# documents k/m/g and also accepts the "mb" spelling, so both are allowed here.
LOG_SIZE = re.compile(r"^(\d+(?:\.\d+)?)(b|[kmg]b?)?$", re.IGNORECASE)


def runs_as_root(user):
    """Return whether a Compose `user:` value would run the container as root.

    `user` is the rendered value, which Compose accepts as `UID[:GID]` or
    `name[:group]`, so only the part before the first colon identifies the user
    and `0:1000` is as much root as `0`. None means no override, which is not
    root: the image's own USER applies, and that is asserted against the built
    image by the "Application image" job in the workflow.
    """
    if user is None:
        return False
    return str(user).split(":", 1)[0].strip().lower() in ("0", "root")


def log_size_is_bounded(size):
    """Return whether a json-file `max-size` option actually bounds the log.

    `size` is the rendered option value. Truthiness is not enough here, since
    `"0"` and a typo'd size are both non-empty strings while neither bounds
    anything, so the value has to parse as a positive Docker size.
    """
    if size is None:
        return False
    match = LOG_SIZE.match(str(size).strip())
    return bool(match) and float(match.group(1)) > 0


def render():
    """Render the merged production configuration.

    The interpolated variables are supplied here rather than read from the
    environment so the result is the same wherever this runs. Returns the parsed
    configuration as a dict. Exits non-zero rather than returning if the config
    fails to render at all, since every assertion below would be meaningless.
    """
    out = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.prod.aws.yml", "config"],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "ROOT_DOMAIN": "example.com",
             "WUID": "1000", "WGID": "999", "CDN_static": "cdn.example.com"},
    )
    if out.returncode:
        sys.exit(f"FAIL: production config does not render:\n{out.stderr}")
    return yaml.safe_load(out.stdout)


def main():
    """Assert every production invariant and report the outcome of each.

    Deliberately evaluates all of them instead of stopping at the first failure,
    so one run tells you everything that drifted. Returns the process exit
    status: 1 if any assertion failed, 0 otherwise.
    """
    services = render().get("services", {})
    failures = []

    def check(ok, msg):
        """Record one assertion, where `ok` is its result and `msg` describes it.

        Prints the outcome and appends `msg` to the enclosing `failures` list
        when `ok` is false, which is what determines the exit status.
        """
        print(f"  {'PASS' if ok else 'FAIL'}  {msg}")
        if not ok:
            failures.append(msg)

    # Everything below describes a specific service, so a service that is not
    # there at all would otherwise read as compliant: `.get(name, {})` finds no
    # published port on a `celery` that does not exist. Establish they are all
    # present first, and say so plainly rather than asserting about nothing.
    for name in REQUIRED_SERVICES:
        check(name in services, f"{name} is defined")
    if failures:
        print(f"\n{len(failures)} failure(s): production is missing a service, so the rest was not checked")
        return 1

    # Nothing but nginx may reach the host: the app must not be reachable around
    # nginx, which terminates TLS and enforces the Host check.
    for name in APP_SERVICES + ("redis",):
        check(not services[name].get("ports"), f"{name} publishes no host port")
    check(
        sorted(f"{p.get('published')}->{p.get('target')}" for p in services["nginx"]["ports"])
        == ["443->8088", "80->8080"],
        "nginx publishes exactly 80 and 443",
    )

    # Production runs the built image, not the host checkout.
    for name in APP_SERVICES:
        check(not services[name].get("volumes"), f"{name} mounts no source volume")

    # Nothing may be pinned to root here. The rendered config cannot see the
    # image's own USER, so this only catches an explicit root override; that the
    # image itself defaults to a non-root user is asserted against the built
    # image by the "Application image" job in
    # .github/workflows/production_config.yml.
    for name in APP_SERVICES:
        check(not runs_as_root(services[name].get("user")), f"{name} is not pinned to root")

    # Tier separation: nginx must have no route to redis.
    nginx_nets = set(services["nginx"].get("networks") or {})
    web_nets = set(services["web"].get("networks") or {})
    redis_nets = set(services["redis"].get("networks") or {})
    check(nginx_nets == {"frontend-network"}, "nginx is only on frontend-network")
    check(web_nets == {"frontend-network", "backend-network"}, "web bridges both tiers")
    check(not (nginx_nets & redis_nets), "nginx shares no network with redis")

    # Restart policy and bounded logs apply everywhere in production.
    for name, svc in services.items():
        check(svc.get("restart") == "unless-stopped", f"{name} restarts unless stopped")
        check(log_size_is_bounded(svc.get("logging", {}).get("options", {}).get("max-size")),
              f"{name} bounds its log size")

    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
