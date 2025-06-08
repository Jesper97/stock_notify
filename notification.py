from alpha_vantage.timeseries import TimeSeries
import matplotlib.pyplot as plt
import pandas as pd
import smtplib

from email.mime.text import MIMEText  
from email.mime.multipart import MIMEMultipart  
from email.mime.base import MIMEBase
from email import encoders
import os

from dotenv import load_dotenv

load_dotenv()

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
if not ALPHA_VANTAGE_API_KEY:
    raise ValueError("API key not found. Make sure it's set in the environment.")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

BTD_POSITIONS = pd.DataFrame(
    {
        "Investment": [288.96],
        "Buy price": [96.32]
    }
)


def get_data(ticker_name):
    ts = TimeSeries(key=ALPHA_VANTAGE_API_KEY, output_format='pandas')
    data, _ = ts.get_daily(symbol=ticker_name, outputsize='full')

    data = data.rename(columns={
        "1. open": "Open",
        "2. high": "High",
        "3. low": "Low",
        "4. close": "Close",
        "5. volume": "Volume"
    })

    data.index = pd.to_datetime(data.index)
    data = (
        data.loc[data.index >= pd.Timestamp.today() - pd.DateOffset(years=2)]
        .iloc[::-1]
    )

    return data


def calc_btd_returns(positions, price_data):
    last_close = price_data["Close"].iloc[-1]
    positions = positions.copy()
    positions["Return"] = (last_close - positions["Buy price"]) / positions["Buy price"]
    positions["Return"] = (100*positions["Return"]).round(1)
    return positions


def calculate_moving_avg(data, window=200):
    data['MA'] = data['Close'].rolling(window=window).mean()
    return data


def check_breach(data):
    yesterday = data['Close'].iloc[-2] > data['MA'].iloc[-2]
    today = data['Close'].iloc[-1] > data['MA'].iloc[-1]

    if yesterday != today:
        breach = True
    else:
        breach = False

    return breach


def check_drawdown_breach(price_series):
    all_time_high = price_series.max()
    current_price = price_series.iloc[-1]

    current_drawdown = round((1 - current_price / all_time_high) * 100, 1)

    if current_drawdown < 10:
        return False, None, current_drawdown

    # Historical drawdowns
    historical_drawdowns = ((1 - price_series / all_time_high) * 100).round(1)

    # Check for first-time breach of any 10% multiple
    for level in sorted(range(10, int(current_drawdown) + 1, 10)):
        previously_breached = (historical_drawdowns.iloc[:-1] >= level).any()
        now_breached = historical_drawdowns.iloc[-1] >= level

        if now_breached and not previously_breached:
            return True, level, current_drawdown

    return False, None, current_drawdown


def generate_fig(data, window, ticker_name):
    data = data.dropna(subset=["MA"])
    plt.plot(data.index, data["Close"], label="Close", color="blue")  # or default color
    plt.plot(data.index, data["MA"], label=f"{window}-day MA", color="orange")

    # Highlight the last 'window' Close values in green
    if len(data) >= window:
        recent_data = data.iloc[-window:]
        plt.plot(recent_data.index, recent_data["Close"], color="green", linewidth=2)

    # Add a dot at the last data point of "Close"
    last_date = data.index[-1]
    last_close = data["Close"].iloc[-1]
    plt.plot(last_date, last_close, 'o', color='black', markersize=6, label='Last Close')

    plt.title(f"{ticker_name} \n{data.index[-1].date()}")
    plt.legend([f"{ticker_name}", f"{window}-day MA"])
    plt.ylabel("USD")

    plot_filename = "index_ma_plot.png"
    plt.savefig(plot_filename)
    plt.close()

  
def send_email(subject, body, to_email, attachment_path, is_html=True):  
    from_email = EMAIL_ADDRESS
    from_password = EMAIL_PASSWORD

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    # Attach the email body, using HTML or plain text
    mime_subtype = 'html' if is_html else 'plain'
    msg.attach(MIMEText(body, mime_subtype))

    if attachment_path:  
        attachment = open(attachment_path, "rb")
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {os.path.basename(attachment_path)}")
        msg.attach(part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, from_password)
        text = msg.as_string()
        server.sendmail(from_email, to_email, text)
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")


def create_and_send_email(data, table, window, ticker_name1, ticker_name2, recipients, ma_breach):
    # ==== ACTION FLAGS ====
    return_breach = any(table["Return"] > 20)
    dd_breach, dd_level, current_drawdown = check_drawdown_breach(data['Close'])
    action_required = ma_breach or return_breach or dd_breach

    # ==== SUBJECT ====
    subject = f"{ticker_name1} Notification {data.index[-1].date()}"
    if action_required:
        subject += " [ACTION REQUIRED]"

    # ==== MA MESSAGE ====
    if ma_breach:
        if data['Close'].iloc[-1] < data['MA'].iloc[-1]:
            ma_msg = (
                f"{ticker_name1} breached its {window}-day moving average downwards. "
                f"Please sell your position until it trades above the MA again."
            )
        else:
            ma_msg = (
                f"{ticker_name1} breached its {window}-day moving average upwards. "
                f"Please create a buy order."
            )
    else:
        ma_msg = f"{ticker_name1} did not cross its {window}-day moving average."

    # ==== RETURN MESSAGE ====
    return_msg = ""
    if return_breach:
        return_msg = f"<p><b>One of your BTD positions in {ticker_name2} has returned more than 20%. Please close the position.</b></p>"

    # ==== DRAWDOWN MESSAGE ====
    dd_msg = f"<p>Current drawdown {ticker_name2} from all-time high: {current_drawdown:.1f}%</p>"
    if dd_breach and dd_level is not None:
        dd_msg += (
            f"<p>{ticker_name2} has dropped more than {dd_level}% from its all-time high. "
            f"Please evaluate whether to buy the dip.</p>"
        )

    # ==== TABLE ====
    table_html = table.to_html(index=False, float_format="%.1f")

    # ==== BODY ====
    body = f"""
    <html>
        <body>
            <p><b>MSCI World:</p></b>
            {return_msg}
            {dd_msg}
            <p>Positions Summary:</p>
            {table_html}
            <p><b>S&P 500:</p></b>
            <p>{ma_msg}</p>
        </body>
    </html>
    """

    # ==== SEND EMAIL ====
    send_email(subject, body, recipients, attachment_path="index_ma_plot.png", is_html=True)


def run_script(ticker_name1, ticker_name2, window):
    data = get_data(ticker_name=ticker_name1)
    data = calculate_moving_avg(data, window=window)

    data_msci = get_data(ticker_name=ticker_name2)
    btd_table = calc_btd_returns(BTD_POSITIONS, data_msci)

    generate_fig(data, window=window,ticker_name=ticker_name1)

    create_and_send_email(data, btd_table, window, ticker_name1, ticker_name2, recipients=EMAIL_ADDRESS, ma_breach=check_breach(data))


if __name__ == "__main__":
    run_script(ticker_name1='SPY', ticker_name2='IWDA.AS', window=200)
    # run_script(ticker_name2='IWDA.AS', window=200)
