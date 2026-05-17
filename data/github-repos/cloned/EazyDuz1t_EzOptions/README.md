<div align="center">
  <h1>Ez Options</h1>
  <p>Unlock the power of options trading with Ez Options, a real-time analysis tool that provides interactive visualizations of options data, greeks, and market indicators. Whether you're a seasoned trader or just starting out, Ez Options helps you make informed decisions with its user-friendly interface and comprehensive data analysis.</p>
  <a href="https://github.com/EazyDuz1t/EzOptions">
    <img src="https://img.shields.io/github/stars/EazyDuz1t/EzOptions" alt="GitHub Repo stars"/>
  </a>
</div>

<div align="center">
  <img src="https://i.imgur.com/4rQXa1C.png" width="500">
</div>

<div align="center">
  <img src="https://i.imgur.com/2J93Tgv.png" width="500">
</div>

## Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Requirements](#requirements)
- [Usage](#usage)
- [How to Keep Updated](#how-to-keep-updated)
- [Credits](#credits)

## Quick Start

1. Download the latest version of the repository [here](https://github.com/EazyDuz1t/EzOptions/archive/refs/heads/main.zip)
2. Navigate to the project directory: `cd ezoptions`
3. Create a virtual environment: `python -m venv venv`
4. Activate the virtual environment:
    * On Windows: `.\venv\Scripts\activate`
    * On macOS and Linux: `source venv/bin/activate`
5. Run `python main.py` to install the required dependencies and launch the dashboard using Streamlit.

## Features

- **Real-time options data visualization:** Provides up-to-the-minute options chain data, allowing users to see the latest prices, volumes, and open interest for calls and puts.
- **Interactive dashboard with multiple views:** A user-friendly interface with different panels for analyzing options data:
    * **Volume and Open Interest analysis:** Visualize volume and open interest data to identify potential support and resistance levels.
    * **Greeks exposure (Delta, Gamma, Vanna, Charm):** Calculate and display the Greeks for a given option, providing insights into its sensitivity to changes in price, time, and volatility.
    * **Intraday price tracking with key levels:** Track the intraday price movements of the underlying asset and identify key support and resistance levels.

## Requirements

- **Python:** 3.13.1 or higher required
- **Dependencies:** Required Python packages are listed in `requirements.txt` and can be installed using `pip install -r requirements.txt`.

## Usage

1. **Launch the dashboard:** Follow the instructions in the [Quick Start](#quick-start) section to launch the dashboard.
2. **Enter a stock ticker:** In the input field, enter the ticker symbol of the stock you want to analyze (e.g., AAPL for Apple, TSLA for Tesla, SPX for S&P 500).
3. **Explore the dashboard:** Use the sidebar menu to navigate between different views:
    * **Volume and Open Interest:** Analyze the volume and open interest data to identify potential support and resistance levels. Look for large spikes in volume or open interest at specific strike prices, which may indicate significant levels.
    * **Greeks Exposure:** Examine the Greeks (Delta, Gamma, Vanna, Charm) to understand the option's sensitivity to changes in price, time, and volatility. Use this information to assess the risk and potential reward of the option.
    * **Intraday Price Tracking:** Track the intraday price movements of the underlying asset and identify key support and resistance levels. Look for patterns such as double tops, double bottoms, and trendlines.
4. **Perform analysis:** Use the interactive tools and visualizations to perform your own analysis. For example, you can:
    * Identify potential trading opportunities based on volume and open interest data.
    * Assess the risk of an option position based on its Greeks.
    * Track the price movements of the underlying asset to identify potential entry and exit points.

## How to Keep Updated

1. Running `main.py` will always ensure you are using the latest version of EzOptions.
2. Stay tuned for new features and improvements by following our [GitHub repository](https://github.com/EazyDuz1t/EzOptions). We are constantly adding new features and enhancements to make your trading experience even better!

## Credits

- Based on the Options Analyzer project by [anvgun](https://github.com/anvgun/Options_Analyzer).
- Additional contributions by [EazyDuz1t](https://github.com/EazyDuz1t).

## Contact

For any inquiries or support, please contact Eazy101 at:
- **Discord:** eazy101
