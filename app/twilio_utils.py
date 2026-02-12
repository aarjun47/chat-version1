import os
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

client = Client(ACCOUNT_SID, AUTH_TOKEN)


def send_whatsapp_message(to: str, body: str):
    client.messages.create(
        from_=WHATSAPP_NUMBER,
        to=f"whatsapp:{to}",
        body=body
    )


# (Optional) keep this for sandbox fallback
def twiml_reply(text: str):
    resp = MessagingResponse()
    resp.message(text)
    return str(resp)
