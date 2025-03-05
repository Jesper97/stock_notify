from alpha_vantage.timeseries import TimeSeries
import matplotlib.pyplot as plt
import pandas as pd
import smtplib

from email.mime.text import MIMEText  
from email.mime.multipart import MIMEMultipart  
from email.mime.base import MIMEBase
from email import encoders
import os

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
if not ALPHA_VANTAGE_API_KEY:
    raise ValueError("API key not found. Make sure it's set in the environment.")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

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


def generate_fig(data, window, ticker_name):
    data[["Close", "MA"]].plot()
    plt.title(f"{ticker_name} \n{data.index[-1].date()}")
    plt.legend([f"{ticker_name}", f"{window}-day MA"])
    plt.ylabel("USD")

    plot_filename = "index_ma_plot.png"
    plt.savefig(plot_filename)
    plt.close()

  
def send_email(subject, body, to_email, attachment_path):  
    from_email = EMAIL_ADDRESS
    from_password = EMAIL_PASSWORD

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

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


def create_and_send_email(data, window, ticker_name, recipients, breach):
    subject = f"{ticker_name} Notification {data.index[-1].date()}" 
    if breach:  
        subject += " [ACTION REQUIRED]"
        if data['Close'].iloc[-1] < data['MA'].iloc[-1]: # Check if breach was downwards
            body = f"{ticker_name} breached its {window}-day moving average downwards. Please sell your position until {ticker_name} is trading above its MA again."
        else:
            body = f"{ticker_name} breached its {window}-day moving average upwards. Please create a buy order."
    else:
        body = f"No action required, {ticker_name} did not cross its {window}-day moving average."

    send_email(subject, body, recipients, attachment_path="index_ma_plot.png")


def run_script(ticker_name, window):
    data = get_data(ticker_name=ticker_name)
    data = calculate_moving_avg(data, window=window)
    generate_fig(data, window=window,ticker_name=ticker_name)

    create_and_send_email(data, window, ticker_name, recipients=EMAIL_ADDRESS, breach=check_breach(data))


if __name__ == "__main__":
    run_script(ticker_name = 'SPY', window=200)
