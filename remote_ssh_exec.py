import argparse
import sys

import paramiko


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", required=True)
    parser.add_argument("--command", required=True)
    args = parser.parse_args()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.host,
        username=args.user,
        password=args.password,
        timeout=20,
        banner_timeout=60,
        auth_timeout=30,
        look_for_keys=False,
        allow_agent=False,
    )
    try:
        _stdin, stdout, stderr = client.exec_command(args.command, get_pty=True)
        out = stdout.read().decode("utf-8", "ignore")
        err = stderr.read().decode("utf-8", "ignore")
        if out:
            sys.stdout.buffer.write(out.encode("utf-8", "replace"))
        if err:
            sys.stderr.buffer.write(err.encode("utf-8", "replace"))
        return stdout.channel.recv_exit_status()
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
