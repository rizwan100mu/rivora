"""Install the bundled single Rivora app from bench/apps/rivora; no ESS checkout."""
from pathlib import Path
import argparse
import shutil
import subprocess

LEGACY_APPS = {"employee_self_service", "rizora_workforce", "ess_mobile_extras"}

def validate(bench, site, source, installed):
    bench, source = Path(bench).resolve(), Path(source).resolve()
    if source != (bench / "apps" / "rivora").resolve():
        raise RuntimeError("Extract this app root (containing pyproject.toml) into BENCH/apps/rivora first.")
    if not (bench / "sites" / site / "site_config.json").is_file():
        raise RuntimeError("The named site does not exist in this bench.")
    conflicts = set(installed) & LEGACY_APPS
    if conflicts:
        raise RuntimeError("Existing legacy apps require a reviewed staging migration: " + ", ".join(sorted(conflicts)))
    if not {"erpnext", "hrms"}.issubset(installed):
        raise RuntimeError("Install ERPNext and HRMS on the staging site first.")
    return bench, source

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--plan", action="store_true", help="Read preflight only; print commands without writes")
    args = parser.parse_args()
    bench = Path(args.bench).resolve()
    executable = shutil.which("bench")
    if not executable:
        raise RuntimeError("Run as the bench owner with bench on PATH.")
    def run(*command, capture=False):
        return subprocess.run([executable, *command], cwd=bench, check=True, text=True, stdout=subprocess.PIPE if capture else None)
    output = run("--site", args.site, "list-apps", capture=True).stdout
    installed = {line.split()[0] for line in output.splitlines() if line.split()}
    bench, source = validate(bench, args.site, Path(__file__).parent, installed)
    commands = [["--site", args.site, "backup", "--with-files"], ["pip", "install", "-e", str(source)]]
    if "rivora" not in installed:
        commands.append(["--site", args.site, "install-app", "rivora"])
    commands.extend([["--site", args.site, "migrate"], ["build", "--app", "rivora"], ["--site", args.site, "clear-cache"], ["restart"]])
    if args.plan:
        for command in commands: print("bench " + " ".join(command))
        print("Rivora is bundled; no separate employee-service repository is fetched.")
        return
    run(*commands[0])
    run(*commands[1])
    apps = bench / "sites" / "apps.txt"
    registered = apps.read_text().splitlines()
    if "rivora" not in registered:
        apps.write_text("\n".join([*registered, "rivora"]) + "\n")
    for command in commands[2:]: run(*command)
    print("Rivora installed from local bundled source. Complete staging acceptance before production.")

if __name__ == "__main__":
    main()
