"""
ibkr/views.py

IBKR TWS integration views.
The IBKRClient singleton is imported from ibkr.client.
If TWS is not running, all endpoints degrade gracefully.
"""

from django.conf import settings as django_settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_GET


def ibkr_status_page(request):
    from .client import ib_client
    connected = ib_client.is_connected()
    return render(request, 'ibkr/index.html', {
        'connected': connected,
        'host': django_settings.IBKR_HOST,
        'port': django_settings.IBKR_PORT,
        'client_id': django_settings.IBKR_CLIENT_ID,
    })


def ibkr_status(request):
    """HTMX partial — returns a status pill. No auto-polling; called on demand only."""
    from .client import ib_client
    connected = ib_client.is_connected()

    if connected:
        html = (
            '<span class="inline-flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-full"'
            ' style="background:var(--profit-glow);color:var(--profit);border:1px solid rgba(16,185,129,0.2)">'
            '<span class="w-1.5 h-1.5 rounded-full bg-profit"></span>TWS Connected</span>'
        )
    else:
        html = (
            '<span class="inline-flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-full"'
            ' style="background:rgba(100,116,139,0.1);color:var(--text-secondary);border:1px solid var(--border)">'
            '<span class="w-1.5 h-1.5 rounded-full bg-slate-500"></span>Not connected</span>'
        )
    return HttpResponse(html)


def ibkr_settings(request):
    if request.method == 'POST':
        host      = request.POST.get('host', '127.0.0.1')
        port      = request.POST.get('port', '7497')
        client_id = request.POST.get('client_id', '1')

        # Write to .env using simple file update (python-decouple reads .env)
        env_path = django_settings.BASE_DIR / '.env'
        env_lines = []
        if env_path.exists():
            env_lines = env_path.read_text().splitlines()

        def _set_env(lines, key, value):
            for i, l in enumerate(lines):
                if l.startswith(f'{key}='):
                    lines[i] = f'{key}={value}'
                    return lines
            lines.append(f'{key}={value}')
            return lines

        env_lines = _set_env(env_lines, 'IBKR_HOST', host)
        env_lines = _set_env(env_lines, 'IBKR_PORT', port)
        env_lines = _set_env(env_lines, 'IBKR_CLIENT_ID', client_id)
        env_path.write_text('\n'.join(env_lines) + '\n')

        messages.success(request, 'IBKR settings saved. Restart the server to apply changes.')
        return redirect('ibkr_settings')

    return render(request, 'ibkr/settings.html', {
        'ibkr_host':      django_settings.IBKR_HOST,
        'ibkr_port':      django_settings.IBKR_PORT,
        'ibkr_client_id': django_settings.IBKR_CLIENT_ID,
    })


@require_GET
def ibkr_chain(request):
    from .client import ib_client
    from django.utils import timezone

    if not ib_client.is_connected():
        return render(request, 'ibkr/chain.html', {'connected': False, 'contracts': []})

    expiry = request.GET.get('expiry', timezone.localdate().strftime('%Y%m%d'))
    try:
        contracts = ib_client.fetch_chain(expiry)
    except Exception as exc:
        messages.error(request, f'Error fetching chain: {exc}')
        contracts = []

    return render(request, 'ibkr/chain.html', {'connected': True, 'contracts': contracts, 'expiry': expiry})


@require_GET
def ibkr_greeks(request):
    """JSON endpoint for the Fetch Greeks button on the trade entry form."""
    from .client import ib_client

    if not ib_client.is_connected():
        return JsonResponse({'error': 'TWS not connected'}, status=503)

    symbol = request.GET.get('symbol', 'SPX')
    expiry = request.GET.get('expiry', '')
    strike = request.GET.get('strike', '')
    right  = request.GET.get('right', 'C')  # C or P

    if not (expiry and strike):
        return JsonResponse({'error': 'expiry and strike are required'}, status=400)

    try:
        greek_data = ib_client.fetch_greeks(symbol, expiry, float(strike), right)
        return JsonResponse(greek_data)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)
