"""Start the localhost application with explicit model configuration."""
import argparse
import os
from .llm.runners import build_runner
from .server import serve


def main():
    """Parse port and runner options, then launch the single application pipeline."""
    parser = argparse.ArgumentParser(description='Heat Pump Ready – lokale Ersteinschätzung')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--runner', choices=('disabled', 'api', 'mlx'), default=os.environ.get('LLM_RUNNER', 'disabled'))
    parser.add_argument('--public-origin', default='', help='Genau eine erlaubte öffentliche HTTPS-Origin für einen Demo-Tunnel.')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port muss zwischen 1024 und 65535 liegen.')
    serve(build_runner(args.runner), args.runner, args.port, args.public_origin)

if __name__ == '__main__':
    main()
