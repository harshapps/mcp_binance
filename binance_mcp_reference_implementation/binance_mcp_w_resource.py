from pathlib import Path
from mcp.server.fastmcp import FastMCP
import requests
from typing import Any
import yfinance as yf
from datetime import datetime
import pandas as pd

THIS_FOLDER = Path(__file__).parent.absolute()
ACTIVITY_LOG_PATH = THIS_FOLDER / "activity.log"

mcp = FastMCP("Binance MCP")

def get_symbol_from_name(name: str) -> str:
    if name.lower() in ["bitcoin", "btc"]:
        return "BTCUSDT"
    elif name.lower() in ["ethereum", "eth"]:
        return "ETHUSDT"
    else:
        return name.upper()

@mcp.tool()
def get_price(symbol: str) -> Any:
    """
    Get the current price of a crypto asset from Binance.

    Args:
        symbol (str): The symbol of the crypto asset to get the price of (e.g., 'BTCUSDT')
    
    Returns:
        Any: The current price of the crypto asset.
    """

    symbol = get_symbol_from_name(symbol)
    url = f"https://api.binance.us/api/v3/ticker/price?symbol={symbol}"
    response = requests.get(url)
    
    if response.status_code != 200:
        return {"error": f"Failed to fetch price for symbol {symbol}. Status code: {response.status_code}"}

        with open(ACTIVITY_LOG_PATH, "a") as f:            
            f.write(
                f"Error getting price for {symbol}: {response.status_code} - {response.text}\n"
            )
            raise Exception(f"Failed to fetch price for symbol {symbol}. Status code: {response.status_code}, Response: {response.text}")
    else:
        price = response.json()["price"]
        with open(ACTIVITY_LOG_PATH, "a") as f:
            f.write(
                f"Successfully fetched price for {symbol}: {price}, Current Time: {datetime.now()}\n"   
            )
    return f"The current price of {symbol} is {price}."



@mcp.tool()
def get_price_price_change(symbol: str) -> Any:
    """
    Get the current price and 24h price change of a crypto asset from Binance.

    Args:
        symbol (str): The symbol of the crypto asset to get the price of (e.g., 'BTCUSDT')
    
    Returns:
        Any: The current price and 24h price change of the crypto asset.
    """

    symbol = get_symbol_from_name(symbol)
    url = f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={symbol}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


@mcp.resource("file://activity.log")
def activity_log() -> str:
    with open(ACTIVITY_LOG_PATH, "r") as f:
        return f.read()


@mcp.resource("resource://crypto_price/{symbol}")
def get_crypto_price(symbol: str) -> Any:
    return get_price(symbol)


@mcp.resource("file://symbol_map.csv")
def symbol_map() -> str:
    with open(THIS_FOLDER / "symbol_map.csv", "r") as f:
        return f.read()

@mcp.tool()
def get_option_premium(
    symbol: str,
    strike: float,
    expiry_date: str,
    option_type: str = "call"
) -> Any:
    """
    Get the current premium (bid, ask, last price) for a stock option.
    
    Args:
        symbol (str): The stock symbol (e.g., 'PLTR', 'AAPL', 'TSLA')
        strike (float): The strike price of the option (e.g., 200.0)
        expiry_date (str): The expiration date in format 'YYYY-MM-DD' or 'MM/DD/YYYY' (e.g., '2025-11-07' or '11/7/2025')
        option_type (str): Type of option - 'call' or 'put' (default: 'call')
    
    Returns:
        Any: Dictionary containing bid, ask, last price, volume, and open interest for the option
    """
    try:
        # Parse expiry date
        try:
            # Try MM/DD/YYYY format first
            if '/' in expiry_date:
                exp_date = datetime.strptime(expiry_date, "%m/%d/%Y").date()
            else:
                # Try YYYY-MM-DD format
                exp_date = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        except ValueError:
            return {"error": f"Invalid date format: {expiry_date}. Use 'YYYY-MM-DD' or 'MM/DD/YYYY'"}
        
        # Get the stock ticker
        ticker = yf.Ticker(symbol.upper())
        
        # Get options chain for the expiry date
        # yfinance uses timestamp format for expiry dates
        try:
            opt_chain = ticker.option_chain(exp_date.strftime("%Y-%m-%d"))
        except Exception as e:
            return {"error": f"Could not fetch options chain: {str(e)}. Make sure the expiry date is valid and the symbol has options available."}
        
        # Select calls or puts
        options_df = opt_chain.calls if option_type.lower() == "call" else opt_chain.puts
        
        # Find the option with matching strike price
        # Allow small tolerance for floating point comparison
        matching_options = options_df[abs(options_df['strike'] - strike) < 0.01]
        
        if matching_options.empty:
            # Return available strikes near the requested strike
            closest_strikes = options_df.iloc[(options_df['strike'] - strike).abs().argsort()[:5]]['strike'].tolist()
            return {
                "error": f"No option found with strike {strike}",
                "available_strikes_nearby": closest_strikes,
                "requested_strike": strike,
                "expiry_date": exp_date.strftime("%Y-%m-%d"),
                "option_type": option_type
            }
        
        # Get the first matching option (should be unique)
        option = matching_options.iloc[0]
        
        # Return the premium information
        result = {
            "symbol": symbol.upper(),
            "strike": float(option['strike']),
            "expiry_date": exp_date.strftime("%Y-%m-%d"),
            "option_type": option_type.lower(),
            "last_price": float(option['lastPrice']) if pd.notna(option['lastPrice']) else None,
            "bid": float(option['bid']) if pd.notna(option['bid']) else None,
            "ask": float(option['ask']) if pd.notna(option['ask']) else None,
            "volume": int(option['volume']) if pd.notna(option['volume']) else 0,
            "open_interest": int(option['openInterest']) if pd.notna(option['openInterest']) else 0,
            "implied_volatility": float(option['impliedVolatility']) if pd.notna(option['impliedVolatility']) else None,
        }
        
        # Calculate mid price if both bid and ask are available
        if result['bid'] is not None and result['ask'] is not None:
            result['mid_price'] = (result['bid'] + result['ask']) / 2
        
        return result
        
    except Exception as e:
        return {"error": f"Error fetching option premium: {str(e)}"}

if __name__ == "__main__":    
    print("\nStarting Binance MCP Server...")

    if not ACTIVITY_LOG_PATH.exists():
        ACTIVITY_LOG_PATH.touch()

    mcp.run()