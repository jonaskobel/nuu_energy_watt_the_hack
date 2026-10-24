"""Start the localhost application with explicit model configuration."""
import argparse
from .llm.runners import build_runner
from .server import serve


def main():
    """Parse port and runner options, then launch the single application pipeline."""
    parser = argparse.ArgumentParser(description='Heat Pump Ready – lokale Ersteinschätzung')
    parser.add_argument('--port', type=int, default=8000)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('-api', '--api', dest='runner', action='store_const', const='api', help='ApiLLMRunner mit LLM_API_URL, LLM_MODEL und optional LLM_API_KEY verwenden.')
    modes.add_argument('-mlx', '--mlx', dest='runner', action='store_const', const='mlx', help='Lokales MLX-Gemma-Modell ausdrücklich aktivieren (Apple Silicon).')
    modes.add_argument('--runner', choices=('disabled', 'api', 'mlx'), help='Explizite Moduswahl; kompatibel mit bisherigen Startbefehlen.')
    parser.set_defaults(runner='disabled')
    parser.add_argument('--public-origin', default='', help='Genau eine erlaubte öffentliche HTTPS-Origin für einen Demo-Tunnel.')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port muss zwischen 1024 und 65535 liegen.')
    try:
        runner = build_runner(args.runner)
    except ValueError as error:
        parser.error(str(error))
    serve(runner, args.runner, args.port, args.public_origin)

if __name__ == '__main__':
    main()
