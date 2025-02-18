import yfinance as yf
import matplotlib.pyplot as plt

import smtplib  
from email.mime.text import MIMEText  
from email.mime.multipart import MIMEMultipart  
from email.mime.base import MIMEBase
from email import encoders
import os


def get_data(ticker_name):
    ticker = yf.Ticker(ticker_name)
    return ticker.history(period='2y')


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
    from_email = "jesper.van.winden@gmail.com"
    from_password = "otyj yvfb cwul qhga"

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

    create_and_send_email(data, window, ticker_name, recipients="jesper.van.winden@gmail.com", breach=check_breach(data))


if __name__ == "__main__":
    run_script(ticker_name = '^GSPC', window=200)