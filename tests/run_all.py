"""Run every test suite and print one summary.

    python tests/run_all.py            run all of them
    python tests/run_all.py 07 11      run only those suites
    python tests/run_all.py --keep     leave the test database behind

The suites run against a **copy** of the database called `<DB_NAME>_test`,
which this script creates, fills with the sample data and drops again at the
end. Your real `service_expert` database is never opened, so a test run can
never change your own bookings, providers or payments.

Two suites reach the internet: test_03 uses the Galli routing and search APIs,
and test_04 talks to the Khalti sandbox. They fail without a connection.
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

import support   # noqa: E402  (the path has to be set first)


def suite_files(wanted):
    names = sorted(f for f in os.listdir(HERE)
                   if f.startswith("test_") and f.endswith(".py"))
    if not wanted:
        return names
    return [f for f in names if any(w in f for w in wanted)]


def build_test_database(name):
    """Create the test database and fill it with the sample data.

    setup_db.py already knows how to create a database, run schema.sql and
    seed it, and it is safe to run twice - so it is used here rather than a
    second copy of the same logic.
    """
    connection = support.connect_server()
    cursor = connection.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
    connection.commit()
    cursor.close()
    connection.close()

    environment = dict(os.environ, DB_NAME=name)
    result = subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "setup_db.py")],
        cwd=PROJECT_ROOT, env=environment,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit("Could not build the test database.")


def drop_test_database(name):
    connection = support.connect_server()
    cursor = connection.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
    connection.commit()
    cursor.close()
    connection.close()


def main():
    arguments = sys.argv[1:]
    keep = "--keep" in arguments
    wanted = [a for a in arguments if not a.startswith("--")]

    files = suite_files(wanted)
    if not files:
        raise SystemExit("No test suites matched.")

    real = support.real_database_name()
    name = support.use_test_database()

    # The runner drops and recreates `name`. If that ever came out equal to the
    # database the application really uses, it would destroy the project's own
    # data - so stop instead.
    if name == real:
        raise SystemExit(
            f"Refusing to run: the test database would be `{name}`, which is "
            "the database the application itself uses. Set DB_NAME in .env to "
            "your real database name (for example service_expert)."
        )

    settings = support.settings()
    print(f"MySQL   : {settings['host']}:{settings['port']} as '{settings['user']}'")
    print(f"Database: {name}  (created for this run, your real data is untouched)")
    print(f"Suites  : {len(files)}\n")

    build_test_database(name)

    environment = dict(os.environ, DB_NAME=name, SERVICE_EXPERT_TEST_DB=name,
                       PYTHONIOENCODING="utf-8")
    results = []
    started = time.time()

    for filename in files:
        print("-" * 70)
        print(filename)
        print("-" * 70)
        run = subprocess.run(
            [sys.executable, os.path.join(HERE, filename)],
            cwd=PROJECT_ROOT, env=environment,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        output = (run.stdout or "") + (run.stderr or "")
        summary = [line for line in output.splitlines() if line.startswith("=====")]

        if run.returncode != 0 and not summary:
            print(output[-2000:])
            results.append((filename, None, None))
            continue

        # Count from the suite's own summary line.
        passed = failed = 0
        if summary:
            print(summary[-1])
            words = summary[-1].replace(",", "").split()
            passed = int(words[words.index("passed") - 1])
            failed = int(words[words.index("failed") - 1])
        if failed:
            for line in output.splitlines():
                if line.startswith("   -"):
                    print(line)
        results.append((filename, passed, failed))

    if not keep:
        drop_test_database(name)

    print("\n" + "=" * 70)
    total_passed = total_failed = 0
    broken = []
    for filename, passed, failed in results:
        if passed is None:
            print(f"  {filename:36s}  DID NOT RUN")
            broken.append(filename)
            continue
        total_passed += passed
        total_failed += failed
        mark = "ok" if not failed else f"{failed} FAILED"
        print(f"  {filename:36s}  {passed:4d} passed   {mark}")

    print("=" * 70)
    print(f"  {total_passed} checks passed, {total_failed} failed, "
          f"{len(broken)} suite(s) did not run   "
          f"({time.time() - started:.0f}s)")
    if keep:
        print(f"  test database `{name}` was kept")
    print("=" * 70)

    return 1 if (total_failed or broken) else 0


if __name__ == "__main__":
    raise SystemExit(main())
