import asyncio
import sys
import os

# Now that the path is set up, we can import the function
from app.web.openai_ptalk.tools import send_plain_email

async def main_test():
    """
    A simple test function to send an email.
    """
    print("Attempting to send a test email...")
    
    recipient = "huangdai@hotmail.com"
    subject = "Testing send_plain_email function"
    content = "This is a test email sent directly from the test script."

    # Call the function
    # The send_plain_email function expects to be called from an environment
    # where config variables (SMTP_SERVER etc.) are loaded.
    # Ensure your .env file is in the project root and config.py loads it.
    try:
        result_json = await send_plain_email(
            email_address=recipient,
            subject=subject,
            body=content
        )
        print(f"Function call result: {result_json}")
    except Exception as e:
        print(f"An error occurred while trying to send the email: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # This script is intended to be run with `python -m tests.ut_send_email`
    asyncio.run(main_test())