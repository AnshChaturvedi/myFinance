import os

from cs50 import SQL
from datetime import datetime
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

#export API_KEY=pk_460d736bf26d459e8a219a25ff7d5447

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():

    # Get the current user id to index to the right purchases,
    # and store those purchases as a list
    current_user_id = session["user_id"]
    rows = db.execute("SELECT * FROM purchases WHERE user_id = ?", current_user_id)
    row_len = len(rows)

    # Empty lists that will be used for the for loop to store values and
    # print to the table in index.html
    prices = []
    total_prices = []
    prices_at_pop = []
    net_profits = []

    # Net worth variable where we will add the current holding values as well
    # as the cash that the user has left to invest
    net_worth = 0

    # Get the amount of cash user has left to invest, and then a) display that value
    # to index.html and b) add that value to the user's net worth
    cash = db.execute("SELECT cash FROM users WHERE id = ?", current_user_id)
    cash_on_hand = float(cash[0]["cash"])
    net_worth += cash_on_hand

    # Loop to iterate through each purchase of the user
    for row in rows:

        # Calculate current value of holding and display that to index.html, and
        # using initial value of holding, calculate the net profit for that purchase
        current_value = lookup(row["stock"])["price"] * row["shares"]
        initial_value = row["total_cost"]
        net_profits.append(current_value - initial_value)

        # Add current value of holding to the user's net worth
        net_worth += current_value

        # Values that will be shown in the table in index.html
        prices_at_pop.append(row["price_at_pop"])
        prices.append(lookup(row["stock"])["price"])
        total_prices.append(round((lookup(row["stock"])["price"] * row["shares"]), 2))

    # Once the loop is completed, render index.html and give it access to the following variables
    return render_template("index.html",
    rows=rows, prices=prices, row_len=row_len, total_prices=total_prices, prices_at_pop=prices_at_pop,
    net_profits=net_profits, net_worth=net_worth, cash_on_hand=cash_on_hand)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    # Render "buy.html" if request method is "get"
    if request.method == "GET":
        return render_template("buy.html")

    # If request method is "post"...
    else:

        symbol = lookup(request.form.get("symbol"))["symbol"].upper()
        shares = int(request.form.get("shares"))

        # Time at point of purchase
        buy_time = datetime.utcnow()

        price_at_pop = lookup(symbol)["price"]

        # Checks whether field is left empty, shares is not a positive integer, or stock symbol doesn't exist
        if not shares or not symbol or shares < 1 or lookup(symbol) == None:
            return apology("Oops! Something went wrong.", 403)

        # Get total cost of transaction
        total_cost = lookup(symbol)["price"] * shares

        # Lookup current user in SQLite database
        current_user_id = session["user_id"]
        rows = db.execute("SELECT * FROM users WHERE id = :the_user_id", the_user_id=current_user_id)

        # Check if user has enough money
        if rows[0]["cash"] < total_cost:
            return apology("You don't have enough money.", 403)

        # Find new balance and set that as the new balance for the user
        else:
            new_balance = rows[0]["cash"] - total_cost

            # Add transaction details to "purchases" table for use in "history" page
            db.execute("INSERT INTO purchases (user_id, time, stock, shares, total_cost, price_at_pop) VALUES (?,?,?,?,?,?)",
            current_user_id, buy_time, symbol, shares, total_cost, price_at_pop)

            # Update user cash information
            db.execute("UPDATE users SET cash = ? WHERE id = ?", new_balance, current_user_id)

            # Add purchase to history
            db.execute("INSERT INTO history (user_id, type, time, stock, shares, money, share_price) VALUES (?,?,?,?,?,?,?)",
            current_user_id, "buy", buy_time, symbol, shares, total_cost, price_at_pop)

        # Finally, redirect user back to /index
        return redirect("/")

@app.route("/history")
@login_required
def history():

    # Get the current user id to index to the right purchases,
    # and store those purchases as a list
    current_user_id = session["user_id"]
    rows = db.execute("SELECT * FROM history WHERE user_id = ?", current_user_id)
    row_len = len(rows)

    # Empty lists that will be used for the for loop to store values and
    # print to the table in index.html
    transaction_types = []
    times = []
    total_prices = []
    prices_at_pot = []

    # Loop to iterate through each purchase of the user
    for row in rows:

        # Values that will be shown in the table in index.html
        transaction_types.append(row["type"])
        times.append(row["time"])
        prices_at_pot.append(row["share_price"])
        total_prices.append(round((row["share_price"] * row["shares"]), 2))

    # Once the loop is completed, render index.html and give it access to the following variables
    return render_template("history.html",
    rows=rows, row_len=row_len, total_prices=total_prices, prices_at_pot=prices_at_pot,)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():

    # Returns webpage if request method is "get"
    if request.method == "GET":
        return render_template("quote.html")

    # Else if the request method is "post"
    else:

        # Extract the values of the dictionary returned by the lookup function
        symbol = lookup(request.form.get("symbol"))["symbol"]
        price = usd(lookup(symbol)["price"])
        company_name = lookup(symbol)["name"]

        # Render "quoted.html" with the company name, symbol and current price
        return render_template("quoted.html", symbol=symbol, price=price, company_name=company_name)

    return apology("TODO")


@app.route("/register", methods=["GET", "POST"])
def register():

    # Returns webpage if request method is "get"
    if request.method == "GET":
        return render_template("register.html")

    # If request method is "post"...
    else:

        # Check if username and password isn't empty
        if not request.form.get("username") or not request.form.get("password"):
            return apology("invalid username and/or password", 403)

        # Check if password and password confirmation fields match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match", 403)

        password = request.form.get("password")

        counter = 0
        special_chars = ["@", "_", "!", "#", "$", "%", "^", "&", "*", "(", ")", "<", ">", "?", "/", ":"]

        for char in password:
            if char in special_chars:
                counter += 1
            continue

        if counter < 2:
            return apology("Passwords is not strong enough. You need atleast three special characters.", counter)

        username = request.form.get("username")
        password_hash = generate_password_hash(request.form.get("password"))

        db.execute("INSERT INTO users (username, hash) VALUES( :username, :hash)",
                   username=username, hash=password_hash)

        return redirect("/login")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "GET":

        return render_template("sell.html")

    else:

        # Get the current user id to access the right information
        current_user_id = session["user_id"]

        # Get stocks and shares that user has purchased and the stock the user wants to sell
        sellable_stocks = db.execute("SELECT stock, shares FROM purchases WHERE user_id = ?", current_user_id)
        stock_to_sell = request.form.get("symbol").upper()
        shares_to_sell = request.form.get("shares")

        # Boolean flags to make sure user has actually bought the stock before and he/she is
        # selling shares that he/she actually owns
        stock_exists = True
        shares_exists = True

        # Loop to check through query and make sure the user's sell request for "stock" is valid
        for stock in sellable_stocks:
            if stock["stock"] != stock_to_sell:
                continue
            stock_exists == False

        # Next loop to check through query and make sure the user's sell request for "shares" is valid
        for stock in sellable_stocks:
            if stock["shares"] != stock_to_sell:
                continue
            shares_exists == False

        # If any one of them is false, the transaction is cancelled and an apology is returned
        if stock_exists == False or shares_exists == False:
            return apology("An error occured.")

        # Share price at point of sale
        price_at_sale = lookup(stock_to_sell)["price"]

        # Total value of holding at point of sale
        money_made = float(shares_to_sell) * price_at_sale

        # Time at point of sale
        sale_time = datetime.utcnow()

        # Insert into the "sales" SQL table the details of the sale
        db.execute("INSERT INTO sales (user_id, time, stock, shares, money_made, price_at_sale) VALUES (?,?,?,?,?,?)",
        current_user_id, sale_time, stock_to_sell, shares_to_sell, money_made, price_at_sale)

        # Add sale to history table
        db.execute("INSERT INTO history (user_id, type, time, stock, shares, money, share_price) VALUES (?,?,?,?,?,?,?)",
        current_user_id, "sell", sale_time, stock_to_sell, shares_to_sell, money_made, price_at_sale)

        # Get current amount of cash left for user
        cash_now = db.execute("SELECT cash FROM users WHERE id = ?", current_user_id)[0]["cash"] + money_made

        # Update cash balance for current user
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_now, current_user_id)

        db.execute("DELETE FROM purchases WHERE user_id = ? AND stock = ?", current_user_id, stock_to_sell)

        # Redirect user to their home page
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)