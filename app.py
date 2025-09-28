import datetime
import random
from flask import Flask, render_template_string, request, redirect, session, url_for
import yfinance as yf
import pandas as pd

# --- Flask App Initialization ---
app = Flask(__name__)
app.secret_key = 'supersecretkey'

# --- In-Memory Data Storage ---
# For a production app, use a DB (SQLite/Postgres/etc.)
users = {}  # {username: {password: '...', balance: 100000, portfolio: {}, contests: []}}
portfolios = {}  # {username: {symbol: {shares: 10, purchase_price: 150.00}}}

# renamed contests -> contests_data to avoid name collision with route function
contests_data = {
    'contest1': {
        'name': 'Beginner Trader Challenge',
        'entry_fee': 100,
        'start_date': datetime.date(2023, 1, 1),
        'end_date': datetime.date(2025, 12, 31),
        'participants': []  # list of usernames
    },
    'contest2': {
        'name': 'High-Stakes Showdown',
        'entry_fee': 500,
        'start_date': datetime.date(2023, 1, 1),
        'end_date': datetime.date(2025, 12, 31),
        'participants': []
    }
}

# --- HTML Templates (as strings) ---
LOGIN_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MOCKVEST - Login</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    body { font-family: 'Inter', sans-serif; }
  </style>
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen">
  <div class="bg-white p-8 rounded-xl shadow-lg w-full max-w-md">
    <h1 class="text-3xl font-bold text-center text-gray-800 mb-6">MOCKVEST</h1>
    <h2 class="text-xl font-semibold text-center text-gray-600 mb-6">{{ mode.capitalize() }}</h2>

    {% if error %}
      <div class="bg-red-100 text-red-700 px-4 py-3 rounded-lg text-sm mb-4" role="alert">{{ error }}</div>
    {% endif %}

    <form method="post" action="{{ url_for('login') }}">
      <input type="hidden" name="mode" value="{{ mode }}">
      <div class="mb-4">
        <label class="block text-gray-700 text-sm font-bold mb-2" for="username">Username</label>
        <input id="username" name="username" type="text" required placeholder="Username"
               class="shadow appearance-none border rounded-lg w-full py-3 px-4 text-gray-700 leading-tight focus:outline-none focus:shadow-outline">
      </div>
      <div class="mb-6">
        <label class="block text-gray-700 text-sm font-bold mb-2" for="password">Password</label>
        <input id="password" name="password" type="password" required placeholder="*********"
               class="shadow appearance-none border rounded-lg w-full py-3 px-4 text-gray-700 leading-tight focus:outline-none focus:shadow-outline">
      </div>

      <div class="flex items-center justify-between">
        <button type="submit"
                class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-lg focus:outline-none focus:shadow-outline transition duration-200">
          {{ mode.capitalize() }}
        </button>
        <a href="#" class="inline-block align-baseline font-bold text-sm text-blue-500 hover:text-blue-800"
           onclick="const m = document.querySelector('input[name=mode]'); m.value = (m.value === 'login' ? 'register' : 'login'); this.innerText = (this.innerText === 'Switch to Register' ? 'Switch to Login' : 'Switch to Register'); event.preventDefault();">
          Switch to {{ 'Register' if mode == 'login' else 'Login' }}
        </a>
      </div>
    </form>
  </div>
</body>
</html>
"""

# mark content safe when rendering ({{ content|safe }}) so inner templates render as HTML
BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 text-gray-900">
    <nav class="bg-blue-600 p-4 text-white flex justify-between">
        <span class="font-bold">MockVest</span>
        <div>
            <a href="/" class="px-3">Dashboard</a>
            <a href="/portfolio" class="px-3">Portfolio</a>
            <a href="/contests" class="px-3">Contests</a>
            <a href="/leaderboard" class="px-3">Leaderboard</a>
        </div>
    </nav>
    <main class="container mx-auto mt-8 p-4">
        {{ content|safe }}
    </main>
</body>
</html>
"""

DASHBOARD_HTML = """
<h2 class="text-2xl font-bold mb-4">Dashboard</h2>
<div class="bg-white p-6 rounded-lg shadow-md">
  <p class="text-lg mb-2"><strong>Current Balance:</strong> ${{ "{:,.2f}".format(balance) }}</p>
  <p class="text-lg mb-2"><strong>Portfolio Value:</strong> ${{ "{:,.2f}".format(portfolio_value) }}</p>
  <p class="text-lg"><strong>Total Net Worth:</strong> ${{ "{:,.2f}".format(net_worth) }}</p>
</div>

<div class="mt-8">
  <h3 class="text-xl font-bold mb-4">Market Snapshot</h3>
  <p class="text-gray-600 mb-2">Prices are updated with each page refresh.</p>
  <div class="bg-white p-6 rounded-lg shadow-md">
    <ul class="space-y-2">
      {% for symbol, price in market_data.items() %}
      <li class="flex justify-between items-center py-2 border-b last:border-b-0">
        <span class="font-semibold">{{ symbol }}</span>
        {% if price is not none %}
          <span class="text-sm text-green-600">${{ "{:,.2f}".format(price) }}</span>
        {% else %}
          <span class="text-sm text-gray-500">N/A</span>
        {% endif %}
      </li>
      {% endfor %}
    </ul>
  </div>
</div>
"""

PORTFOLIO_HTML = """
<h2 class="text-2xl font-bold mb-4">My Portfolio</h2>
<div class="bg-white p-6 rounded-lg shadow-md">
  <p class="text-lg mb-4"><strong>Current Balance:</strong> ${{ "{:,.2f}".format(balance) }}</p>

  <h3 class="text-xl font-semibold mb-4">Holdings</h3>
  {% if not holdings %}
    <p class="text-gray-600 italic">Your portfolio is currently empty.</p>
  {% else %}
  <div class="overflow-x-auto">
    <table class="min-w-full divide-y divide-gray-200">
      <thead class="bg-gray-50">
        <tr>
          <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Symbol</th>
          <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Shares</th>
          <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Current Price</th>
          <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Total Value</th>
        </tr>
      </thead>
      <tbody class="bg-white divide-y divide-gray-200">
        {% for symbol, stock_data in holdings.items() %}
        <tr>
          <td class="px-6 py-4 whitespace-nowrap font-medium text-gray-900">{{ symbol }}</td>
          <td class="px-6 py-4 whitespace-nowrap text-gray-500">{{ stock_data['shares'] }}</td>
          <td class="px-6 py-4 whitespace-nowrap text-gray-500">
            {% if stock_data['current_price'] is not none %}
              ${{ "{:,.2f}".format(stock_data['current_price']) }}
            {% else %}
              N/A
            {% endif %}
          </td>
          <td class="px-6 py-4 whitespace-nowrap text-gray-500">
            ${{ "{:,.2f}".format(stock_data['total_value']) }}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}

  <h3 class="text-xl font-semibold mt-8 mb-4">Trade Stocks</h3>
  <form action="{{ url_for('trade_stock') }}" method="post" class="space-y-4">
    <div>
      <label for="symbol" class="block text-sm font-medium text-gray-700">Stock Symbol</label>
      <input type="text" name="symbol" id="symbol" placeholder="e.g., AAPL, GOOG" required
             class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring focus:ring-blue-500 focus:ring-opacity-50 px-3 py-2">
    </div>
    <div>
      <label for="shares" class="block text-sm font-medium text-gray-700">Number of Shares</label>
      <input type="number" name="shares" id="shares" min="1" required
             class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring focus:ring-blue-500 focus:ring-opacity-50 px-3 py-2">
    </div>
    <div class="flex space-x-4">
      <button type="submit" name="action" value="buy" class="flex-1 bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded-lg transition duration-200">Buy</button>
      <button type="submit" name="action" value="sell" class="flex-1 bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded-lg transition duration-200">Sell</button>
    </div>
  </form>
</div>
"""

CONTESTS_HTML = """
<h2 class="text-2xl font-bold mb-4">Join a Contest</h2>
<div class="grid md:grid-cols-2 gap-6">
  {% for contest_id, contest_data in contests.items() %}
  <div class="bg-white p-6 rounded-lg shadow-md flex flex-col justify-between">
    <div>
      <h3 class="text-xl font-semibold mb-2">{{ contest_data['name'] }}</h3>
      <p class="text-gray-600 mb-2"><strong>Entry Fee:</strong> ${{ "{:,.2f}".format(contest_data['entry_fee']) }}</p>
      <p class="text-gray-600 mb-4"><strong>Participants:</strong> {{ contest_data['participants'] | length }}</p>
    </div>
    <div class="flex items-center space-x-4">
      {% if username in contest_data['participants'] %}
        <span class="text-sm font-medium text-green-600">Joined!</span>
        <a href="{{ url_for('leaderboard', contest_id=contest_id) }}" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-lg transition duration-200">View Leaderboard</a>
      {% else %}
        <form method="post" action="{{ url_for('join_contest', contest_id=contest_id) }}">
          <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-lg transition duration-200">Join Contest</button>
        </form>
      {% endif %}
    </div>
  </div>
  {% endfor %}
</div>
"""

LEADERBOARD_HTML = """
<h2 class="text-2xl font-bold mb-4">Leaderboard: {{ contest_name }}</h2>
<div class="bg-white p-6 rounded-lg shadow-md">
  <div class="overflow-x-auto">
    <table class="min-w-full divide-y divide-gray-200">
      <thead class="bg-gray-50">
        <tr>
          <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rank</th>
          <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Username</th>
          <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Net Worth</th>
          <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Returns (%)</th>
        </tr>
      </thead>
      <tbody class="bg-white divide-y divide-gray-200">
        {% for participant in leaderboard %}
        <tr>
          <td class="px-6 py-4 whitespace-nowrap font-medium text-gray-900">{{ loop.index }}</td>
          <td class="px-6 py-4 whitespace-nowrap text-gray-500">{{ participant['username'] }}</td>
          <td class="px-6 py-4 whitespace-nowrap text-gray-500">${{ "{:,.2f}".format(participant['net_worth']) }}</td>
          <td class="px-6 py-4 whitespace-nowrap text-{{ 'green' if participant['returns'] >= 0 else 'red' }}-600 font-semibold">{{ "{:,.2f}".format(participant['returns']) }}%</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
"""

# --- Helper Functions ---
def get_stock_price(symbol):
    """Fetches the current price of a stock using yfinance.
       Returns float price or None if not available."""
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if not data.empty:
            # Take last close
            return float(data['Close'].iloc[-1])
    except Exception:
        pass
    return None

def calculate_portfolio_value(username):
    """Calculates the current value of a user's stock portfolio."""
    user_portfolio = portfolios.get(username, {})
    total_value = 0.0
    if not user_portfolio:
        return 0.0

    # For reliability we fetch per symbol (safe fallback)
    for symbol, stock_data in user_portfolio.items():
        current_price = get_stock_price(symbol)
        if current_price is None:
            # fallback to purchase_price if current price not available
            current_price = float(stock_data.get('purchase_price', 0.0))
        total_value += stock_data['shares'] * current_price

    return total_value

def calculate_returns(net_worth):
    """Calculates the percentage return based on initial capital."""
    initial_capital = 100000.0
    if initial_capital == 0:
        return 0.0
    returns = ((net_worth - initial_capital) / initial_capital) * 100.0
    return returns

# --- Flask Routes ---

@app.route('/')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_data = users.get(username, {})

    balance = float(user_data.get('balance', 0.0))
    portfolio_value = calculate_portfolio_value(username)
    net_worth = balance + portfolio_value

    # Market data (robust to None)
    market_symbols = ['AAPL', 'GOOG', 'MSFT', 'AMZN']
    market_data = {}
    for sym in market_symbols:
        p = get_stock_price(sym)
        market_data[sym] = p  # p may be float or None; template handles None

    content = render_template_string(DASHBOARD_HTML,
                                     balance=balance,
                                     portfolio_value=portfolio_value,
                                     net_worth=net_worth,
                                     market_data=market_data)
    return render_template_string(BASE_HTML, title="Dashboard", content=content, username=username)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    # Default mode is 'login' on GET, or get from POST
    mode = request.form.get('mode', 'login')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if mode == 'register':
            if username in users:
                error = 'Username already exists. Please choose a different one.'
            else:
                users[username] = {'password': password, 'balance': 100000.0, 'contests': []}
                portfolios[username] = {}
                session['username'] = username
                return redirect(url_for('dashboard'))
        elif mode == 'login':
            user = users.get(username)
            if user and user['password'] == password:
                session['username'] = username
                return redirect(url_for('dashboard'))
            else:
                error = 'Invalid username or password.'

    return render_template_string(LOGIN_HTML, error=error, mode=mode)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/portfolio')
def portfolio():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_data = users.get(username, {})
    balance = float(user_data.get('balance', 0.0))

    user_portfolio = portfolios.get(username, {})
    holdings = {}

    # Build holdings with current prices and total values
    for symbol, stock_data in user_portfolio.items():
        current_price = get_stock_price(symbol)
        if current_price is None:
            current_price = float(stock_data.get('purchase_price', 0.0))
        total_value = stock_data['shares'] * current_price
        holdings[symbol] = {
            'shares': stock_data['shares'],
            'current_price': current_price,
            'total_value': total_value
        }

    content = render_template_string(PORTFOLIO_HTML, balance=balance, holdings=holdings)
    return render_template_string(BASE_HTML, title="My Portfolio", content=content, username=username)

@app.route('/trade_stock', methods=['POST'])
def trade_stock():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    symbol = request.form['symbol'].strip().upper()
    try:
        shares = int(request.form['shares'])
    except Exception:
        return "Invalid number of shares.", 400
    action = request.form['action']

    current_price = get_stock_price(symbol)
    if current_price is None:
        return "Invalid stock symbol or price not available.", 400

    user_data = users.get(username)
    user_portfolio = portfolios.get(username)

    if action == 'buy':
        cost = shares * current_price
        if user_data['balance'] >= cost:
            user_data['balance'] -= cost

            # Update or add stock to portfolio
            if symbol in user_portfolio:
                existing_shares = user_portfolio[symbol]['shares']
                existing_price = user_portfolio[symbol]['purchase_price']

                # Calculate new average price
                new_total_cost = (existing_shares * existing_price) + cost
                new_total_shares = existing_shares + shares

                user_portfolio[symbol]['shares'] = new_total_shares
                user_portfolio[symbol]['purchase_price'] = new_total_cost / new_total_shares
            else:
                user_portfolio[symbol] = {'shares': shares, 'purchase_price': current_price}
        else:
            return "Insufficient balance.", 400

    elif action == 'sell':
        if symbol not in user_portfolio or user_portfolio[symbol]['shares'] < shares:
            return "Insufficient shares to sell.", 400

        revenue = shares * current_price
        user_data['balance'] += revenue
        user_portfolio[symbol]['shares'] -= shares

        if user_portfolio[symbol]['shares'] == 0:
            del user_portfolio[symbol]

    return redirect(url_for('portfolio'))

# Renamed route function to avoid shadowing the contests_data variable
@app.route('/contests')
def contests_page():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    content = render_template_string(CONTESTS_HTML, contests=contests_data, username=username)
    return render_template_string(BASE_HTML, title="Contests", content=content, username=username)

@app.route('/join_contest/<contest_id>', methods=['POST'])
def join_contest(contest_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    contest_data = contests_data.get(contest_id)
    user_data = users.get(username)

    if not contest_data:
        return "Contest not found.", 404

    if username in contest_data['participants']:
        return "You have already joined this contest.", 400

    entry_fee = contest_data['entry_fee']
    if user_data['balance'] < entry_fee:
        return "Insufficient balance to join the contest.", 400

    user_data['balance'] -= entry_fee
    contest_data['participants'].append(username)

    return redirect(url_for('contests_page'))

@app.route('/leaderboard/<contest_id>')
def leaderboard(contest_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    contest_data = contests_data.get(contest_id)
    if not contest_data:
        return "Contest not found.", 404

    leaderboard_data = []
    for uname in contest_data['participants']:
        user_data = users.get(uname, {})
        balance = float(user_data.get('balance', 0.0))
        portfolio_value = calculate_portfolio_value(uname)
        net_worth = balance + portfolio_value
        returns_pct = calculate_returns(net_worth)

        leaderboard_data.append({
            'username': uname,
            'net_worth': net_worth,
            'returns': returns_pct
        })

    # Sort the leaderboard by returns in descending order
    leaderboard_data.sort(key=lambda x: x['returns'], reverse=True)

    content = render_template_string(LEADERBOARD_HTML,
                                     contest_name=contest_data['name'],
                                     leaderboard=leaderboard_data)
    return render_template_string(BASE_HTML, title="Leaderboard", content=content, username=session['username'])


# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True)
