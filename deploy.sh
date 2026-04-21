#!/usr/bin/env bash
# Тонкая обёртка: запуск из корня клона на сервере — bash deploy.sh
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy/deploy.sh" "$@"
