import os

from waitress import serve

from mysite.wsgi import application


def get_trusted_proxy_headers():
    value = os.getenv(
        'WAITRESS_TRUSTED_PROXY_HEADERS',
        'x-forwarded-for x-forwarded-host x-forwarded-proto x-forwarded-port',
    )
    return {
        item.strip().lower()
        for item in value.replace(',', ' ').split()
        if item.strip()
    }


def main():
    host = os.getenv('WAITRESS_HOST', '127.0.0.1')
    port = int(os.getenv('WAITRESS_PORT', '8000'))
    threads = int(os.getenv('WAITRESS_THREADS', '8'))
    trusted_proxy = os.getenv('WAITRESS_TRUSTED_PROXY', '127.0.0.1')
    trusted_proxy_count = int(os.getenv('WAITRESS_TRUSTED_PROXY_COUNT', '1'))

    print(f'Starting Waitress on http://{host}:{port}')
    serve(
        application,
        host=host,
        port=port,
        threads=threads,
        trusted_proxy=trusted_proxy,
        trusted_proxy_count=trusted_proxy_count,
        trusted_proxy_headers=get_trusted_proxy_headers(),
        clear_untrusted_proxy_headers=True,
    )


if __name__ == '__main__':
    main()
