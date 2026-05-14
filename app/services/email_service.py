import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
PORTAL_URL = os.getenv("PORTAL_URL", "http://localhost:3000")

def send_welcome_email(email: str, display_name: str, password: str):
    if not SMTP_USER or not SMTP_PASSWORD:
        print("⚠️ SMTP credentials not set. Skipping welcome email.")
        return

    subject = "Welcome to 7G House - Your Account is Ready"
    
    html_content = f"""
    <html>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #000; padding: 30px; border-radius: 20px 20px 0 0; text-align: center;">
                <h1 style="color: #fff; margin: 0; font-size: 28px; letter-spacing: -1px;">7G House</h1>
            </div>
            <div style="background-color: #f9f9f9; padding: 40px; border-radius: 0 0 20px 20px; border: 1px solid #eee;">
                <h2 style="color: #000; margin-top: 0;">Welcome, {display_name}!</h2>
                <p>Your internal account for the <strong>7G House AI Portal</strong> has been created. You can now start generating and managing architectural visualizations.</p>
                
                <div style="background-color: #fff; padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0; margin: 25px 0;">
                    <p style="margin-top: 0; font-weight: bold; color: #666; text-transform: uppercase; font-size: 11px;">Your Login Credentials</p>
                    <p style="margin-bottom: 8px;"><strong>Email:</strong> {email}</p>
                    <p style="margin-bottom: 0;"><strong>Password:</strong> <code style="background: #eee; padding: 2px 6px; border-radius: 4px;">{password}</code></p>
                </div>

                <div style="text-align: center; margin: 35px 0;">
                    <a href="{PORTAL_URL}" style="background-color: #000; color: #fff; padding: 14px 30px; text-decoration: none; border-radius: 10px; font-weight: bold; font-size: 16px;">Login to Portal</a>
                </div>

                <p style="font-size: 13px; color: #888;">For security reasons, we recommend changing your password after your first login in your profile settings.</p>
                
                <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="font-size: 12px; color: #bbb; text-align: center;">&copy; 2026 7G House. All rights reserved.</p>
            </div>
        </body>
    </html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"7G House <{SMTP_USER}>"
    msg['To'] = email
    msg['Subject'] = subject

    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
            print(f"✅ Welcome email sent to {email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
